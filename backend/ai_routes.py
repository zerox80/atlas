"""AI document analysis and contract chat routes."""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ai_errors import InvalidStructuredAIResponse
from api_core import (
    MISTRAL_DOCUMENT_PROCESSING_ENABLED,
    check_contract_permission,
    get_current_user,
    limiter,
    user_can_create_documents,
)
from contract_queries import ensure_ai_supported_contract_file
from database import get_session
from file_utils import resolve_file_path, validate_file
from models import Contract, User
from schemas import ChatRequest, ChatResponse, ContractAnalysisResult

router = APIRouter()
logger = logging.getLogger(__name__)

_ANALYSIS_DOCUMENT_TYPES = frozenset({"contract", "invoice"})
_AI_PROCESSING_DISABLED_MESSAGE = "KI-Dokumentverarbeitung ist deaktiviert."
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _require_ai_availability(feature: str) -> None:
    """Reject AI requests when the provider or feature flag is unavailable."""
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail=(
                f"KI-{feature} nicht verfügbar. "
                "MISTRAL_API_KEY nicht konfiguriert."
            ),
        )
    if not MISTRAL_DOCUMENT_PROCESSING_ENABLED:
        raise HTTPException(status_code=403, detail=_AI_PROCESSING_DISABLED_MESSAGE)


async def _read_uploaded_pdf(file: UploadFile) -> bytes:
    """Validate an analysis upload and return its PDF contents."""
    try:
        mime_type = await validate_file(file)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not validate uploaded AI analysis file")
        raise HTTPException(status_code=400, detail="Invalid file") from error

    if mime_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Nur PDF-Dateien werden unterstützt.",
        )

    try:
        return await file.read()
    except (OSError, ValueError) as error:
        logger.warning("Could not read uploaded AI analysis file: %s", error)
        raise HTTPException(
            status_code=400,
            detail="PDF-Datei konnte nicht gelesen werden.",
        ) from error


async def _read_contract_pdf_for_ai(
    contract_id: int,
    current_user: User,
    session: Session,
) -> bytes:
    """Authorize and read a contract file for a chat request."""
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Vertrag nicht gefunden")

    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=404, detail="Vertrag nicht gefunden")
    ensure_ai_supported_contract_file(contract)

    try:
        file_path = resolve_file_path(contract.file_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Vertragsdatei nicht gefunden",
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail="Stored file path is outside the upload directory",
        ) from error

    try:
        async with aiofiles.open(file_path, "rb") as stored_file:
            return await stored_file.read()
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Vertragsdatei nicht gefunden",
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail="Stored file path is outside the upload directory",
        ) from error
    except (OSError, ValueError) as error:
        logger.exception("Could not read contract file %s for AI chat", contract_id)
        raise HTTPException(
            status_code=500,
            detail="Vertragsdatei konnte nicht gelesen werden.",
        ) from error


def _sse_data(payload: str) -> str:
    """Serialize one server-sent event safely, including newlines in payloads."""
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_chat_response(pdf_bytes: bytes, question: str) -> AsyncIterator[str]:
    """Yield chat chunks as server-sent events and convert failures to an event."""
    try:
        from ai_service import chat_about_contract_stream

        async for chunk in chat_about_contract_stream(pdf_bytes, question):
            yield _sse_data(chunk)
        yield _sse_data("[DONE]")
    except Exception:
        error_id = str(uuid.uuid4())
        logger.exception("AI chat stream failed (error_id=%s)", error_id)
        yield _sse_data(
            f"[ERROR] KI-Chat fehlgeschlagen. Fehler-ID: {error_id}"
        )


@router.post("/contracts/analyze", response_model=ContractAnalysisResult)
@limiter.limit("5/minute")
async def analyze_contract_pdf(
    request: Request,
    file: UploadFile = File(...),
    document_type: Annotated[str, Form()] = "contract",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ContractAnalysisResult:
    """Analyze a PDF and return suggestions for a contract or invoice form."""
    if not user_can_create_documents(current_user, session):
        raise HTTPException(status_code=403, detail="No writable workspace available")
    if document_type not in _ANALYSIS_DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Ungültiger Dokumenttyp.")

    _require_ai_availability("Analyse")
    pdf_bytes = await _read_uploaded_pdf(file)

    try:
        from ai_service import analyze_contract_pdf as analyze_pdf

        result = await analyze_pdf(pdf_bytes, document_type=document_type)
        return ContractAnalysisResult(**result)
    except (ValidationError, InvalidStructuredAIResponse):
        logger.warning("AI contract analysis returned invalid structured data")
        raise HTTPException(
            status_code=502,
            detail="KI-Analyse lieferte ungueltige Dokumentdaten.",
        ) from None
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception:
        logger.exception("AI contract analysis failed")
        raise HTTPException(
            status_code=500,
            detail="KI-Analyse fehlgeschlagen. Bitte versuche es erneut.",
        ) from None


@router.post("/contracts/{contract_id}/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat_with_contract(
    contract_id: int,
    chat_request: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChatResponse:
    """Answer a question about an authorized contract using the AI provider."""
    _require_ai_availability("Chat")
    pdf_bytes = await _read_contract_pdf_for_ai(contract_id, current_user, session)

    try:
        from ai_service import chat_about_contract

        answer = await chat_about_contract(pdf_bytes, chat_request.question)
        return ChatResponse(answer=answer)
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception:
        logger.exception("AI chat failed for contract %s", contract_id)
        raise HTTPException(
            status_code=500,
            detail="KI-Chat fehlgeschlagen. Bitte versuche es erneut.",
        ) from None


@router.post("/contracts/{contract_id}/chat/stream")
@limiter.limit("10/minute")
async def chat_with_contract_stream(
    contract_id: int,
    chat_request: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Stream answers about an authorized contract as server-sent events."""
    _require_ai_availability("Chat")
    pdf_bytes = await _read_contract_pdf_for_ai(contract_id, current_user, session)

    return StreamingResponse(
        _stream_chat_response(pdf_bytes, chat_request.question),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/ai/status")
def get_ai_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Return the availability of authenticated AI features."""
    has_key = bool(os.getenv("MISTRAL_API_KEY"))
    document_processing_enabled = MISTRAL_DOCUMENT_PROCESSING_ENABLED
    available = has_key and document_processing_enabled
    return {
        "available": available,
        "model": os.getenv("MISTRAL_CHAT_MODEL", "mistral-medium-3-5") if has_key else None,
        "ocr_model": os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-4-0") if has_key else None,
        "external_document_processing": document_processing_enabled,
        "provider": "Mistral AI" if has_key else None,
        "features": ["contract_analysis", "contract_chat"] if available else [],
    }
