import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, select
from test_review_pipeline import add_document, pdf_bytes
from test_review_semantics import extraction

import ai_routes
import document_review
import review_worker
from api_core import limiter
from models import DocumentReviewControl, DocumentReviewItem
from review_dispatcher import dispatch_reviews, drive_review


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_USE_OCR", "true")
    monkeypatch.setattr(ai_routes, "MISTRAL_DOCUMENT_PROCESSING_ENABLED", True)
    limiter.reset()


async def test_server_finishes_all_sections_without_browser_next_requests(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(5)]))
    analyze = AsyncMock(return_value=[extraction([])])
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    endpoint = "/ai/reviews/" + auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    assert auth_client.get(endpoint).json()["running"]
    dispatcher = asyncio.create_task(dispatch_reviews(session.get_bind()))
    try:
        async with asyncio.timeout(8):
            while auth_client.get(endpoint).json()["remaining"]:
                await asyncio.sleep(.1)
        assert analyze.await_count == 2
        assert not auth_client.get(endpoint).json()["running"]
    finally:
        dispatcher.cancel()
        await asyncio.gather(dispatcher, return_exceptions=True)


async def test_pause_finishes_only_current_section_and_resume_preserves_checkpoint(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(5)]))
    started, release = asyncio.Event(), asyncio.Event()
    async def analyze(section, owner, progress):
        progress("analysis")
        started.set()
        await release.wait()
        return [extraction([])]
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    run_id = auth_client.post("/ai/reviews").json()["id"]
    endpoint = f"/ai/reviews/{run_id}"
    auth_client.post(endpoint + "/start")
    job = asyncio.create_task(drive_review(session.get_bind(), run_id))
    try:
        await asyncio.wait_for(started.wait(), 3)
        # Repeated start and another dispatcher must not duplicate paid work.
        auth_client.post(endpoint + "/start")
        await drive_review(session.get_bind(), run_id)
        assert auth_client.post(endpoint + "/pause").status_code == 200
        assert not auth_client.get(endpoint).json()["running"]
    finally:
        release.set()
        await job
    await drive_review(session.get_bind(), run_id)
    first = auth_client.get(endpoint).json()["items"][0]
    assert first["status"] == "pending"
    assert first["result"]["progress"]["completed_pages"] == 4
    assert first["result"]["progress"]["files"] == [{"name": "synthetic.pdf", "pages": 5}]
    assert first["result"]["progress"]["ocr_completed_pages"] == 4
    assert first["result"]["progress"]["heartbeat_at"]
    auth_client.post(endpoint + "/start")
    await drive_review(session.get_bind(), run_id)
    assert auth_client.get(endpoint).json()["remaining"] == 0


async def test_timeout_does_not_stop_remaining_documents(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "first")
    add_document(session, test_user, "second")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    monkeypatch.setattr(review_worker, "analyze_section", AsyncMock(side_effect=[TimeoutError(), [extraction([])]]))
    run_id = auth_client.post("/ai/reviews").json()["id"]
    endpoint = f"/ai/reviews/{run_id}"
    auth_client.post(endpoint + "/start")
    for _ in range(3):
        await drive_review(session.get_bind(), run_id)
    page = auth_client.get(endpoint).json()
    assert page["remaining"] == 0 and page["counts"] == {"checked": 1, "error": 1}
    assert not page["running"]


async def test_running_intent_survives_new_session_and_pause_is_private(auth_client, session, test_user, admin_user):
    from main import app, get_current_user

    run_id = auth_client.post("/ai/reviews").json()["id"]
    endpoint = f"/ai/reviews/{run_id}"
    auth_client.post(endpoint + "/start")
    with Session(session.get_bind()) as fresh:
        assert fresh.get(DocumentReviewControl, run_id).running
    app.dependency_overrides[get_current_user] = lambda: admin_user
    assert auth_client.post(endpoint + "/pause").status_code == 404
    assert auth_client.post(endpoint + "/start").status_code == 404


async def test_worker_reports_heartbeat_while_model_is_waiting(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    started, release = asyncio.Event(), asyncio.Event()
    async def analyze(section, owner, progress):
        progress("analysis")
        started.set()
        await release.wait()
        return [extraction([])]
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    run_id = auth_client.post("/ai/reviews").json()["id"]
    auth_client.post(f"/ai/reviews/{run_id}/start")
    job = asyncio.create_task(drive_review(session.get_bind(), run_id))
    try:
        await asyncio.wait_for(started.wait(), 3)
        def heartbeat():
            with Session(session.get_bind()) as fresh:
                item = fresh.exec(select(DocumentReviewItem).where(DocumentReviewItem.run_id == run_id)).one()
                return json.loads(item.result_json)["progress"]["heartbeat_at"]
        first = heartbeat()
        async with asyncio.timeout(7):
            while heartbeat() == first:
                await asyncio.sleep(.1)
    finally:
        release.set()
        await job


async def test_timeout_subdivides_only_unfinished_pages_and_keeps_the_model(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(8)]))
    calls = []
    async def analyze(section, owner, progress):
        calls.append((section.first_page, section.last_page))
        if section.first_page == 5 and section.last_page == 8:
            raise TimeoutError()
        return [extraction([])]
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    run_id = auth_client.post("/ai/reviews").json()["id"]
    endpoint = f"/ai/reviews/{run_id}"
    auth_client.post(endpoint + "/start")
    for _ in range(2):
        await drive_review(session.get_bind(), run_id)
    item = auth_client.get(endpoint).json()["items"][0]
    assert item["status"] == "pending"
    assert item["result"]["progress"]["stage"] == "retrying"
    assert item["result"]["progress"]["completed_pages"] == 4
    for _ in range(2):
        await drive_review(session.get_bind(), run_id)
    item = auth_client.get(endpoint).json()["items"][0]
    assert item["status"] == "checked"
    assert item["result"]["progress"]["completed_pages"] == 8
    assert item["result"]["model"] == review_worker.MODEL
    assert calls == [(1, 4), (5, 8), (5, 6), (7, 8)]
