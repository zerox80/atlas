"""
Tests for the Mistral AI service helpers.
"""
import asyncio
import importlib
from types import SimpleNamespace

import pytest

from ai_errors import AIProcessingCapacityError


def test_ocr_4_is_default_model(monkeypatch):
    monkeypatch.delenv("MISTRAL_OCR_MODEL", raising=False)

    import ai_service

    service = importlib.reload(ai_service)

    assert service.OCR_MODEL == "mistral-ocr-4-0"


def test_medium_3_5_is_default_chat_model(monkeypatch):
    monkeypatch.delenv("MISTRAL_CHAT_MODEL", raising=False)

    import ai_service

    service = importlib.reload(ai_service)

    assert service.MODEL == "mistral-medium-3-5"


def test_imports_current_mistral_client():
    import ai_service

    assert ai_service.Mistral is not None
    assert ai_service.SDKError is not None


def test_build_ocr_options_enable_ocr_4_features(monkeypatch):
    monkeypatch.setenv("MISTRAL_OCR_MODEL", "mistral-ocr-4-0")
    monkeypatch.setenv("MISTRAL_OCR_TABLE_FORMAT", "markdown")
    monkeypatch.setenv("MISTRAL_OCR_INCLUDE_BLOCKS", "true")
    monkeypatch.setenv("MISTRAL_OCR_CONFIDENCE_GRANULARITY", "page")

    import ai_service

    service = importlib.reload(ai_service)

    assert service._build_ocr_options() == {
        "model": "mistral-ocr-4-0",
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
    }


def test_format_ocr_text_includes_pages_confidence_and_blocks():
    import ai_service

    ocr_response = SimpleNamespace(
        pages=[
            SimpleNamespace(
                index=0,
                markdown="Vertragstext",
                confidence_scores=SimpleNamespace(
                    average_page_confidence_score=0.97,
                    minimum_page_confidence_score=0.91,
                ),
                blocks=[
                    SimpleNamespace(type="title", content="Rahmenvertrag"),
                    SimpleNamespace(type="signature", content="Max Mustermann"),
                ],
            )
        ]
    )

    text = ai_service._format_ocr_text(ocr_response)

    assert "## Seite 1" in text
    assert "Vertragstext" in text
    assert "OCR-Konfidenz: average=0.97, minimum=0.91" in text
    assert "- title: Rahmenvertrag" in text
    assert "- signature: Max Mustermann" in text


async def test_pending_document_work_is_bounded_and_deduplicated(monkeypatch):
    import ai_service

    service = importlib.reload(ai_service)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def process_document(pdf_bytes, processing_mode):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "processed"

    monkeypatch.setattr(service, "_DOCUMENT_PROCESSING_MAX_TASKS", 1)
    monkeypatch.setattr(service, "_DOCUMENT_PROCESSING_MAX_BYTES", 1024)
    monkeypatch.setattr(
        service, "_DOCUMENT_PROCESSING_MAX_BYTES_PER_USER", 1024
    )
    monkeypatch.setattr(service, "use_ocr_mode", lambda: True)
    monkeypatch.setattr(service, "_build_ocr_options", dict)
    monkeypatch.setattr(service, "_process_document_payload", process_document)

    first = asyncio.create_task(
        service._processed_document_payload(b"first", owner_id=1)
    )
    await started.wait()
    duplicate = asyncio.create_task(
        service._processed_document_payload(b"first", owner_id=1)
    )
    await asyncio.sleep(0)

    with pytest.raises(AIProcessingCapacityError):
        await service._processed_document_payload(b"second", owner_id=2)

    release.set()
    assert await asyncio.gather(first, duplicate) == [
        ("ocr", "processed"),
        ("ocr", "processed"),
    ]
    await asyncio.sleep(0)

    assert calls == 1
    assert service._document_processing_tasks == {}
    assert service._document_processing_bytes == 0
    assert service._document_processing_bytes_by_user == {}


async def test_pending_document_work_enforces_byte_budgets(monkeypatch):
    import ai_service

    service = importlib.reload(ai_service)
    first_started = asyncio.Event()
    both_started = asyncio.Event()
    release = asyncio.Event()
    started_documents = []

    async def process_document(pdf_bytes, processing_mode):
        started_documents.append(pdf_bytes)
        first_started.set()
        if len(started_documents) == 2:
            both_started.set()
        await release.wait()
        return pdf_bytes.decode()

    monkeypatch.setattr(service, "_DOCUMENT_PROCESSING_MAX_TASKS", 3)
    monkeypatch.setattr(service, "_DOCUMENT_PROCESSING_MAX_BYTES", 6)
    monkeypatch.setattr(
        service, "_DOCUMENT_PROCESSING_MAX_BYTES_PER_USER", 4
    )
    monkeypatch.setattr(service, "use_ocr_mode", lambda: True)
    monkeypatch.setattr(service, "_build_ocr_options", dict)
    monkeypatch.setattr(service, "_process_document_payload", process_document)

    first = asyncio.create_task(
        service._processed_document_payload(b"1234", owner_id=1)
    )
    await first_started.wait()

    with pytest.raises(AIProcessingCapacityError):
        await service._processed_document_payload(b"x", owner_id=1)

    second = asyncio.create_task(
        service._processed_document_payload(b"12", owner_id=2)
    )
    await both_started.wait()

    with pytest.raises(AIProcessingCapacityError):
        await service._processed_document_payload(b"x", owner_id=3)

    assert service._document_processing_bytes == 6
    assert service._document_processing_bytes_by_user == {1: 4, 2: 2}

    release.set()
    assert await asyncio.gather(first, second) == [
        ("ocr", "1234"),
        ("ocr", "12"),
    ]
    await asyncio.sleep(0)

    assert service._document_processing_tasks == {}
    assert service._document_processing_bytes == 0
    assert service._document_processing_bytes_by_user == {}


async def test_document_processing_is_cancelled_without_waiters(monkeypatch):
    import ai_service

    service = importlib.reload(ai_service)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def process_document(pdf_bytes, processing_mode):
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    monkeypatch.setattr(service, "use_ocr_mode", lambda: True)
    monkeypatch.setattr(service, "_build_ocr_options", dict)
    monkeypatch.setattr(service, "_process_document_payload", process_document)

    caller = asyncio.create_task(
        service._processed_document_payload(b"document", owner_id=1)
    )
    await started.wait()
    caller.cancel()

    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.wait_for(stopped.wait(), timeout=1)
    await asyncio.sleep(0)

    assert service._document_processing_tasks == {}
    assert service._document_processing_bytes == 0
    assert service._document_processing_bytes_by_user == {}
