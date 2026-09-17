"""Conservative verification of cancellation periods against source text."""

import re
import unicodedata

_NUMBERS = {"null": 0, "ein": 1, "eine": 1, "einer": 1, "einen": 1,
            "einem": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4,
            "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
            "zehn": 10, "elf": 11, "zwölf": 12, "vierzehn": 14,
            "dreißig": 30, "dreissig": 30}
_DURATION = re.compile(
    r"\b(\d+|" + "|".join(_NUMBERS) + r")\s*(?:\(\d+\)\s*)?(tage?[ns]?|wochen?)\b"
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def enforce_notice_evidence(result: dict, document_text: str | None) -> dict:
    """Accept only an exact source quote with an unambiguous day/week duration.

    This verifies provenance and units, not the legal applicability of a clause.
    Image-only inputs cannot provide verifiable textual provenance.
    """
    days = result.get("notice_period")
    quote = result.get("notice_period_evidence")
    normalized = _normalize(quote) if isinstance(quote, str) else ""
    verified_quote = bool(
        normalized and document_text and normalized in _normalize(document_text)
    )
    if not verified_quote:
        result["notice_period_evidence"] = None
    if days is None:
        return result
    candidates = set()
    for number, unit in _DURATION.findall(normalized):
        count = int(number) if number.isdigit() else _NUMBERS[number]
        candidates.add(count * (7 if unit.startswith("woche") else 1))
    if re.search(r"ohne (?:eine )?kündigungsfrist", normalized):
        candidates.add(0)
    valid = (
        verified_quote
        and type(days) is int
        and 0 <= days <= 36_500
        and candidates == {days}
        and "kündig" in normalized
        and not re.search(
            r"\b(monat\w*|jahr\w*|widerruf\w*|ausserordentlich\w*|sonderkündig\w*|"
            r"fristlos\w*|zahlungsfrist\w*|fällig\w*|nicht|keine?)\b|zu zahlen",
            normalized,
        )
    )
    if not valid:
        result["notice_period"] = None
        warnings = result.get("analysis_warnings")
        if not isinstance(warnings, list):
            warnings = []
        result["analysis_warnings"] = [
            "Kündigungsfrist nicht eindeutig mit einer Textstelle in Tagen belegt; Feld bleibt leer.",
            *warnings[:19],
        ]
    return result
