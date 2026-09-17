from copy import deepcopy

import pytest
from pydantic import ValidationError

from review_comparison import build_review_result, result_status
from review_evidence import verify_extraction
from review_schema import Observation, ReviewExtraction


def observation(scope, value, quote, **kwargs):
    return {"scope": scope, "value": value, "kind": "explicit", "confidence": 0.99,
            "reason": "Aus dem Dokument übernommen.", "evidence": {"page": 1, "quote": quote},
            "entity": "document", **kwargs}


def extraction(facts, *, document_type="invoice", document=1, text=None):
    raw = ReviewExtraction.model_validate({"document_type": document_type, "observations": facts,
                                          "warnings": []})
    source = text if text is not None else "\n".join(fact["evidence"]["quote"] for fact in facts if fact.get("evidence"))
    return verify_extraction(raw, {1: source}, document, f"Dokument {document}.pdf")


def stored(**kwargs):
    return {"title": "Veeam Upgrade und Maintenance", "description": None, "value": 9752.05,
            "annual_value": None, "start_date": "2024-02-22", "end_date": None,
            "notice_period": 30, "tags": [], "version": 1, **kwargs}


def checks(result):
    return {check["field"]: check for check in result["checks"]}


def test_veeam_all_positions_gross_delivery_and_missing_notice():
    positions = [("Upgrade-Lizenzen", 2155.28, "2 x 1.077,64 = 2.155,28 EUR netto"),
                 ("Maintenance Uplift", 94.26, "6 x 15,71 = 94,26 EUR netto"),
                 ("3 Jahre Production Maintenance", 5945.46, "2 x 2.972,73 = 5.945,46 EUR netto")]
    facts = [observation("line_item_net", amount, quote, currency="EUR", entity="line_item")
             for _, amount, quote in positions]
    facts += [observation("invoice_total_net", 8195.0, "Gesamt netto: 8.195,00 EUR; Umsatzsteuer 19 %", currency="EUR"),
              observation("tax_rate", 19, "Umsatzsteuer 19 %"),
              # Even a mislabeled model response is corrected using the delivery label.
              observation("contract_start_date", "2024-02-22", "Lieferschein Nr.: LS0681451 vom 22.02.24")]
    data = extraction(facts)
    result = build_review_result(stored(), [data], "invoice")
    fields = checks(result)
    assert fields["value"]["status"] == "DERIVED"
    assert fields["value"]["after"] == 9752.05
    assert not fields["value"]["is_conflict"] and not fields["value"]["can_apply"]
    assert fields["notice_period"]["status"] == "NOT_EVIDENCED"
    assert not fields["notice_period"]["can_apply"]
    assert fields["start_date"]["status"] == "WRONG_SCOPE"
    assert fields["start_date"]["document_scope"] == "delivery_date"
    assert "components" not in result
    assert result_status(result) == "hints"
    legacy = checks(build_review_result(stored(), [data], "contract"))["value"]
    assert legacy["stored_scope"] == "contract_value_gross"
    assert legacy["status"] == "DERIVED" and not legacy["can_apply"] and not legacy["is_conflict"]


def test_line_item_never_replaces_gross_even_if_model_mislabels_it():
    data = extraction([observation("invoice_total_gross", 2155.28, "Position 1: 2 x 1.077,64 = 2.155,28 EUR netto", currency="EUR")])
    field = checks(build_review_result(stored(), [data], "invoice"))["value"]
    assert field["status"] == "WRONG_SCOPE"
    assert not field["can_apply"] and not field["is_conflict"]


@pytest.mark.parametrize(("old", "new", "expected"), [(30, 30, "CONFIRMED"), (30, 90, "EXPLICIT_CONFLICT"), (None, 90, "NEW_INFORMATION")])
def test_explicit_same_scope_notice(old, new, expected):
    quote = f"Die ordentliche Kündigungsfrist beträgt {new} Tage."
    data = extraction([observation("notice_period", new, quote)], document_type="contract")
    field = checks(build_review_result(stored(notice_period=old), [data], "contract"))["notice_period"]
    assert field["status"] == expected
    assert field["can_apply"] == (expected != "CONFIRMED")
    assert field["is_conflict"] == (expected == "EXPLICIT_CONFLICT")


def test_absence_is_not_a_conflict_or_deletion_and_does_not_require_review():
    result = build_review_result(stored(), [extraction([])], "contract")
    assert result_status(result) == "checked"
    assert all(field["status"] == "NOT_EVIDENCED" and not field["can_apply"] for field in result["checks"])


def test_unverifiable_quote_cannot_create_high_confidence_conflict():
    data = extraction([observation("notice_period", 90, "Kündigungsfrist 90 Tage")], text="Keine Vertragsbedingungen.")
    field = checks(build_review_result(stored(), [data], "contract"))["notice_period"]
    assert field["status"] == "AMBIGUOUS" and not field["can_apply"]
    assert field["confidence"] <= 0.4


def test_contract_authority_wins_over_invoice_but_peer_conflicts_need_review():
    contract = extraction([observation("notice_period", 30, "Kündigungsfrist 30 Tage")], document_type="contract")
    invoice = extraction([observation("notice_period", 90, "Kündigungsfrist 90 Tage")], document=2)
    result = checks(build_review_result(stored(), [invoice, contract], "contract"))
    assert result["notice_period"]["status"] == "CONFIRMED"
    peer = deepcopy(invoice)
    peer["observations"][0]["document_type"] = "contract"
    result = checks(build_review_result(stored(), [contract, peer], "contract"))
    assert result["notice_period"]["status"] == "AMBIGUOUS"
    assert not result["notice_period"]["can_apply"]


