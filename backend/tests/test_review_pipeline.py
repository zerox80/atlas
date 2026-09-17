import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fitz
import httpx
import pytest
from sqlmodel import select
from test_review_semantics import extraction

import ai_document_processing
import ai_routes
import document_review
import review_analysis
import review_worker
from ai_client import SDKError
from api_core import limiter
from models import Contract, ContractPermission, DocumentReviewItem, DocumentReviewRun
from review_analysis import Section, section_pages, split_documents
from review_errors import error_details


def pdf_bytes(pages):
    with fitz.open() as pdf:
        for index in range(pages):
            page = pdf.new_page()
            page.insert_text((50, 50), f"Seite {index + 1}")
        return pdf.tobytes()


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_USE_OCR", "true")
    monkeypatch.setattr(ai_routes, "MISTRAL_DOCUMENT_PROCESSING_ENABLED", True)
    limiter.reset()


def add_document(session, user, title):
    document = Contract(title=title, file_path=f"uploads/{title}.pdf")
    session.add(document)
    session.flush()
    session.add(ContractPermission(user_id=user.id, contract_id=document.id, permission_level="write"))
    session.commit()
    return document


def test_22_pages_survive_failure_resume_and_other_documents_progress(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "Lang")
    add_document(session, test_user, "Kurz")
    long_pdf, short_pdf = pdf_bytes(22), pdf_bytes(1)
    async def read(paths):
        return [long_pdf if "Lang" in paths[0] else short_pdf]
    calls = []
    failed = False
    async def analyze(section, owner_id, progress):
        nonlocal failed
        progress("ocr")
        progress("analysis")
        calls.append((section.name, section.first_page, section.last_page))
        if section.first_page == 9 and not failed:
            failed = True
            raise TimeoutError("SECRET MODEL CONTENT")
        return [extraction([])]
    monkeypatch.setattr(document_review, "_read_bundle", read)
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    run = auth_client.post("/ai/reviews").json()
    endpoint = f"/ai/reviews/{run['id']}"
    for _ in range(3):
        assert auth_client.post(endpoint + "/next").status_code == 202
    page = auth_client.get(endpoint)
    first = page.json()["items"][0]
    assert first["status"] == "error"
    assert first["result"]["progress"]["completed_pages"] == 8
    assert first["result"]["progress"]["total_pages"] == 22
    assert first["result"]["diagnostic"]["stage"] == "analysis"
    assert first["result"]["diagnostic"]["code"] == "TIMEOUT"
    assert "SECRET" not in page.text and "checkpoint" not in page.text
    auth_client.post(endpoint + "/next")
    assert auth_client.get(endpoint).json()["counts"]["checked"] == 1
    assert auth_client.post(endpoint + "/next").json()["finished"]
    auth_client.post(endpoint + "/retry")
    for _ in range(4):
        auth_client.post(endpoint + "/next")
    page = auth_client.get(endpoint).json()
    assert page["remaining"] == 0 and page["counts"]["checked"] == 2
    assert page["items"][0]["result"]["progress"]["completed_pages"] == 22
    assert [first for name, first, _ in calls if "Lang" in name] == [1, 5, 9, 9, 13, 17, 21]


def test_actual_page_limit_error_includes_setting_count_and_continues(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "22 Seiten")
    monkeypatch.setattr(review_analysis, "MAX_PDF_PAGES", 8)
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(22)]))
    run = auth_client.post("/ai/reviews").json()
    endpoint = f"/ai/reviews/{run['id']}"
    auth_client.post(endpoint + "/next")
    result = auth_client.get(endpoint).json()
    assert result["remaining"] == 0
    item = result["items"][0]
    assert "22 Seiten" in item["error"] and "MISTRAL_MAX_PDF_PAGES=8" in item["error"]
    assert item["result"]["diagnostic"]["code"] == "PAGE_LIMIT"


def test_expired_worker_is_not_restarted_forever(auth_client, session, test_user):
    doc = add_document(session, test_user, "Unterbrochen")
    run = auth_client.post("/ai/reviews").json()
    item = session.exec(select(DocumentReviewItem).where(DocumentReviewItem.contract_id == doc.id)).one()
    item.status = "processing"
    saved = session.get(DocumentReviewRun, run["id"])
    saved.lease_token = "old"
    saved.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    session.add_all([item, saved])
    session.commit()
    endpoint = f"/ai/reviews/{run['id']}"
    assert auth_client.post(endpoint + "/next").json()["interrupted"]
    assert auth_client.get(endpoint).json()["items"][0]["status"] == "error"
    assert auth_client.post(endpoint + "/next").json()["finished"]


