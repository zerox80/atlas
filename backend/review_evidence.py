"""Keep page provenance and conservatively verify semantic observations."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ai_evidence import _normalize, enforce_notice_evidence
from review_schema import DATE_SCOPES, MONEY_SCOPES, ReviewExtraction


def _quoted_numbers(quote: str) -> set[Decimal]:
    numbers = set()
    for token in re.findall(r"(?<!\w)\d[\d.,]*(?!\w)", quote):
        token = token.rstrip(".,")
        if "," in token and "." in token:
            decimal = "," if token.rfind(",") > token.rfind(".") else "."
            token = token.replace("." if decimal == "," else ",", "").replace(decimal, ".")
        elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
            token = token.replace(".", "").replace(",", "")
        else:
            token = token.replace(",", ".")
        try:
            numbers.add(Decimal(token))
        except ArithmeticError:
            continue
    return numbers


def _quoted_dates(quote: str) -> set[str]:
    dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", quote))
    for day, month, year in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b", quote):
        try:
            # Two-digit years are deliberately not assigned a century blindly.
            parsed = date(int(year), int(month), int(day)).isoformat()
            dates.add(parsed if len(year) == 4 else parsed[2:])
        except ValueError:
            continue
    return dates


def verify_extraction(extraction: ReviewExtraction, pages: dict[int, str], document: int, name: str) -> dict:
    result = extraction.model_dump()
    for record in [*result["observations"], *result["components"]]:
        evidence = record.get("evidence")
        verified = bool(evidence and _normalize(evidence["quote"])
                        and _normalize(evidence["quote"]) in _normalize(pages.get(evidence["page"], "")))
        record.update(document=document, document_name=name, document_type=extraction.document_type,
                      evidence_verified=verified)
        if not verified:
            record["confidence"] = min(record.get("confidence", 1), 0.4)
        if "scope" not in record:
            if not verified:
                record["separate_contract_reasons"] = []
            continue
        quote = evidence["quote"] if evidence else ""
        # An explicit delivery-note label must never turn into a contract/invoice date.
        if (record["scope"] in DATE_SCOPES and re.search(r"lieferschein|lieferdatum", quote, re.IGNORECASE)
                and not re.search(r"rechnungsdatum|vertragsbeginn|leistungsbeginn|laufzeitende", quote, re.IGNORECASE)):
            record["scope"] = "delivery_date"
            record["reason"] = "Das Datum ist ausdrücklich einem Lieferschein/einer Lieferung zugeordnet."
        if (record["scope"] in {"invoice_total_net", "invoice_total_gross", "contract_value_net", "contract_value_gross"}
                and re.search(r"\bposition\b|\bpos\.|\d+\s*[x×]\s*\d", quote, re.IGNORECASE)
                and not re.search(r"gesamt|summe|total", quote, re.IGNORECASE)):
            record["scope"] = "line_item_gross" if "brutto" in quote.casefold() else "line_item_net"
            record["entity"] = "component"
            record["reason"] = "Der Beleg beschreibt eine einzelne Rechnungsposition, keinen Gesamtbetrag."
        if record["scope"] == "notice_period":
            check = enforce_notice_evidence({"notice_period": int(record["value"]),
                                            "notice_period_evidence": quote}, pages.get(evidence["page"]) if evidence else None)
            if check["notice_period"] is None:
                record.update(kind="ambiguous", evidence_verified=False, confidence=0.4)
                record["reason"] = "Keine eindeutig belegte ordentliche Kündigungsfrist in Tagen."
        # Validate only the quoted value, never match numbers across scopes.
        if (record["scope"] in MONEY_SCOPES | {"tax_rate"} and record["kind"] == "explicit" and verified
                and Decimal(str(record["value"])) not in _quoted_numbers(quote)):
            record.update(kind="ambiguous", confidence=0.4)
            record["reason"] = "Der Zahlenwert ist im angegebenen Beleg nicht eindeutig numerisch nachweisbar."
        if record["scope"] in DATE_SCOPES and record["kind"] == "explicit" and verified:
            dates = _quoted_dates(quote)
            if record["value"] not in dates and record["value"][2:] not in dates:
                record.update(kind="ambiguous", confidence=0.4)
                record["reason"] = "Das Datum ist im angegebenen Beleg nicht eindeutig nachweisbar."
    return result


def add_verified_totals(observations: list[dict]) -> list[dict]:
    """Derive gross only from one explicitly sourced net/tax pair of the same invoice."""
    output = list(observations)
    for document in {item["document"] for item in observations}:
        facts = [item for item in observations if item["document"] == document
                 and item["entity"] == "document" and item["evidence_verified"] and item["kind"] == "explicit"]
        nets = [item for item in facts if item["scope"] == "invoice_total_net"]
        taxes = [item for item in facts if item["scope"] == "tax_rate"]
        if len({(item["value"], item.get("currency")) for item in nets}) != 1 or len({item["value"] for item in taxes}) != 1:
            continue
        net, tax = nets[0], taxes[0]
        if not net.get("currency") or any(item["scope"] == "invoice_total_gross" for item in facts):
            continue
        gross = (Decimal(str(net["value"])) * (1 + Decimal(str(tax["value"])) / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        output.append({**net, "scope": "invoice_total_gross", "value": float(gross), "kind": "derived",
                       "confidence": min(net["confidence"], tax["confidence"]), "derivation_verified": True,
                       "reason": f"Rechnungsnetto {net['value']} + {tax['value']} % USt = {gross} {net['currency']} brutto.",
                       "supporting_evidence": [net["evidence"], tax["evidence"]]})
    return output
