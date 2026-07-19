"""High-level AI analysis and contract chat operations."""

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from typing import Any

from ai_client import (
    AI_REQUEST_TIMEOUT_SECONDS,
    MODEL,
    OCR_MODEL,
    Mistral,
    SDKError,
    complete_chat_with_timeout,
    get_client,
    stream_chunks_with_timeout,
)
from ai_document_processing import (
    build_ocr_options as _build_ocr_options,
    format_ocr_text as _format_ocr_text,
    process_pdf_to_images,
    process_pdf_with_ocr,
    use_ocr_mode,
    validate_pdf_for_ai,
)
from ai_errors import InvalidStructuredAIResponse
from ai_prompts import (
    CONTRACT_ANALYSIS_PROMPT,
    CONTRACT_ANALYSIS_SYSTEM_PROMPT,
    CONTRACT_ASSISTANT_PROMPT,
    INVOICE_ANALYSIS_PROMPT,
    build_contract_question_prompt,
    build_ocr_analysis_prompt,
)


__all__ = [
    "OCR_MODEL",
    "Mistral",
    "SDKError",
    "_build_ocr_options",
    "_format_ocr_text",
    "analyze_contract_pdf",
    "chat_about_contract",
    "chat_about_contract_stream",
]


logger = logging.getLogger(__name__)

DocumentPayload = str | list[str]
_DOCUMENT_CACHE_MAX_ENTRIES = 16
_DOCUMENT_CACHE_MAX_BYTES = 64 * 1024 * 1024
_document_cache: OrderedDict[str, tuple[DocumentPayload, int]] = OrderedDict()
_document_cache_bytes = 0
_document_processing_tasks: dict[str, asyncio.Task[DocumentPayload]] = {}


def _copy_document_payload(payload: DocumentPayload) -> DocumentPayload:
    return payload if isinstance(payload, str) else list(payload)


def _document_payload_size(payload: DocumentPayload) -> int:
    if isinstance(payload, str):
        return len(payload.encode("utf-8"))
    return sum(len(image) for image in payload)


def _cache_document_payload(key: str, payload: DocumentPayload) -> None:
    global _document_cache_bytes

    payload_size = _document_payload_size(payload)
    if payload_size > _DOCUMENT_CACHE_MAX_BYTES:
        return

    previous = _document_cache.pop(key, None)
    if previous is not None:
        _document_cache_bytes -= previous[1]
    _document_cache[key] = (_copy_document_payload(payload), payload_size)
    _document_cache_bytes += payload_size

    while (
        len(_document_cache) > _DOCUMENT_CACHE_MAX_ENTRIES
        or _document_cache_bytes > _DOCUMENT_CACHE_MAX_BYTES
    ):
        _, (_, evicted_size) = _document_cache.popitem(last=False)
        _document_cache_bytes -= evicted_size


async def _process_document_payload(
    pdf_bytes: bytes, processing_mode: str
) -> DocumentPayload:
    if processing_mode == "ocr":
        return await process_pdf_with_ocr(pdf_bytes)
    return await process_pdf_to_images(pdf_bytes)


def _finish_document_processing(
    key: str, task: asyncio.Future[DocumentPayload]
) -> None:
    if _document_processing_tasks.get(key) is task:
        _document_processing_tasks.pop(key, None)
    if task.cancelled():
        return
    try:
        payload = task.result()
    except Exception:
        return
    _cache_document_payload(key, payload)


async def _processed_document_payload(
    pdf_bytes: bytes,
) -> tuple[str, DocumentPayload]:
    processing_mode = "ocr" if use_ocr_mode() else "images"
    processing_options = (
        json.dumps(_build_ocr_options(), sort_keys=True)
        if processing_mode == "ocr"
        else "max_pages=8"
    )
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    cache_key = f"{processing_mode}:{processing_options}:{digest}"

    cached = _document_cache.pop(cache_key, None)
    if cached is not None:
        _document_cache[cache_key] = cached
        return processing_mode, _copy_document_payload(cached[0])

    task = _document_processing_tasks.get(cache_key)
    if task is None:
        task = asyncio.create_task(
            _process_document_payload(pdf_bytes, processing_mode)
        )
        _document_processing_tasks[cache_key] = task
        task.add_done_callback(
            lambda completed, key=cache_key: _finish_document_processing(
                key, completed
            )
        )

    payload = await asyncio.shield(task)
    return processing_mode, _copy_document_payload(payload)


def _parse_analysis_response(response_content: str) -> dict[str, Any]:
    def reject_json_constant(constant: str) -> None:
        raise ValueError(f"Invalid JSON constant: {constant}")

    def parse_json_object(value: str) -> dict[str, Any]:
        parsed = json.loads(value, parse_constant=reject_json_constant)
        if not isinstance(parsed, dict):
            raise InvalidStructuredAIResponse(
                "AI analysis response must be a JSON object"
            )
        return parsed

    try:
        return parse_json_object(response_content)
    except InvalidStructuredAIResponse:
        raise
    except (json.JSONDecodeError, ValueError) as parse_error:
        json_match = re.search(r"\{[\s\S]*\}", response_content)
        if json_match:
            try:
                return parse_json_object(json_match.group())
            except (json.JSONDecodeError, ValueError) as fallback_error:
                raise InvalidStructuredAIResponse(
                    "AI analysis returned invalid structured data"
                ) from fallback_error
        raise InvalidStructuredAIResponse(
            "AI analysis returned invalid structured data"
        ) from parse_error


