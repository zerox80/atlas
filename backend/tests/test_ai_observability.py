"""Observable provider waits must preserve deadlines, cancellation, and privacy."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import ai_client
import ai_document_processing
import ai_observability
from ai_observability import observed_request, review_context


async def test_pending_request_logs_then_returns_response(monkeypatch, caplog):
    monkeypatch.setattr(ai_observability, "WAIT_LOG_INTERVAL", 0.001)
    token = review_context.set("run=test-run item=7")
    response = object()

    async def delayed():
        await asyncio.sleep(0.02)
        return response

    try:
        assert await observed_request(delayed(), operation="chat", model="zai-glm-5-3", timeout=1) is response
    finally:
        review_context.reset(token)
    messages = [record.message for record in caplog.records if record.name == "atlas.ai"]
    assert "request started" in messages[0]
    assert "waiting for response" in messages[1]
    assert "response received" in messages[-1]
    assert all("run=test-run item=7" in message for message in messages)
    assert all("model=zai-glm-5-3" in message for message in messages)
    assert review_context.get() == "review=-"


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_and_cancellation_stop_request_and_monitor(cancel, caplog):
    active_before = asyncio.all_tasks()
    started, stopped = asyncio.Event(), asyncio.Event()

    async def pending():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    task = asyncio.create_task(observed_request(
        pending(), operation="ocr", model="mistral-ocr-4-1", timeout=1 if cancel else 0.01,
    ))
    await started.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert stopped.is_set()
    assert asyncio.all_tasks() == active_before
    expected = "request cancelled" if cancel else "error_type=TimeoutError"
    assert expected in caplog.text
    assert "response received" not in caplog.text


async def test_provider_failure_logs_status_without_body_or_credentials(caplog):
    class ProviderError(Exception):
        status_code = 504

    error = ProviderError("SECRET_API_KEY private contract text")

    async def failed():
        raise error

    with pytest.raises(ProviderError) as caught:
        await observed_request(failed(), operation="chat", model="zai-glm-5-3", timeout=1)
    assert caught.value is error
    assert "http_status=504" in caplog.text
    assert "error_type=ProviderError" in caplog.text
    assert "SECRET_API_KEY" not in caplog.text and "private contract text" not in caplog.text
    assert "response received" not in caplog.text


async def test_chat_wrapper_preserves_request_and_logs_completion(caplog):
    response = object()
    complete = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(complete_async=complete))
    kwargs = {"model": "zai-glm-5-3", "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}]}
    assert await ai_client.complete_chat_with_timeout(client, **kwargs) is response
    complete.assert_awaited_once_with(**kwargs)
    assert "operation=chat" in caplog.text and "response received" in caplog.text
    assert "PRIVATE_PROMPT" not in caplog.text


@pytest.mark.parametrize("finish_reason, expected", [("length", "length"), ("PRIVATE_STATUS\nforged", "unknown")])
async def test_response_metadata_is_useful_without_logging_provider_content(caplog, finish_reason, expected):
    response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish_reason, message="PRIVATE_ANSWER")],
        usage=SimpleNamespace(prompt_tokens=150, completion_tokens=4000, total_tokens="PRIVATE_USAGE"),
    )
    result = await observed_request(AsyncMock(return_value=response)(), operation="chat", model="test", timeout=1)
    assert result is response
    assert f"finish_reason={expected}" in caplog.text
    assert "prompt_tokens=150 completion_tokens=4000 total_tokens=-" in caplog.text
    assert "PRIVATE" not in caplog.text and "forged" not in caplog.text


async def test_ocr_wrapper_logs_without_pdf_or_ocr_content(monkeypatch, caplog):
    process = AsyncMock(return_value={"pages": [{"index": 0, "markdown": "PRIVATE_OCR"}]})
    monkeypatch.setattr(ai_document_processing, "get_client", lambda: SimpleNamespace(ocr=SimpleNamespace(process_async=process)))
    assert "PRIVATE_OCR" in await ai_document_processing.process_pdf_with_ocr(b"PRIVATE_PDF")
    process.assert_awaited_once()
    assert "operation=ocr" in caplog.text and "response received" in caplog.text
    assert "PRIVATE_OCR" not in caplog.text and "PRIVATE_PDF" not in caplog.text
    assert "document_url" not in caplog.text


def test_logging_setup_is_idempotent_and_emits_info_to_stderr(capsys):
    application = logging.getLogger("atlas")
    handlers = application.handlers[:]
    try:
        application.handlers.clear()
        ai_observability.configure_ai_logging()
        ai_observability.configure_ai_logging()
        logging.getLogger("atlas.ai").info("visible-in-docker")
        assert capsys.readouterr().err.count("visible-in-docker") == 1
    finally:
        for handler in application.handlers:
            handler.close()
        application.handlers[:] = handlers
