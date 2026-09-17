"""Refresh recommendations from saved, verified observations without another AI call."""

import json

from sqlmodel import Session, col, update

from models import Contract, DocumentReviewItem
from review_comparison import build_review_result, result_status
from review_schema import PIPELINE_VERSION, REVIEW_FIELDS


def load_review_result(item: DocumentReviewItem, document: Contract, session: Session) -> tuple[dict, bool]:
    original = item.result_json
    result = json.loads(original or "{}")
    before = json.loads(item.snapshot_json or "{}")
    if (item.status not in {"issues", "hints", "checked", "applied"}
            or result.get("schema_version") != PIPELINE_VERSION
            or result.get("comparison_version") == 1 or result.get("decision")
            or not isinstance(result.get("observations"), list)
            or not set(REVIEW_FIELDS).issubset(before)
            or before.get("version") != document.version):
        return result, False
    # Derived totals are recomputed from their original net/tax observations.
    extraction = {
        "observations": [fact for fact in result["observations"] if not fact.get("derivation_verified")],
        "warnings": result.get("warnings", []),
        "split_proposals": result.get("split_proposals", []),
    }
    refreshed = {**result, **build_review_result(before, [extraction], document.document_type)}
    status = result_status(refreshed)
    if status == "checked" and result.get("applied_fields"):
        status = "applied"
    # A concurrent decision, retry or apply must never be overwritten by a page refresh.
    saved = session.exec(update(DocumentReviewItem).where(
        col(DocumentReviewItem.id) == item.id, col(DocumentReviewItem.result_json) == original,
        col(DocumentReviewItem.snapshot_json) == item.snapshot_json,
        col(DocumentReviewItem.status) == item.status,
    ).values(result_json=json.dumps(refreshed, ensure_ascii=False), status=status)
      .execution_options(synchronize_session=False))
    session.expire(item)
    return json.loads(item.result_json or "{}"), saved.rowcount == 1
