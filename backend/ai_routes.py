"""AI document analysis and contract chat routes."""

import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api_core import (
    MISTRAL_DOCUMENT_PROCESSING_ENABLED,
    check_contract_permission,
    get_current_user,
    limiter,
)
from contract_queries import ensure_ai_supported_contract_file
from database import get_session
from file_utils import resolve_file_path, validate_file
from models import Contract, User
from schemas import ChatRequest, ChatResponse, ContractAnalysisResult

router = APIRouter()

@router.post("/contracts/analyze", response_model=ContractAnalysisResult)
@limiter.limit("5/minute")
async def analyze_contract_pdf(
    request: Request,
    file: UploadFile = File(...),
    document_type: Annotated[str, Form()] = "contract",
    current_user: User = Depends(get_current_user)
):
    """
    Analyze a PDF contract using Mistral AI and extract structured data.
    Returns auto-fill suggestions for contract form fields.
    """
    if document_type not in {"contract", "invoice"}:
        raise HTTPException(status_code=422, detail="UngÃ¼ltiger Dokumenttyp.")

    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503, 
            detail="KI-Analyse nicht verfÃ¼gbar. MISTRAL_API_KEY nicht konfiguriert."
        )
    if not MISTRAL_DOCUMENT_PROCESSING_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="KI-Dokumentverarbeitung ist deaktiviert."
        )
    
    # Use consolidated validation
    try:
        mime_type = await validate_file(file)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid file")
        
    if mime_type != "application/pdf":
         raise HTTPException(status_code=400, detail="Nur PDF-Dateien werden unterstÃ¼tzt.")

    # Read full file into memory
    pdf_bytes = await file.read()
    
    try:
        from ai_service import analyze_contract_pdf as analyze_pdf
        result = await analyze_pdf(pdf_bytes, document_type=document_type)
        return ContractAnalysisResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        print(f"[AI ERROR] Contract analysis failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail="KI-Analyse fehlgeschlagen. Bitte versuche es erneut."
        )


@router.post("/contracts/{contract_id}/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat_with_contract(
    contract_id: int,
    chat_req: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Chat with AI about a specific contract.
    Ask questions about contract terms, dates, conditions, etc.
    """
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503, 
            detail="KI-Chat nicht verfÃ¼gbar. MISTRAL_API_KEY nicht konfiguriert."
        )
    if not MISTRAL_DOCUMENT_PROCESSING_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="KI-Dokumentverarbeitung ist deaktiviert."
        )
    
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Vertrag nicht gefunden")
    
    # Check permission
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="Keine Berechtigung fÃ¼r diesen Vertrag")
    ensure_ai_supported_contract_file(contract)
    
    try:
        abs_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vertragsdatei nicht gefunden")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Stored file path is outside the upload directory")
    
    try:
        import aiofiles
        async with aiofiles.open(abs_path, "rb") as f:
            pdf_bytes = await f.read()
        
        from ai_service import chat_about_contract
        answer = await chat_about_contract(pdf_bytes, chat_req.question)
        return ChatResponse(answer=answer)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        print(f"[AI ERROR] Contract chat failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail="KI-Chat fehlgeschlagen. Bitte versuche es erneut."
        )


@router.post("/contracts/{contract_id}/chat/stream")
@limiter.limit("10/minute")
async def chat_with_contract_stream(
    contract_id: int,
    chat_req: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Stream chat responses about a contract using Server-Sent Events.
    Tokens are sent as they arrive for real-time response display.
    """
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503, 
            detail="KI-Chat nicht verfÃ¼gbar. MISTRAL_API_KEY nicht konfiguriert."
        )
    if not MISTRAL_DOCUMENT_PROCESSING_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="KI-Dokumentverarbeitung ist deaktiviert."
        )
    
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Vertrag nicht gefunden")
    
    # Check permission
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="Keine Berechtigung fÃ¼r diesen Vertrag")
    ensure_ai_supported_contract_file(contract)
    
    try:
        abs_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vertragsdatei nicht gefunden")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Stored file path is outside the upload directory")
    
    # Read PDF into memory
    import aiofiles
    async with aiofiles.open(abs_path, "rb") as f:
        pdf_bytes = await f.read()
    
    async def generate_stream():
        """Generate SSE stream from AI response."""
        import json as _json
        try:
            from ai_service import chat_about_contract_stream
            async for chunk in chat_about_contract_stream(pdf_bytes, chat_req.question):
                # JSON-encode chunk to preserve newlines and special chars
                yield f"data: {_json.dumps(chunk)}\n\n"
            # Send done signal
            yield "data: \"[DONE]\"\n\n"
        except Exception as e:
            error_id = str(uuid.uuid4())
            print(f"[AI ERROR] Stream failed ({error_id}): {e}")
            yield f"data: {_json.dumps(f'[ERROR] KI-Chat fehlgeschlagen. Fehler-ID: {error_id}')}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/ai/status")
def get_ai_status(current_user: User = Depends(get_current_user)):
    """Check if AI features are available."""
    has_key = bool(os.getenv("MISTRAL_API_KEY"))
    document_processing_enabled = MISTRAL_DOCUMENT_PROCESSING_ENABLED
    return {
        "available": has_key and document_processing_enabled,
        "model": os.getenv("MISTRAL_CHAT_MODEL", "mistral-medium-3-5") if has_key else None,
        "ocr_model": os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-4-0") if has_key else None,
        "external_document_processing": document_processing_enabled,
        "provider": "Mistral AI" if has_key else None,
        "features": ["contract_analysis", "contract_chat"] if has_key and document_processing_enabled else []
    }

