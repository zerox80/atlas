"""Storage and authorized downloads for additional contract files."""

import mimetypes
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from api_core import check_contract_permission, get_current_user
from database import get_session
from file_utils import (
    delete_upload_file,
    resolve_file_path,
    save_upload_file,
    validate_file,
)
from models import Contract, ContractAttachment, User
from security_utils import log_audit

router = APIRouter()
MAX_DOCUMENT_FILES = 10


async def validate_attachments(files: list[UploadFile], existing_count: int = 0) -> None:
    if 1 + existing_count + len(files) > MAX_DOCUMENT_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"Pro Dokument sind maximal {MAX_DOCUMENT_FILES} Dateien erlaubt.",
        )
    for file in files:
        await validate_file(file)


async def save_attachments(files: list[UploadFile]) -> list[ContractAttachment]:
    """Stage files; the caller commits their rows or removes the staged files."""
    attachments: list[ContractAttachment] = []
    try:
        for file in files:
            filename = (file.filename or "Anhang").replace("\\", "/").rsplit("/", 1)[-1]
            filename = re.sub(r"[\x00-\x1f\x7f]", "", filename).strip() or "Anhang"
            file.file.seek(0, os.SEEK_END)
            size = file.file.tell()
            await file.seek(0)
            path = await save_upload_file(file)
            attachments.append(ContractAttachment(filename=filename, file_path=path, size=size))
    except Exception:
        for attachment in attachments:
            delete_upload_file(attachment.file_path)
        raise
    return attachments


@router.get("/contracts/{contract_id}/attachments/{attachment_id}/download")
def download_attachment(
    contract_id: int,
    attachment_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if (
        contract is None
        or contract.deleted_at is not None
        or not check_contract_permission(current_user, contract_id, "read", session)
    ):
        raise HTTPException(status_code=404, detail="Document not found")
    attachment = session.get(ContractAttachment, attachment_id)
    if attachment is None or attachment.contract_id != contract_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        path = resolve_file_path(attachment.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found on server") from None
    except PermissionError:
        raise HTTPException(status_code=403, detail="Invalid stored file path") from None

    log_audit(
        session, current_user.id, "DOWNLOAD",
        f"[CID:{contract_id}] Downloaded attachment {attachment.filename}",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"), contract_id=contract_id,
    )
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path)[0] or "application/octet-stream",
        filename=attachment.filename,
    )
