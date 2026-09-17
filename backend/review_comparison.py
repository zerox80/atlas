"""Semantic comparison and centrally configured source authority (no model decisions applied blindly)."""

from decimal import Decimal

from review_evidence import add_verified_totals
from review_schema import DATE_SCOPES, MONEY_SCOPES, PIPELINE_VERSION, REVIEW_FIELDS

# Highest authority first. Unknown sources can supply hints, never explicit conflicts.
CONTRACT_PRIORITY = ("contract", "amendment", "order_confirmation", "invoice", "delivery_note", "unknown")
SOURCE_PRIORITY = {
    "notice_period": CONTRACT_PRIORITY,
    "contract_start_date": ("contract", "order_confirmation", "amendment", "invoice", "delivery_note", "unknown"),
    "contract_end_date": CONTRACT_PRIORITY,
    "invoice_total_net": ("invoice", "order_confirmation", "contract", "amendment", "delivery_note", "unknown"),
    "invoice_total_gross": ("invoice", "order_confirmation", "contract", "amendment", "delivery_note", "unknown"),
    "invoice_date": ("invoice", "order_confirmation", "contract", "amendment", "delivery_note", "unknown"),
}
FIELD_SCOPES = {
    "title": {"title"}, "description": {"description"}, "tags": {"tags"},
    "value": {"contract_value_net", "contract_value_gross", "invoice_total_net", "invoice_total_gross"},
    "annual_value": {"annual_value"}, "start_date": {"contract_start_date", "invoice_date"},
    "end_date": {"contract_end_date"}, "notice_period": {"notice_period"},
}


def _equal(left, right) -> bool:
    if type(left) in {float, int} and type(right) in {float, int}:
        return abs(Decimal(str(left)) - Decimal(str(right))) < Decimal("0.005")
    if isinstance(left, list) and isinstance(right, list):
        return sorted(left) == sorted(right)
    return left == right


def stored_scope(field: str, document_type: str) -> str:
    # Invoice value has always been defined as gross in Atlas. Contract value and
    # the old shared start-date field have no persisted semantics: do not guess.
    if field == "value":
        return "invoice_total_gross" if document_type == "invoice" else "legacy_amount"
    if field == "start_date":
        return "legacy_date"
    return {"end_date": "contract_end_date"}.get(field, field)


def _target_scopes(field: str, document_type: str) -> set[str]:
    if field == "value" and document_type == "invoice":
        return {"invoice_total_gross"}
    if field == "start_date":
        return {"invoice_date" if document_type == "invoice" else "contract_start_date"}
    return FIELD_SCOPES[field]


def _pick(candidates: list[dict]) -> tuple[dict, bool]:
    def rank(fact):
        order = SOURCE_PRIORITY.get(fact["scope"], CONTRACT_PRIORITY)
        return (not fact["evidence_verified"], order.index(fact["document_type"]), fact["kind"] != "explicit")
    ordered = sorted(candidates, key=rank)
    first = ordered[0]
    peers = [fact for fact in ordered if rank(fact) == rank(first)]
    different = any(not _equal(first["value"], fact["value"]) or
                    (first["scope"], first.get("currency"), first.get("billing_interval")) !=
                    (fact["scope"], fact.get("currency"), fact.get("billing_interval")) for fact in peers)
    return first, different


