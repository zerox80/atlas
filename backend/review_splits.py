"""Validate independent document proposals against their own source pages."""

from ai_evidence import _normalize
from review_comparison import build_review_result
from review_evidence import verify_extraction
from review_schema import REVIEW_FIELDS, DocumentSuggestion, ReviewExtraction


def verify_suggestions(suggestions: list[DocumentSuggestion], sources: dict, names: dict) -> list[dict]:
    if len(suggestions) < 2:
        return []
    seen: set[tuple[int, int]] = set()
    result = []
    for suggestion in suggestions:
        pages = {(part.document, part.page) for part in suggestion.pages}
        evidence = suggestion.evidence
        if (len(pages) != len(suggestion.pages) or seen & pages
                or any(page not in sources.get(document, {}) for document, page in pages)
                or (evidence.document, evidence.page) not in pages
                or not _normalize(evidence.quote)
                or not suggestion.title.strip()
                or _normalize(evidence.quote) not in _normalize(sources[evidence.document][evidence.page])):
            return []
        seen.update(pages)
        extracts = []
        for document in sorted({document for document, _ in pages}):
            facts = [fact for fact in suggestion.observations if fact.evidence and fact.evidence.document == document]
            selected = {page: sources[document][page] for doc, page in pages if doc == document}
            extracts.append(verify_extraction(ReviewExtraction(document_type=suggestion.document_type,
                            observations=facts, warnings=[]), selected, document, names[document]))
        before = dict.fromkeys(REVIEW_FIELDS)
        before["tags"] = []
        checked = build_review_result(before, extracts, suggestion.document_type)
        values = {change["field"]: change["after"] for change in checked["changes"] if change["can_apply"]}
        # The display title is confirmed by the user; financial/date metadata needs its own evidence.
        values["title"] = suggestion.title
        values.pop("tags", None)
        result.append({"title": suggestion.title, "document_type": suggestion.document_type,
                       "pages": [part.model_dump() for part in suggestion.pages], "reason": suggestion.reason,
                       "evidence": evidence.model_dump(), "values": values, "checks": checked["checks"]})
    return result
