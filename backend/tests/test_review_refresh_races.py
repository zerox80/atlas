"""Refreshing saved suggestions preserves newer decisions and previous partial saves."""

import json

import pytest
from sqlmodel import Session, col, update
from test_review_refresh import saved_review

import review_refresh
from document_review import snapshot
from models import DocumentReviewItem


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_refresh_returns_concurrent_decision_without_overwriting_it(
    auth_client, session, test_user, monkeypatch, decision,
):
    document, item, url = saved_review(session, test_user)
    original = json.loads(item.result_json)
    decided = {**original, "decision": decision, "decision_at": "2026-09-17T10:00:00+00:00"}
    original_snapshot = snapshot(document)
    build = review_refresh.build_review_result

    def build_after_concurrent_decision(*args, **kwargs):
        # The request has read its old report, then another session saves a decision
        # before the refresh attempts its conditional update.
        with Session(session.get_bind()) as concurrent:
            concurrent.exec(update(DocumentReviewItem).where(
                col(DocumentReviewItem.id) == item.id,
            ).values(result_json=json.dumps(decided)))
            concurrent.commit()
        return build(*args, **kwargs)

    monkeypatch.setattr(review_refresh, "build_review_result", build_after_concurrent_decision)
    response = auth_client.get(url)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["result"] == decided
    session.refresh(item)
    session.refresh(document)
    assert json.loads(item.result_json) == decided
    assert snapshot(document) == original_snapshot


def test_refresh_keeps_previously_applied_old_report_fields_and_remaining_suggestions(
    auth_client, session, test_user,
):
    document, item, url = saved_review(session, test_user)
    old_result = json.loads(item.result_json)
    title_check = next(check for check in old_result["checks"] if check["field"] == "title")
    document.title = title_check["after"]
    document.version += 1
    title_check.update(before=document.title, status="CONFIRMED", can_apply=False, is_conflict=False,
                       reason="Vorschlag durch den Nutzer übernommen.")
    old_result["changes"] = [change for change in old_result["changes"] if change["field"] != "title"]
    old_result["applied_fields"] = ["title"]
    item.result_json = json.dumps(old_result)
    item.snapshot_json = json.dumps(snapshot(document))
    session.add_all([document, item])
    session.commit()

    response = auth_client.get(url)
    assert response.status_code == 200, response.text
    result = response.json()["items"][0]["result"]
    checks = {check["field"]: check for check in result["checks"]}
    assert result["comparison_version"] == 1
    assert result["applied_fields"] == ["title"]
    assert checks["title"]["recommendation"] == "keep" and not checks["title"]["can_apply"]
    assert checks["title"]["before"] == document.title
    assert checks["start_date"]["can_apply"] and checks["value"]["can_apply"]
    session.refresh(document)
    assert document.version == 2 and document.value == 100

    applied = auth_client.post(f"{url}/items/{item.id}/apply", json={"fields": ["start_date"]})
    assert applied.status_code == 200, applied.text
    session.refresh(document)
    assert document.title == "Rechnung mit Wartung" and document.value == 100 and document.version == 3
    assert snapshot(document)["start_date"] == "2024-02-22"
    result = auth_client.get(url).json()["items"][0]["result"]
    assert result["applied_fields"] == ["start_date", "title"]
    assert any(change["field"] == "value" and change["can_apply"] for change in result["changes"])