def compare_field(field: str, before: dict, facts: list[dict], document_type: str) -> dict:
    old = before[field]
    scope = stored_scope(field, document_type)
    base = {"field": field, "before": old, "after": None, "status": "NOT_EVIDENCED",
            "is_conflict": False, "can_apply": False, "confidence": None, "stored_scope": scope,
            "document_scope": None, "reason": "Das geprüfte Dokument enthält hierzu keine Aussage.",
            "evidence": None, "document_type": None}
    target = _target_scopes(field, document_type)
    candidates = [fact for fact in facts if fact["scope"] in target and fact["entity"] == "document"]
    if not candidates:
        related = MONEY_SCOPES if field in {"value", "annual_value"} else DATE_SCOPES if field in {"start_date", "end_date"} else target
        wrong = [fact for fact in facts if fact["scope"] in related]
        if wrong:
            fact, _ = _pick(wrong)
            base.update(after=fact["value"], status="WRONG_SCOPE", document_scope=fact["scope"],
                        reason="Der gefundene Wert gehört zu einer anderen Bedeutung oder Vertragseinheit und ist nicht vergleichbar.",
                        confidence=fact["confidence"], evidence=fact["evidence"], document=fact["document"],
                        document_name=fact["document_name"], document_type=fact["document_type"],
                        evidence_verified=fact["evidence_verified"], currency=fact.get("currency"))
        return base
    fact, disagreement = _pick(candidates)
    base.update(after=fact["value"], document_scope=fact["scope"], confidence=fact["confidence"],
                document=fact["document"], document_name=fact["document_name"], document_type=fact["document_type"],
                evidence=fact["evidence"], evidence_verified=fact["evidence_verified"], currency=fact.get("currency"),
                alternatives=[{"value": candidate["value"], "scope": candidate["scope"],
                               "document_name": candidate["document_name"], "evidence": candidate["evidence"],
                               "currency": candidate.get("currency")}
                              for candidate in candidates if candidate is not fact])
    if disagreement or fact["kind"] == "ambiguous":
        base.update(status="AMBIGUOUS", reason="Mehrdeutige oder widersprüchliche Dokumentangaben. " + fact["reason"])
    elif field in {"value", "annual_value"} and fact.get("currency") != "EUR":
        base.update(status="WRONG_SCOPE", reason="Die Währung ist unbekannt oder weicht vom EUR-Feld ab.")
    elif field == "annual_value" and fact.get("billing_interval") not in {None, "year"}:
        base.update(status="WRONG_SCOPE", reason="Der Bezugszeitraum entspricht keinem Jahreswert.")
    elif field in {"value", "start_date"} and scope.startswith("legacy_") and old is not None:
        base.update(status="AMBIGUOUS", reason="Die Bedeutung des bestehenden Legacy-Wertes ist nicht gespeichert. "
                    "Keine automatische Zuordnung oder Überschreibung. " + fact["reason"])
    elif not fact["evidence_verified"] or fact["document_type"] == "unknown":
        base.update(status="AMBIGUOUS", confidence=min(fact["confidence"], 0.4),
                    reason="Belegstelle oder Dokumenttyp nicht sicher nachweisbar. " + fact["reason"])
    elif fact["confidence"] < 0.75:
        base.update(status="AMBIGUOUS", reason="Unsichere Extraktion; den Beleg manuell prüfen. " + fact["reason"])
    elif fact["kind"] == "derived" or field in {"title", "description", "tags"}:
        base.update(status="CONFIRMED" if _equal(old, fact["value"]) and fact["kind"] == "explicit" else "DERIVED",
                    reason=fact["reason"])
        # Model-authored calculations stay informational. Only verified arithmetic
        # or editorial suggestions can be applied intentionally.
        base["can_apply"] = not _equal(old, fact["value"]) and (bool(fact.get("derivation_verified")) or field in {"title", "description", "tags"})
    elif _equal(old, fact["value"]):
        base.update(status="CONFIRMED", reason="Wert für denselben Geltungsbereich durch eine Belegstelle bestätigt.")
    elif old is None or old == "" or old == []:
        base.update(status="NEW_INFORMATION", reason="Belegte Ergänzung für ein bisher leeres Feld. " + fact["reason"], can_apply=True)
    else:
        base.update(status="EXPLICIT_CONFLICT", reason="Ausdrücklich anderer Wert für denselben Geltungsbereich. " + fact["reason"],
                    is_conflict=True, can_apply=fact["confidence"] >= 0.75)
    if len(candidates) > 1 and not disagreement:
        base["reason"] += " Quellenpriorität berücksichtigt; weitere Belege sind aufgeführt."
    return base


def result_status(result: dict) -> str:
    checks = result.get("checks", [])
    if any(check["status"] in {"EXPLICIT_CONFLICT", "AMBIGUOUS"} for check in checks):
        return "issues"
    if (any(check["status"] in {"NEW_INFORMATION", "DERIVED", "WRONG_SCOPE"} for check in checks)
            or result.get("warnings") or result.get("components")):
        return "hints"
    return "checked"


def build_review_result(before: dict, extractions: list[dict], document_type: str) -> dict:
    facts = add_verified_totals([fact for extraction in extractions for fact in extraction["observations"]])
    checks = [compare_field(field, before, facts, document_type) for field in REVIEW_FIELDS]
    components = []
    seen = set()
    for extraction in extractions:
        for component in extraction["components"]:
            key = (component["document"], component["name"], component["evidence"]["page"])
            if key not in seen:
                components.append(component)
                seen.add(key)
    return {"schema_version": PIPELINE_VERSION, "checks": checks,
            "changes": [check for check in checks if check["status"] != "CONFIRMED"],
            "observations": facts, "components": components,
            "warnings": list(dict.fromkeys(warning for extraction in extractions for warning in extraction["warnings"]))}
