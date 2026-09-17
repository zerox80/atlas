"""Contract creation, update, and download endpoints."""

import logging
import mimetypes
import os
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlmodel import Session, col, update

from api_core import (
    check_contract_permission,
    check_workspace_permission,
    contract_read_for_user,
    get_current_user,
    resolve_user_default_workspace,
)
from contract_endpoints.attachments import save_attachments, validate_attachments
from contract_endpoints.helpers import enforce_upload_rate_limit, resolve_tags
from contract_queries import (
    parse_date_form,
    parse_float_form,
    parse_int_form,
    parse_tags_form,
    validate_contract_form,
)
from contract_queries.forms import validate_cancellation_date
from database import get_session
from file_cleanup import enqueue_file_deletion, process_file_deletion_job
from file_utils import (
    delete_upload_file,
    resolve_file_path,
    save_upload_file,
    validate_file,
)
from models import Contract, ContractAttachment, ContractList, ContractListLink, User
from schemas import ContractCreate, ContractRead, ContractUpdate
from security_utils import log_audit

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/contracts", response_model=ContractRead)
async def create_contract(
    request: Request,
    title: Annotated[str, Form()],
    file: UploadFile = File(...),
    attachments: list[UploadFile] = File(default=[]),
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
    value: Annotated[str | None, Form()] = None,
    annual_value: Annotated[str | None, Form()] = None,
    notice_period: Annotated[str | None, Form()] = "30",
    description: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form(max_length=2_550)] = "",
    document_type: Annotated[str, Form()] = "contract",
    list_id: Annotated[int | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    enforce_upload_rate_limit(request)
    if current_user.id is None:
        raise HTTPException(status_code=403, detail="Document owner could not be resolved")
    target_workspace = (
        session.get(ContractList, list_id)
        if list_id is not None
        else resolve_user_default_workspace(session, current_user)
    )
    if target_workspace is None:
        if list_id is not None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        raise HTTPException(
            status_code=403,
            detail="No writable default workspace is configured",
        )
    if target_workspace.id is None:
        raise RuntimeError("Target workspace has no database ID")
    if (
        target_workspace.is_default
        and target_workspace.owner_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=400,
            detail="A personal Default workspace only accepts its owner's documents",
        )
    if not check_workspace_permission(
        current_user,
        target_workspace.id,
        "write",
        session,
    ):
        raise HTTPException(
            status_code=403,
            detail="You don't have write permission for this workspace",
        )
    parsed_notice_period = parse_int_form(notice_period)
    contract_data = validate_contract_form(
        ContractCreate,
        title=title,
        description=description if description else None,
        start_date=parse_date_form(start_date),
        end_date=parse_date_form(end_date),
        value=parse_float_form(value),
        annual_value=parse_float_form(annual_value),
        notice_period=parsed_notice_period if parsed_notice_period is not None else 30,
        tags=parse_tags_form(tags),
        document_type=document_type,
    )

    validate_cancellation_date(contract_data.end_date, contract_data.notice_period)
    try:
        await validate_file(file)
        await validate_attachments(attachments)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not validate contract upload")
        raise HTTPException(status_code=400, detail="Invalid file") from error

    file_path = await save_upload_file(file)
    contract = Contract(
        owner_user_id=current_user.id,
        title=contract_data.title,
        description=contract_data.description,
        start_date=contract_data.start_date,
        end_date=contract_data.end_date,
        file_path=file_path,
        document_type=contract_data.document_type,
        value=contract_data.value if contract_data.value is not None else 0.0,
        annual_value=contract_data.annual_value,
        notice_period=contract_data.notice_period,
    )

    new_attachments: list[ContractAttachment] = []
    try:
        new_attachments = await save_attachments(attachments)
        contract.attachments.extend(new_attachments)
        contract.tags.extend(
            resolve_tags(
                session,
                contract_data.tags or [],
                allow_create=current_user.role == "admin",
            )
        )
        session.add(contract)
        session.flush()
        if contract.id is None:
            raise RuntimeError("Contract owner could not be assigned")
        session.add(
            ContractListLink(
                contract_id=contract.id,
                list_id=target_workspace.id,
            )
        )
        client_host = request.client.host if request.client else "unknown"
        log_audit(
            session,
            current_user.id,
            "UPLOAD",
            f"[CID:{contract.id}] Uploaded {contract.document_type} {contract.title}",
            client_host,
            request.headers.get("user-agent"),
            contract_id=contract.id,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        delete_upload_file(file_path)
        for attachment in new_attachments:
            delete_upload_file(attachment.file_path)
        raise

    session.refresh(contract)
    return contract_read_for_user(contract, current_user, session)


@router.get("/contracts/{contract_id}", response_model=ContractRead)
def read_contract(
    contract_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return one visible document for deep links and detail dialogs."""
    contract = session.get(Contract, contract_id)
    if contract is None or contract.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=404, detail="Document not found")
    return contract_read_for_user(contract, current_user, session)


@router.get("/contracts/{contract_id}/download")
def download_contract(
    contract_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract or contract.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=404, detail="Contract not found")

    try:
        resolved_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        logger.warning("Contract file is missing on disk: %s", contract.file_path)
        raise HTTPException(status_code=404, detail="File not found on server")
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Stored file path is outside the upload directory",
        )

    client_host = request.client.host if request.client else "unknown"
    log_audit(
        session,
        current_user.id,
        "DOWNLOAD",
        f"[CID:{contract.id}] Downloaded {contract.title}",
        client_host,
        request.headers.get("user-agent"),
        contract_id=contract.id,
    )

    media_type, _ = mimetypes.guess_type(resolved_path)
    _, extension = os.path.splitext(resolved_path)
    if extension.lower() == ".pdf":
        media_type = "application/pdf"
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        resolved_path,
        media_type=media_type,
        filename=f"{contract.title}{extension}",
    )


@router.put("/contracts/{contract_id}", response_model=ContractRead)
async def update_contract(
    contract_id: int,
    request: Request,
    version: Annotated[int, Form(ge=1)],
    title: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
    value: Annotated[str | None, Form()] = None,
    annual_value: Annotated[str | None, Form()] = None,
    notice_period: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form(max_length=2_550)] = None,
    file: UploadFile = File(None),
    attachments: list[UploadFile] = File(default=[]),
    removed_attachment_ids: Annotated[list[int] | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract or contract.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not check_contract_permission(current_user, contract_id, "write", session):
        raise HTTPException(status_code=404, detail="Contract not found")

    expected_version = version
    if expected_version != contract.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract was changed by another request; reload and retry",
        )
    session.autoflush = False
    removed_ids = set(removed_attachment_ids or [])
    removed_attachments = [item for item in contract.attachments if item.id in removed_ids]
    if len(removed_attachments) != len(removed_ids):
        raise HTTPException(status_code=404, detail="Attachment not found")
    await validate_attachments(
        attachments, len(contract.attachments) - len(removed_attachments),
    )

    update_data = validate_contract_form(
        ContractUpdate,
        title=title,
        description=description if description else None,
        start_date=parse_date_form(start_date),
        end_date=parse_date_form(end_date),
        value=parse_float_form(value),
        annual_value=parse_float_form(annual_value),
        notice_period=parse_int_form(notice_period),
        tags=parse_tags_form(tags) if tags is not None else None,
    )
    if end_date is not None or notice_period is not None:
        validate_cancellation_date(
            update_data.end_date if end_date is not None else contract.end_date,
            (
                update_data.notice_period
                if notice_period is not None
                else contract.notice_period
            ),
        )
    changes: list[str] = []

    def check_and_update(field_name, new_value, provided):
        if provided:
            old_value = getattr(contract, field_name)
            if old_value != new_value:
                changes.append(f"{field_name}: '{old_value}' -> '{new_value}'")
                setattr(contract, field_name, new_value)

    check_and_update("title", update_data.title, title is not None)
    check_and_update("description", update_data.description, description is not None)
    check_and_update("start_date", update_data.start_date, start_date is not None)
    check_and_update("end_date", update_data.end_date, end_date is not None)
    check_and_update(
        "value",
        update_data.value if update_data.value is not None else 0.0,
        value is not None,
    )
    check_and_update("annual_value", update_data.annual_value, annual_value is not None)
    check_and_update("notice_period", update_data.notice_period, notice_period is not None)

    new_file_path: str | None = None
    old_file_path: str | None = None
    deletion_job_ids: list[int] = []
    if file or attachments:
        enforce_upload_rate_limit(request)
    if file:
        try:
            await validate_file(file)
            new_file_path = await save_upload_file(
                file,
                replaced_file_path=contract.file_path,
            )
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("Could not replace file for contract %s", contract_id)
            raise HTTPException(status_code=500, detail="File upload failed") from error
        old_file_path = contract.file_path
        contract.file_path = new_file_path
        changes.append("file: updated")

    new_attachments: list[ContractAttachment] = []
    try:
        new_attachments = await save_attachments(attachments)
        contract.attachments.extend(new_attachments)
        if new_attachments:
            changes.append(f"attachments: added {len(new_attachments)}")
        for attachment in removed_attachments:
            job = enqueue_file_deletion(session, attachment.file_path)
            if job is not None and job.id is not None:
                deletion_job_ids.append(job.id)
            session.delete(attachment)
        if removed_attachments:
            changes.append(f"attachments: removed {len(removed_attachments)}")
        if tags is not None:
            old_tags = [tag.name for tag in contract.tags]
            new_tags = update_data.tags or []
            if set(old_tags) != set(new_tags):
                changes.append(f"tags: {old_tags} -> {new_tags}")
                contract.tags = resolve_tags(
                    session,
                    new_tags,
                    allow_create=current_user.role == "admin",
                )

        if changes:
            claim_result = session.exec(
                update(Contract)
                .where(
                    col(Contract.id) == contract_id,
                    col(Contract.version) == expected_version,
                )
                .values(version=expected_version + 1)
                .execution_options(synchronize_session=False)
            )
            if claim_result.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Contract was changed by another request; reload and retry",
                )
            contract.version = expected_version + 1
            session.add(contract)
            log_audit(
                session,
                current_user.id,
                "UPDATE_CONTRACT",
                f"[CID:{contract_id}] Updated Contract. Changes: {'; '.join(changes)}",
                request.client.host if request.client else "unknown",
                request.headers.get("user-agent"),
                contract_id=contract_id,
                commit=False,
            )
            if old_file_path and old_file_path != contract.file_path:
                deletion_job = enqueue_file_deletion(session, old_file_path)
                if deletion_job is None or deletion_job.id is None:
                    raise RuntimeError("File cleanup job could not be created")
                deletion_job_ids.append(deletion_job.id)
            session.commit()
    except Exception:
        session.rollback()
        if new_file_path:
            delete_upload_file(new_file_path)
        for attachment in new_attachments:
            delete_upload_file(attachment.file_path)
        raise

    if changes:
        session.refresh(contract)
    response_payload = contract_read_for_user(contract, current_user, session)
    for deletion_job_id in deletion_job_ids:
        process_file_deletion_job(session, deletion_job_id)

    return response_payload