@pytest.mark.parametrize("currency", ["USD", None])
def test_other_or_missing_currency_is_not_a_comparable_amount(currency):
    data = extraction([observation("invoice_total_gross", 42.0, "Gesamt brutto 42,00", currency=currency)])
    field = checks(build_review_result(stored(), [data], "invoice"))["value"]
    assert field["status"] == "WRONG_SCOPE" and not field["can_apply"]


def test_unknown_legacy_date_is_not_assigned_a_meaning_even_if_numbers_match():
    data = extraction([observation("invoice_date", "2024-02-22", "Rechnungsdatum: 22.02.2024")])
    field = checks(build_review_result(stored(), [data], "invoice"))["start_date"]
    assert field["status"] == "AMBIGUOUS" and not field["can_apply"]


@pytest.mark.parametrize("value", ["9.752,05", "9752.05", True, float("inf"), float("nan"), -1])
def test_rejects_invalid_amounts(value):
    with pytest.raises(ValidationError):
        Observation.model_validate(observation("invoice_total_gross", value, "Total"))


@pytest.mark.parametrize("payload", [{}, {"observations": []}, {"document_type": "invoice", "observations": [], "components": [], "warnings": [], "extra": True}])
def test_incomplete_or_unexpected_model_schema_is_rejected(payload):
    with pytest.raises(ValidationError):
        ReviewExtraction.model_validate(payload)


def test_other_contract_cannot_supply_parent_end_date():
    fact = observation("contract_end_date", "2027-05-25", "Laufzeitende 25.05.2027", entity="other_source")
    result = checks(build_review_result(stored(), [extraction([fact])], "contract"))
    assert result["end_date"]["status"] == "WRONG_SCOPE"
    assert not result["end_date"]["can_apply"]


def test_invented_tax_cannot_supply_verified_gross_calculation():
    data = extraction([observation("invoice_total_net", 8195, "Gesamt netto 8.195,00 EUR", currency="EUR"),
                       observation("tax_rate", 19, "Umsatzsteuer enthalten")])
    result = build_review_result(stored(), [data], "invoice")
    assert not any(fact["scope"] == "invoice_total_gross" for fact in result["observations"])
    assert not checks(result)["value"]["can_apply"]


def test_invented_date_in_existing_quote_cannot_change_contract():
    data = extraction([observation("contract_end_date", "2027-05-25", "Laufzeitende 31.12.2026")], document_type="contract")
    field = checks(build_review_result(stored(), [data], "contract"))["end_date"]
    assert field["status"] == "AMBIGUOUS" and not field["can_apply"]


def test_low_confidence_new_value_requires_manual_review():
    data = extraction([observation("notice_period", 90, "Kündigungsfrist 90 Tage", confidence=0.2)], document_type="contract")
    field = checks(build_review_result(stored(notice_period=None), [data], "contract"))["notice_period"]
    assert field["status"] == "AMBIGUOUS" and not field["can_apply"]


def test_monthly_amount_cannot_be_applied_as_annual_value():
    data = extraction([observation("annual_value", 120, "Monatliches Entgelt 120,00 EUR", currency="EUR", billing_interval="month")])
    field = checks(build_review_result(stored(), [data], "contract"))["annual_value"]
    assert field["status"] == "WRONG_SCOPE" and not field["can_apply"]


@pytest.mark.parametrize("document_type", ["contract", "invoice"])
@pytest.mark.parametrize("scope,value,quote", [
    ("invoice_total_net", 8195, "Gesamt netto: 8.195,00 EUR"),
    ("invoice_total_gross", 2155.28, "Upgrade Veeam 2 Stk 1.077,64 2.155,28 EUR"),
    ("contract_value_gross", 5834, "VMw vSph EssPlus 6P 3yr E-LTU 5.834,00 EUR netto"),
    ("invoice_total_gross", 8195, "Gesamt netto: 8.195,00 EUR"),
    ("invoice_total_gross", 2155.28, "Upgrade 2.155,28 EUR; Gesamt brutto 9.752,05 EUR"),
    ("invoice_total_gross", 2155.28, "Gesamt brutto 9.752,05 EUR; Upgrade 2.155,28 EUR"),
])
def test_only_labeled_gross_total_can_replace_total(document_type, scope, value, quote):
    data = extraction([observation(scope, value, quote, currency="EUR")])
    field = checks(build_review_result(stored(), [data], document_type))["value"]
    assert not field["can_apply"] and not field["is_conflict"]


@pytest.mark.parametrize("document_type", ["contract", "invoice"])
def test_full_invoice_gross_including_services_confirms_value(document_type):
    data = extraction([observation("invoice_total_gross", 9752.05, "Gesamt brutto: 9.752,05 EUR", currency="EUR")])
    field = checks(build_review_result(stored(), [data], document_type))["value"]
    assert field["status"] == "CONFIRMED" and not field["can_apply"]


def test_gross_is_not_calculated_from_tax_of_another_invoice():
    data = extraction([observation("invoice_total_net", 8195, "Gesamt netto 8.195,00 EUR", currency="EUR"),
                       observation("tax_rate", 19, "Alte Rechnung: Umsatzsteuer 19 %")])
    assert not checks(build_review_result(stored(), [data], "invoice"))["value"]["can_apply"]
    assert not any(fact["scope"] == "invoice_total_gross" for fact in build_review_result(stored(), [data], "invoice")["observations"])


def test_different_source_totals_never_silently_choose_one():
    invoice = extraction([observation("invoice_total_gross", 9752.05, "Gesamt brutto 9.752,05 EUR", currency="EUR")])
    contract = extraction([observation("contract_value_gross", 120, "Gesamt brutto 120 EUR", currency="EUR")], document_type="contract", document=2)
    field = checks(build_review_result(stored(), [invoice, contract], "contract"))["value"]
    assert field["status"] == "AMBIGUOUS" and not field["can_apply"]
