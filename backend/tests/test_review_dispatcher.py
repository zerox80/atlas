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
from models import DocumentReviewControl, DocumentReviewItem, DocumentReviewRun
from review_dispatcher import dispatch_reviews, drive_review


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_USE_OCR", "true")
    monkeypatch.setattr(ai_routes, "MISTRAL_DOCUMENT_PROCESSING_ENABLED", True)
    async def scan(section, owner, progress):
        progress("ocr")
        return {page: "SOURCE" for page in range(section.first_page, section.last_page + 1)}
    monkeypatch.setattr(review_worker, "scan_section", scan)
    monkeypatch.setattr(review_worker, "analyze_bundle", AsyncMock(return_value=[extraction([])]))
    limiter.reset()


async def test_server_scans_all_pages_then_analyzes_once_without_browser(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(5)]))
    endpoint = "/ai/reviews/" + auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    dispatcher = asyncio.create_task(dispatch_reviews(session.get_bind()))
    try:
        async with asyncio.timeout(8):
            while auth_client.get(endpoint).json()["remaining"]:
                await asyncio.sleep(.1)
        review_worker.analyze_bundle.assert_awaited_once()
        sections = review_worker.analyze_bundle.call_args.args[0]
        assert [sorted(section.ocr_pages) for section in sections] == [[1, 2, 3, 4], [5]]
        assert not auth_client.get(endpoint).json()["running"]
    finally:
        dispatcher.cancel()
        await asyncio.gather(dispatcher, return_exceptions=True)


async def test_pause_finishes_current_scan_and_preserves_checkpoint(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(5)]))
    started, release = asyncio.Event(), asyncio.Event()
    async def scan(section, owner, progress):
        progress("ocr")
        started.set()
        await release.wait()
        return {page: "SOURCE" for page in range(section.first_page, section.last_page + 1)}
    scan_mock = AsyncMock(side_effect=scan)
    monkeypatch.setattr(review_worker, "scan_section", scan_mock)
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    endpoint = f"/ai/reviews/{run_id}"
    job = asyncio.create_task(drive_review(session.get_bind(), run_id))
    try:
        await asyncio.wait_for(started.wait(), 3)
        auth_client.post(endpoint + "/start")
        await drive_review(session.get_bind(), run_id)
        scan_mock.assert_awaited_once()
        assert auth_client.post(endpoint + "/pause").status_code == 200
    finally:
        release.set()
        await job
    await drive_review(session.get_bind(), run_id)
    first = auth_client.get(endpoint).json()["items"][0]
    assert first["status"] == "pending"
    assert first["result"]["progress"]["ocr_completed_pages"] == 4
    assert first["result"]["progress"]["completed_pages"] == 0
    review_worker.analyze_bundle.assert_not_awaited()
    auth_client.post(endpoint + "/start")
    await drive_review(session.get_bind(), run_id)
    await drive_review(session.get_bind(), run_id)
    assert auth_client.get(endpoint).json()["remaining"] == 0
    assert scan_mock.await_count == 2
    review_worker.analyze_bundle.assert_awaited_once()


async def test_timeout_does_not_stop_remaining_documents(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "first")
    add_document(session, test_user, "second")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    monkeypatch.setattr(review_worker, "analyze_bundle", AsyncMock(side_effect=[TimeoutError(), [extraction([])]]))
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    for _ in range(5):
        await drive_review(session.get_bind(), run_id)
    page = auth_client.get(f"/ai/reviews/{run_id}").json()
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


async def test_worker_heartbeat_during_single_analysis(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "synthetic")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    started, release = asyncio.Event(), asyncio.Event()
    async def analyze(sections, progress):
        progress("analysis")
        started.set()
        await release.wait()
        return [extraction([])]
    monkeypatch.setattr(review_worker, "analyze_bundle", analyze)
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    await drive_review(session.get_bind(), run_id)  # scan
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


async def test_stuck_analysis_times_out_and_releases_lease_without_resplitting(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "stuck")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(4)]))
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    await drive_review(session.get_bind(), run_id)
    monkeypatch.setattr(review_worker, "STEP_TIMEOUT", .1)
    async def analyze(sections, progress):
        progress("analysis")
        await asyncio.sleep(1)
    monkeypatch.setattr(review_worker, "analyze_bundle", analyze)
    await drive_review(session.get_bind(), run_id)
    item = auth_client.get(f"/ai/reviews/{run_id}").json()["items"][0]
    assert item["status"] == "error" and item["result"]["diagnostic"]["code"] == "TIMEOUT"
    assert item["result"]["progress"]["ocr_completed_pages"] == 4
    assert item["result"]["progress"]["total_sections"] == 1
    with Session(session.get_bind()) as fresh:
        assert fresh.get(DocumentReviewRun, run_id).lease_until is None


@pytest.mark.parametrize("single_document", [False, True])
def test_second_active_run_is_rejected_but_existing_run_can_resume(auth_client, session, test_user, single_document):
    document = add_document(session, test_user, "synthetic")
    request = {"start": True, **({"document_id": document.id} if single_document else {})}
    first = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    assert auth_client.post("/ai/reviews", json=request).status_code == 409
    assert auth_client.post(f"/ai/reviews/{first}/start").status_code == 202
    assert auth_client.post(f"/ai/reviews/{first}/pause").status_code == 200
    assert auth_client.post("/ai/reviews", json=request).status_code == 200


async def test_changed_document_during_analysis_cannot_save_suggestions(auth_client, session, test_user, monkeypatch):
    doc = add_document(session, test_user, "changed")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    await drive_review(session.get_bind(), run_id)
    async def analyze(sections, progress):
        progress("analysis")
        doc.version += 1
        session.add(doc)
        session.commit()
        return [extraction([])]
    monkeypatch.setattr(review_worker, "analyze_bundle", analyze)
    await drive_review(session.get_bind(), run_id)
    item = auth_client.get(f"/ai/reviews/{run_id}").json()["items"][0]
    assert item["status"] == "error" and not item["result"]
    assert "geändert" in item["error"]
