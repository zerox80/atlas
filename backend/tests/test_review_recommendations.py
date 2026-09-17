"""Review decisions remain useful while retaining evidence and scope checks."""

import pytest
from test_review_semantics import checks, extraction, observation, stored

from review_comparison import build_review_result


@pytest.mark.parametrize("scope,field,value,quote,extra", [
    ("invoice_total_gross", "value", 119, "Gesamt brutto 119,00 EUR", {"currency": "EUR"}),
    ("invoice_date", "start_date", "2024-03-01", "Rechnungsdatum 01.03.2024", {}),
    ("contract_end_date", "end_date", "2027-12-31", "Laufzeitende 31.12.2027", {}),
])
def test_verified_numeric_and_date_suggestions_survive_low_model_confidence(scope, field, value, quote, extra):
    data = extraction([observation(scope, value, quote, confidence=0.2, **extra)])
    result = build_review_result(stored(), [data], "invoice")
    check = checks(result)[field]
    assert result["comparison_version"] == 1
    assert check["can_apply"] and check["recommendation"] == "update"
    assert check["after"] == value and "niedrige Sicherheit" in check["reason"]
    assert "manuell" not in check["recommendation_reason"]


def test_verified_gross_calculation_survives_low_model_confidence():
    quote = "Gesamt netto 100,00 EUR zzgl. Umsatzsteuer 19 %"
    data = extraction([
        observation("invoice_total_net", 100, quote, currency="EUR", confidence=0.2),
        observation("tax_rate", 19, "Umsatzsteuer 19 %", confidence=0.2),
    ])
    check = checks(build_review_result(stored(value=100), [data], "invoice"))["value"]
    assert check["status"] == "DERIVED" and check["after"] == 119
    assert check["can_apply"] and check["recommendation"] == "update"


@pytest.mark.parametrize("scope,value", [
    ("title", "Softwarelizenzen mit Wartung"),
    ("description", "Softwarelizenzen und dreijährige Wartung für die vorhandene Installation."),
    ("tags", ["Software", "Wartung"]),
])
def test_grounded_editorial_suggestions_survive_low_model_confidence(scope, value):
    quote = "Veeam Upgrade-Lizenzen und drei Jahre Production Maintenance"
    data = extraction([observation(scope, value, quote, kind="derived", confidence=0.2)])
    check = checks(build_review_result(stored(), [data], "invoice"))[scope]
    assert check["status"] == "DERIVED" and check["can_apply"]
    assert check["recommendation"] == "update"
    assert "Aus dem Dokument" in check["recommendation_reason"]


def test_same_derived_title_recommends_keeping_instead_of_proposing_a_change():
    old = stored()
    data = extraction([observation("title", old["title"], "Veeam Upgrade und Maintenance", kind="derived", confidence=0.2)])
    check = checks(build_review_result(old, [data], "invoice"))["title"]
    assert not check["can_apply"] and check["recommendation"] == "keep"
    assert "bereits dem gespeicherten Wert" in check["recommendation_reason"]


@pytest.mark.parametrize("old,expected", [(None, "leave_empty"), ("", "leave_empty"), ("Vorhandene Beschreibung", "keep")])
def test_missing_evidence_gives_explicit_keep_or_leave_empty_recommendation(old, expected):
    result = build_review_result(stored(description=old), [extraction([])], "invoice")
    check = checks(result)["description"]
    assert check["recommendation"] == expected and not check["can_apply"]
    assert "keine Aussage" in check["recommendation_reason"]
    assert all(entry["recommendation"] in {"update", "keep", "leave_empty"} and entry["recommendation_reason"] for entry in result["checks"])
    assert checks(result)["tags"]["recommendation"] == "leave_empty"


@pytest.mark.parametrize("failure", ["quote", "ambiguous", "unknown"])
def test_editorial_change_still_requires_usable_evidence(failure):
    quote = "Softwarelizenzen mit Wartung"
    data = extraction(
        [observation("title", "Vollständiger Titel", quote, kind="ambiguous" if failure == "ambiguous" else "derived")],
        text="Keine passende Belegstelle" if failure == "quote" else quote,
        document_type="unknown" if failure == "unknown" else "contract",
    )
    check = checks(build_review_result(stored(), [data], "contract"))["title"]
    assert check["status"] == "AMBIGUOUS" and not check["can_apply"]
    assert check["recommendation"] == "keep"
    assert "belassen" in check["recommendation_reason"]


@pytest.mark.parametrize("scope,quote", [
    ("delivery_date", "Lieferdatum 01.03.2024"),
    ("order_date", "Bestelldatum 01.03.2024"),
])
def test_other_date_roles_do_not_replace_start_date(scope, quote):
    data = extraction([observation(scope, "2024-03-01", quote)])
    check = checks(build_review_result(stored(), [data], "invoice"))["start_date"]
    assert check["status"] == "WRONG_SCOPE" and not check["can_apply"]
    assert check["recommendation"] == "keep" and "anderen Bedeutung" in check["recommendation_reason"]


def test_conflicting_totals_recommend_keeping_existing_value():
    data = extraction([
        observation("invoice_total_gross", 119, "Gesamt brutto 119,00 EUR", currency="EUR"),
        observation("invoice_total_gross", 238, "Gesamt brutto 238,00 EUR", currency="EUR"),
    ])
    check = checks(build_review_result(stored(), [data], "invoice"))["value"]
    assert check["status"] == "AMBIGUOUS" and not check["can_apply"]
    assert check["recommendation"] == "keep" and "widersprüchliche" in check["recommendation_reason"]


def test_split_updates_recommendation_after_blocking_collection_amount():
    data = extraction([observation("invoice_total_gross", 119, "Gesamt brutto 119,00 EUR", currency="EUR")])
    data["split_proposals"] = [{"title": "Erstes Dokument"}, {"title": "Zweites Dokument"}]
    check = checks(build_review_result(stored(), [data], "invoice"))["value"]
    assert check["recommendation"] == "keep" and not check["can_apply"]
    assert "mehrere eigenständige Dokumente" in check["recommendation_reason"]


def test_model_calculation_without_verified_arithmetic_is_not_a_change_recommendation():
    data = extraction([observation("annual_value", 120, "Jährliche Abrechnung", currency="EUR", kind="derived")])
    check = checks(build_review_result(stored(), [data], "contract"))["annual_value"]
    assert check["status"] == "DERIVED" and not check["can_apply"]
    assert check["recommendation"] == "leave_empty"
    assert "Berechnung ist nicht anhand ihrer Grundlagen bestätigt" in check["recommendation_reason"]
