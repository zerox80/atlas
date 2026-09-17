"""Saved reports expose actionable suggestions and only selected values are written."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from test_review_semantics import extraction, observation

import review_worker
from document_review import snapshot
from models import Contract, ContractPermission, DocumentReviewItem, DocumentReviewRun
from review_comparison import build_review_result


def saved_review(session, user):
    document = Contract(title="Alt", file_path="uploads/test.pdf", document_type="invoice",
                        owner_user_id=user.id, start_date=datetime(2020, 1, 1, tzinfo=UTC), value=100)
    session.add(document)
    session.flush()
    session.add(ContractPermission(user_id=user.id, contract_id=document.id, permission_level="write"))
    before = snapshot(document)
    facts = extraction([
        observation("title", "Rechnung mit Wartung", "Rechnung mit Wartung", kind="derived"),
        observation("invoice_date", "2024-02-22", "Rechnungsdatum: 22.02.2024"),
        observation("invoice_total_gross", 119, "Gesamt brutto: 119,00 EUR", currency="EUR", confidence=0.6),
    ])
    result = build_review_result(before, [facts], "invoice")
    # Emulate the saved v3 report from before recommendations were introduced.
    result.pop("comparison_version", None)
    result.update(model="saved-model", source_fingerprint="saved-fingerprint", checked_files=1)
    for check in result["checks"]:
        check.pop("recommendation", None)
        check.pop("recommendation_reason", None)
        if check["field"] in {"start_date", "value"}:
            check.update(can_apply=False, status="AMBIGUOUS", reason="Bisherige pauschale Sperre.")
    run = DocumentReviewRun(owner_subject=user.auth_subject, model="saved-model")
    session.add(run)
    session.flush()
    item = DocumentReviewItem(run_id=run.id, contract_id=document.id, status="issues",
                              snapshot_json=json.dumps(before), result_json=json.dumps(result))
    session.add(item)
    session.commit()
    return document, item, f"/ai/reviews/{run.id}"


def test_read_refreshes_existing_report_once_without_ai_or_contract_changes(auth_client, session, test_user, monkeypatch):
    document, item, url = saved_review(session, test_user)
    analyze = AsyncMock()
    monkeypatch.setattr(review_worker, "analyze_bundle", analyze)
    first = auth_client.get(url)
    assert first.status_code == 200
    result = first.json()["items"][0]["result"]
    checks = {check["field"]: check for check in result["checks"]}
    assert result["comparison_version"] == 1
    assert checks["start_date"]["recommendation"] == "update"
    assert checks["value"]["can_apply"]
    assert result["source_fingerprint"] == "saved-fingerprint"
    assert result["model"] == "saved-model" and result["checked_files"] == 1
    assert auth_client.get(url).json()["items"][0]["result"] == result
    session.refresh(item)
    session.refresh(document)
    assert json.loads(item.result_json) == result
    assert document.title == "Alt" and document.value == 100 and document.version == 1
    analyze.assert_not_awaited()


def test_apply_refreshes_and_writes_only_selected_date_with_serializable_report(auth_client, session, test_user):
    document, item, url = saved_review(session, test_user)
    response = auth_client.post(f"{url}/items/{item.id}/apply", json={"fields": ["start_date"]})
    assert response.status_code == 200, response.text
    session.refresh(document)
    assert snapshot(document)["start_date"] == "2024-02-22"
    assert document.title == "Alt" and document.value == 100 and document.version == 2
    result = auth_client.get(url).json()["items"][0]["result"]
    assert "start_date" not in {change["field"] for change in result["changes"]}
    applied = next(check for check in result["checks"] if check["field"] == "start_date")
    assert applied["before"] == "2024-02-22" and applied["recommendation"] == "keep"
    assert not applied["can_apply"]
    assert any(change["field"] == "value" and change["can_apply"] for change in result["changes"])
    assert auth_client.post(f"{url}/items/{item.id}/apply", json={"fields": ["value"]}).status_code == 200
    session.refresh(document)
    assert document.value == 119 and document.title == "Alt"


@pytest.mark.parametrize("unchanged", ["accepted", "rejected", "legacy", "changed_document"])
def test_refresh_preserves_decisions_legacy_and_changed_documents(auth_client, session, test_user, unchanged):
    document, item, url = saved_review(session, test_user)
    result = json.loads(item.result_json)
    if unchanged in {"accepted", "rejected"}:
        result["decision"] = unchanged
    elif unchanged == "legacy":
        result["schema_version"] = 2
    else:
        document.version += 1
        session.add(document)
    item.result_json = json.dumps(result)
    session.add(item)
    session.commit()
    response = auth_client.get(url)
    assert response.status_code == 200
    session.refresh(item)
    assert json.loads(item.result_json) == result
    assert "comparison_version" not in response.json()["items"][0]["result"]