def test_ocr_tables_and_blank_pages_are_not_discarded():
    text = ai_document_processing.format_ocr_text({"pages": [
        {"index": 0, "markdown": "Rechnung\n[tbl-0.md](tbl-0.md)", "tables": [
            {"id": "tbl-0.md", "content": "|Upgrade|2.155,28|\n|Maintenance|5.945,46|\n|Gesamt netto|8.195,00|"},
        ], "footer": "Laufzeit bis 25.05.2027"},
        {"index": 1, "markdown": ""},
    ]})
    assert "Maintenance|5.945,46" in text and "Gesamt netto|8.195,00" in text
    assert "[tbl-0.md]" not in text and "## Seite 2" in text and "25.05.2027" in text
    assert set(section_pages(text, Section(1, "x.pdf", 5, 6, b"pdf"))) == {5, 6}


def test_real_22_page_pdf_is_split_without_the_image_limit():
    sections, _ = split_documents([pdf_bytes(22)], ["lang.pdf"])
    assert [(part.first_page, part.last_page) for part in sections] == [(1, 4), (5, 8), (9, 12), (13, 16), (17, 20), (21, 22)]
    for part in sections:
        with fitz.open(stream=part.pdf, filetype="pdf") as pdf:
            assert len(pdf) == part.last_page - part.first_page + 1


async def test_each_document_has_independent_prompt_without_other_contracts(monkeypatch):
    monkeypatch.setattr(review_analysis, "get_client", lambda: object())
    monkeypatch.setattr(review_analysis, "_processed_document_payload", AsyncMock(side_effect=[
        ("ocr", "## Seite 1\nALPHA_UNIQUE_CONTRACT"), ("ocr", "## Seite 1\nBETA_UNIQUE_CONTRACT"),
    ]))
    complete = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
        content=json.dumps({"document_type": "contract", "observations": [], "components": [], "warnings": []}))) ]))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    for name in ("alpha", "beta"):
        await review_analysis.analyze_section(Section(1, name, 1, 1, b"pdf"), 1, lambda stage: None)
    first, second = [call.kwargs["messages"] for call in complete.call_args_list]
    assert [message["role"] for message in second] == ["system", "user"]
    assert "ALPHA_UNIQUE_CONTRACT" in first[1]["content"] and "ALPHA_UNIQUE_CONTRACT" not in str(second)
    assert "BETA_UNIQUE_CONTRACT" in second[1]["content"] and "BETA_UNIQUE_CONTRACT" not in str(first)


def test_provider_diagnostics_preserve_status_without_response_body():
    error = SDKError("SECRET_PROVIDER_BODY", httpx.Response(404, request=httpx.Request("POST", "https://api.mistral.ai")), "SECRET_RAW_BODY")
    diagnostic = error_details(error, "ocr", 300)
    assert diagnostic["code"] == "PROVIDER_HTTP_404" and diagnostic["stage"] == "ocr"
    assert "SECRET" not in json.dumps(diagnostic)


def test_changed_section_size_never_skips_pages_on_resume(auth_client, session, test_user, monkeypatch):
    add_document(session, test_user, "Planwechsel")
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[pdf_bytes(22)]))
    analyze = AsyncMock(return_value=[extraction([])])
    monkeypatch.setattr(review_worker, "analyze_section", analyze)
    endpoint = "/ai/reviews/" + auth_client.post("/ai/reviews").json()["id"]
    auth_client.post(endpoint + "/next")
    monkeypatch.setattr(review_analysis, "SECTION_PAGES", 8)
    auth_client.post(endpoint + "/next")
    item = auth_client.get(endpoint).json()["items"][0]
    assert item["status"] == "error" and item["result"]["diagnostic"]["code"] == "CONFIG_CHANGED"
    assert item["result"]["progress"]["completed_pages"] == 4
    assert analyze.await_count == 1


def test_split_pdfs_are_stable_for_existing_ocr_cache():
    data = pdf_bytes(5)
    first, _ = split_documents([data], ["cache.pdf"])
    second, _ = split_documents([data], ["cache.pdf"])
    assert [part.pdf for part in first] == [part.pdf for part in second]
