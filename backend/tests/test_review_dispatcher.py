import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlmodel import Session, select
from test_review_pipeline import add_document, pdf_bytes
from test_review_semantics import extraction

import ai_routes
import document_review
import review_analysis
import review_worker
from ai_client import SDKError
from api_core import limiter
from models import DocumentReviewControl, DocumentReviewItem, DocumentReviewRun
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


def model_reply(valid=True):
    payload = {"document_type": "contract", "observations": [], "components": [], "warnings": []} if valid else {}
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(payload)))])


@pytest.mark.parametrize("correction", [True, False])
async def test_each_model_request_gets_full_deadline_and_renews_lease(auth_client, session, test_user, monkeypatch, correction):
    add_document(session, test_user, "deadlines")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    monkeypatch.setattr(review_worker, "STEP_TIMEOUT", .4)
    monkeypatch.setattr(review_analysis, "get_client", lambda: object())
    if not correction:
        monkeypatch.setattr(review_analysis, "text_sections", lambda pages: iter(["first fragment", "second fragment"]))
    async def ocr(*args):
        await asyncio.sleep(.23)
        return "ocr", "## Seite 1\nSOURCE"
    monkeypatch.setattr(review_analysis, "_processed_document_payload", ocr)
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    leases = []
    async def complete(*args, **kwargs):
        with Session(session.get_bind()) as fresh:
            leases.append(fresh.get(DocumentReviewRun, run_id).lease_until)
        await asyncio.sleep(.23)
        return model_reply(not correction or len(leases) > 1)
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    await drive_review(session.get_bind(), run_id)
    item = auth_client.get(f"/ai/reviews/{run_id}").json()["items"][0]
    assert item["status"] == "checked"
    assert item["result"]["progress"]["completed_pages"] == 1
    assert len(leases) == 2 and leases[1] > leases[0]
    with Session(session.get_bind()) as fresh:
        assert fresh.get(DocumentReviewRun, run_id).lease_until is None


async def test_stuck_stage_still_times_out(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "stuck")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(1)]))
    monkeypatch.setattr(review_worker, "STEP_TIMEOUT", .1)
    async def analyze(section, owner, progress):
        progress("analysis")
        await asyncio.sleep(1)
        return [extraction([])]
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    await drive_review(session.get_bind(), run_id)
    item = auth_client.get(f"/ai/reviews/{run_id}").json()["items"][0]
    assert item["status"] == "error"
    assert item["result"]["diagnostic"]["code"] == "TIMEOUT"
    assert item["result"]["progress"]["completed_pages"] == 0


@pytest.mark.parametrize("status", [None, 504])
async def test_split_reuses_persisted_ocr_with_original_pages_and_clears_warning(auth_client, session, test_user, monkeypatch, status):
    add_document(session, test_user, "cached")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(4)]))
    monkeypatch.setattr(review_analysis, "get_client", lambda: object())
    ocr = AsyncMock(return_value=("ocr", "\n".join(f"## Seite {page}\nPRIVATE_SOURCE_{page}" for page in range(1, 5))))
    monkeypatch.setattr(review_analysis, "_processed_document_payload", ocr)
    error = TimeoutError() if status is None else SDKError(
        "PRIVATE_PROVIDER_BODY", httpx.Response(status, request=httpx.Request("POST", "https://api.mistral.ai")), "PRIVATE_RAW_BODY")
    complete = AsyncMock(side_effect=[error, model_reply(), model_reply()])
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    run_id = auth_client.post("/ai/reviews", json={"start": True}).json()["id"]
    endpoint = f"/ai/reviews/{run_id}"
    await drive_review(session.get_bind(), run_id)
    page = auth_client.get(endpoint)
    assert page.json()["items"][0]["result"]["progress"]["retry_message"]
    assert "PRIVATE_SOURCE" not in page.text
    assert "PRIVATE_PROVIDER_BODY" not in page.text and "PRIVATE_RAW_BODY" not in page.text
    if status == 504:
        assert "Anbieter-Zeitlimit (HTTP 504)" in page.json()["items"][0]["result"]["progress"]["retry_message"]
    with Session(session.get_bind()) as fresh:
        item = fresh.exec(select(DocumentReviewItem).where(DocumentReviewItem.run_id == run_id)).one()
        assert set(json.loads(item.result_json)["checkpoint"]["ocr"]["pages"]) == {"1", "2", "3", "4"}
    # Each drive creates a new worker/session, just like a later retry or restart.
    await drive_review(session.get_bind(), run_id)
    item = auth_client.get(endpoint).json()["items"][0]
    assert item["result"]["progress"]["completed_pages"] == 2
    assert "retry_message" not in item["result"]["progress"]
    with Session(session.get_bind()) as fresh:
        item = fresh.exec(select(DocumentReviewItem).where(DocumentReviewItem.run_id == run_id)).one()
        assert set(json.loads(item.result_json)["checkpoint"]["ocr"]["pages"]) == {"3", "4"}
    await drive_review(session.get_bind(), run_id)
    item = auth_client.get(endpoint).json()["items"][0]
    assert item["status"] == "checked"
    assert item["result"]["progress"]["completed_pages"] == 4
    assert ocr.await_count == 1 and complete.await_count == 3
    first_child, second_child = [call.kwargs["messages"][1]["content"] for call in complete.call_args_list[1:]]
    assert "## Seite 1\nPRIVATE_SOURCE_1" in first_child and "PRIVATE_SOURCE_3" not in first_child
    assert "## Seite 3\nPRIVATE_SOURCE_3" in second_child and "PRIVATE_SOURCE_1" not in second_child