async def analyze_contract_pdf(
    pdf_bytes: bytes, document_type: str = "contract"
) -> dict:
    """Analyze a PDF and extract structured contract or invoice data."""
    if document_type not in {"contract", "invoice"}:
        raise ValueError("Ungültiger Dokumenttyp.")

    await validate_pdf_for_ai(pdf_bytes)
    client = get_client()
    processing_mode, document_payload = await _processed_document_payload(pdf_bytes)
    if processing_mode == "ocr":
        logger.info("Using OCR mode for contract analysis")
        if not isinstance(document_payload, str):
            raise RuntimeError("Invalid cached OCR payload")
        document_text = document_payload
        if not document_text:
            raise ValueError("OCR konnte keinen Text aus dem PDF extrahieren")
        content = [
            {"type": "text", "text": build_ocr_analysis_prompt(document_text)}
        ]
    else:
        logger.info("Using image mode for contract analysis")
        if isinstance(document_payload, str):
            raise RuntimeError("Invalid cached image payload")
        images_base64 = document_payload
        content = [
            {"type": "image_url", "image_url": image} for image in images_base64
        ]
        content.append({"type": "text", "text": CONTRACT_ANALYSIS_PROMPT})

    if document_type == "invoice":
        content.append({"type": "text", "text": INVOICE_ANALYSIS_PROMPT})

    response = await complete_chat_with_timeout(
        client,
        model=MODEL,
        messages=[
            {"role": "system", "content": CONTRACT_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
    )
    response_content = response.choices[0].message.content
    if not isinstance(response_content, str):
        response_content = "" if response_content is None else str(response_content)
    result = _parse_analysis_response(response_content)

    defaults: dict = {
        "title": None,
        "description": None,
        "value": None,
        "annual_value": None,
        "start_date": None,
        "end_date": None,
        "notice_period": None,
        "tags": [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
    return result


async def _question_content(
    pdf_bytes: bytes, question: str
) -> list[dict[str, str]]:
    processing_mode, document_payload = await _processed_document_payload(pdf_bytes)
    if processing_mode == "ocr":
        if not isinstance(document_payload, str):
            raise RuntimeError("Invalid cached OCR payload")
        document_text = document_payload
        if not document_text:
            raise ValueError("OCR konnte keinen Text aus dem PDF extrahieren.")
        return [
            {
                "type": "text",
                "text": build_contract_question_prompt(document_text, question),
            }
        ]

    if isinstance(document_payload, str):
        raise RuntimeError("Invalid cached image payload")
    images_base64 = document_payload
    content = [
        {"type": "image_url", "image_url": image} for image in images_base64
    ]
    content.append({"type": "text", "text": f"Frage zum Vertrag: {question}"})
    return content


async def chat_about_contract(pdf_bytes: bytes, question: str) -> str:
    """Answer a question about a PDF contract."""
    await validate_pdf_for_ai(pdf_bytes)
    client = get_client()
    logger.info(
        "Using %s mode for contract chat", "OCR" if use_ocr_mode() else "image"
    )
    try:
        content = await _question_content(pdf_bytes, question)
    except ValueError as error:
        if str(error) == "OCR konnte keinen Text aus dem PDF extrahieren.":
            return f"Fehler: {error}"
        raise

    response = await complete_chat_with_timeout(
        client,
        model=MODEL,
        messages=[
            {"role": "system", "content": CONTRACT_ASSISTANT_PROMPT},
            {"role": "user", "content": content},
        ],
    )
    response_content = response.choices[0].message.content
    if not isinstance(response_content, str):
        response_content = "" if response_content is None else str(response_content)
    return response_content


async def chat_about_contract_stream(pdf_bytes: bytes, question: str):
    """Stream an answer about a PDF contract token by token."""
    await validate_pdf_for_ai(pdf_bytes)
    client = get_client()
    logger.info(
        "Using %s mode for contract chat (streaming)",
        "OCR" if use_ocr_mode() else "image",
    )
    try:
        content = await _question_content(pdf_bytes, question)
    except ValueError as error:
        if str(error) == "OCR konnte keinen Text aus dem PDF extrahieren.":
            yield f"Fehler: {error}"
            return
        raise

    stream_response = await asyncio.wait_for(
        client.chat.stream_async(
            model=MODEL,
            messages=[
                {"role": "system", "content": CONTRACT_ASSISTANT_PROMPT},
                {"role": "user", "content": content},
            ],
        ),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
    )
    async for chunk in stream_chunks_with_timeout(stream_response):
        if chunk.data.choices and len(chunk.data.choices) > 0:
            delta = chunk.data.choices[0].delta
            if hasattr(delta, "content") and delta.content:
                yield delta.content
