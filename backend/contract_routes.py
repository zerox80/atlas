"""Contract creation, update, download, deletion, and protection routes."""

import logging
import mimetypes
import os
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from limits import parse
from sqlalchemy.exc import IntegrityError
from slowapi.util import get_remote_address
from sqlmodel import Session, col, delete, select, update

from api_core import (
    check_contract_permission,
    contract_read_for_user,
    get_current_user,
    limiter,
)
from contract_queries import (
    parse_date_form,
    parse_float_form,
    parse_int_form,
    parse_tags_form,
    validate_contract_form,
)
from database import get_session
from file_utils import delete_upload_file, resolve_file_path, save_upload_file, validate_file
from models import Contract, ContractListLink, ContractPermission, ContractTagLink, Tag, User
from schemas import ContractCreate, ContractRead, ContractUpdate
from security_utils import log_audit

router = APIRouter()
logger = logging.getLogger(__name__)
UPLOAD_RATE_LIMIT = os.getenv("RATE_LIMIT_UPLOAD", "20/hour")
UPLOAD_RATE_ITEM = parse(UPLOAD_RATE_LIMIT)


def _enforce_upload_rate_limit(request: Request) -> None:
    """Consume one shared upload quota unit for the trusted client address."""
    client_address = get_remote_address(request)
    if not limiter.limiter.hit(
        UPLOAD_RATE_ITEM,
        client_address,
        "contract-upload",
    ):
        raise HTTPException(status_code=429, detail="Upload rate limit exceeded")

def _resolve_tags(session: Session, tag_names: list[str]) -> list[Tag]:
    """Resolve tags without committing the caller's transaction."""
    unique_names = list(dict.fromkeys(tag_names))
    if not unique_names:
        return []

    existing = session.exec(select(Tag).where(col(Tag.name).in_(unique_names))).all()
    tags_by_name = {tag.name: tag for tag in existing}

    for tag_name in unique_names:
        if tag_name in tags_by_name:
            continue
        try:
            with session.begin_nested():
                tag = Tag(name=tag_name)
                session.add(tag)
                session.flush()
            tags_by_name[tag_name] = tag
        except IntegrityError:
            tag = session.exec(select(Tag).where(Tag.name == tag_name)).first()
            if tag is None:
                raise
            tags_by_name[tag_name] = tag

    return [tags_by_name[name] for name in unique_names]

@router.post("/contracts", response_model=ContractRead)
async def create_contract(
    request: Request,
    title: Annotated[str, Form()],
    file: UploadFile = File(...),
    start_date: Annotated[Optional[str], Form()] = None,
    end_date: Annotated[Optional[str], Form()] = None,
    value: Annotated[Optional[str], Form()] = None,
    annual_value: Annotated[Optional[str], Form()] = None,
    notice_period: Annotated[Optional[str], Form()] = "30",
    description: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form(max_length=2_550)] = "",
    document_type: Annotated[str, Form()] = "contract",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    _enforce_upload_rate_limit(request)
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

    # Validate before persisting an upload. ``validate_file`` already returns
    # client-safe HTTP errors for expected validation failures.
    try:
        await validate_file(file)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not validate contract upload")
        raise HTTPException(status_code=400, detail="Invalid file") from error

    file_path = await save_upload_file(file)
        
    contract = Contract(
        title=contract_data.title,
        description=contract_data.description,
        start_date=contract_data.start_date,
        end_date=contract_data.end_date,
        file_path=file_path,
        document_type=contract_data.document_type,
        value=contract_data.value if contract_data.value is not None else 0.0,
        annual_value=contract_data.annual_value,
        notice_period=contract_data.notice_period
    )
    
    try:
        contract.tags.extend(_resolve_tags(session, contract_data.tags or []))
        session.add(contract)
        session.flush()
        if current_user.id is None or contract.id is None:
            raise RuntimeError("Contract owner could not be assigned")
        session.add(ContractPermission(
            user_id=current_user.id,
            contract_id=contract.id,
            permission_level="full"
        ))
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
        raise

    # A refresh failure after a successful commit must never delete the file
    # that the committed row now references.
    session.refresh(contract)
    return contract_read_for_user(contract, current_user, session)

@router.get("/contracts/{contract_id}/download")
def download_contract(
    contract_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="You don't have permission to access this contract")
        
    try:
        resolved_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        logger.warning("Contract file is missing on disk: %s", contract.file_path)
        raise HTTPException(status_code=404, detail="File not found on server")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Stored file path is outside the upload directory")

    # Standard download
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
    
    # Determine basic mime types to avoid browser confusion
    media_type, _ = mimetypes.guess_type(resolved_path)
    
    # Check explicitly for pdf to be sure
    _, ext = os.path.splitext(resolved_path)
    if ext.lower() == ".pdf":
        media_type = "application/pdf"
        
    if not media_type:
        media_type = "application/octet-stream"
        
    # Ensure extension is in filename
    filename = f"{contract.title}{ext}"
    
    return FileResponse(resolved_path, media_type=media_type, filename=filename)

@router.put("/contracts/{contract_id}", response_model=ContractRead)
async def update_contract(
    contract_id: int, 
    request: Request,
    version: Annotated[int, Form(ge=1)],
    title: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
    start_date: Annotated[Optional[str], Form()] = None,
    end_date: Annotated[Optional[str], Form()] = None,
    value: Annotated[Optional[str], Form()] = None,
    annual_value: Annotated[Optional[str], Form()] = None,
    notice_period: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form(max_length=2_550)] = None,
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission (need at least "write" level)
    if not check_contract_permission(current_user, contract_id, "write", session):
        raise HTTPException(status_code=403, detail="You don't have permission to edit this contract")

    expected_version = version
    if expected_version != contract.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract was changed by another request; reload and retry",
        )
    session.autoflush = False

    parsed_value = parse_float_form(value)
    update_data = validate_contract_form(
        ContractUpdate,
        title=title,
        description=description if description else None,
        start_date=parse_date_form(start_date),
        end_date=parse_date_form(end_date),
        value=parsed_value,
        annual_value=parse_float_form(annual_value),
        notice_period=parse_int_form(notice_period),
        tags=parse_tags_form(tags) if tags is not None else None,
    )

    changes: list[str] = []
    
    # helper to check and update
    def check_and_update(field_name, new_val, provided):
        if provided:
            old_val = getattr(contract, field_name)
            if old_val != new_val:
                changes.append(f"{field_name}: '{old_val}' -> '{new_val}'")
                setattr(contract, field_name, new_val)

    check_and_update("title", update_data.title, title is not None)
    check_and_update("description", update_data.description, description is not None)
    check_and_update("start_date", update_data.start_date, start_date is not None)
    check_and_update("end_date", update_data.end_date, end_date is not None)
    check_and_update("value", update_data.value if update_data.value is not None else 0.0, value is not None)
    check_and_update("annual_value", update_data.annual_value, annual_value is not None)
    check_and_update("notice_period", update_data.notice_period, notice_period is not None)

    new_file_path: str | None = None
    old_file_path: str | None = None

    # Handle File Update
    if file:
        _enforce_upload_rate_limit(request)
        # Validate and Save
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
            
        # Mark old file for deletion AFTER commit
        old_file_path = contract.file_path
        
        contract.file_path = new_file_path
        changes.append("file: updated")

    try:
        if tags is not None:
            old_tags = [tag.name for tag in contract.tags]
            new_tags = update_data.tags or []
            if set(old_tags) != set(new_tags):
                changes.append(f"tags: {old_tags} -> {new_tags}")
                contract.tags = _resolve_tags(session, new_tags)

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
            diff_summary = "; ".join(changes)
            log_audit(
                session,
                current_user.id,
                "UPDATE_CONTRACT",
                f"[CID:{contract_id}] Updated Contract. Changes: {diff_summary}",
                request.client.host if request.client else "unknown",
                request.headers.get("user-agent"),
                contract_id=contract_id,
                commit=False,
            )
            session.commit()
    except Exception:
        session.rollback()
        if new_file_path:
            delete_upload_file(new_file_path)
        raise

    # Keep post-commit reads outside the rollback/file-cleanup path. A failed
    # refresh cannot undo the transaction and the new file is now authoritative.
    if changes:
        session.refresh(contract)
    if old_file_path and old_file_path != contract.file_path:
        delete_upload_file(old_file_path)
    
    return contract_read_for_user(contract, current_user, session)

@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: int, 
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission (need "full" level to delete)
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=403, detail="You don't have permission to delete this contract")
    
    if contract.is_protected:
        raise HTTPException(
            status_code=403, 
            detail=(
                "This contract is protected. You must unprotect it from the "
                "Protected Contracts page before deleting."
            ),
        )
    
    expected_version = version
    if expected_version != contract.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract was changed by another request; reload and retry",
        )

    # Save immutable values from the version that the conditional delete claims.
    file_path_to_delete = contract.file_path
    contract_title = contract.title

    try:
        session.exec(delete(ContractTagLink).where(col(ContractTagLink.contract_id) == contract_id))
        session.exec(delete(ContractListLink).where(col(ContractListLink.contract_id) == contract_id))
        session.exec(delete(ContractPermission).where(col(ContractPermission.contract_id) == contract_id))
        client_host = request.client.host if request.client else "unknown"
        log_audit(
            session,
            current_user.id,
            "DELETE_CONTRACT",
            f"[CID:{contract_id}] Deleted contract {contract_title}",
            client_host,
            request.headers.get("user-agent"),
            contract_id=contract_id,
            commit=False,
        )
        session.exec(
            update(Contract)
            .where(col(Contract.parent_id) == contract_id)
            .values(parent_id=None)
        )
        delete_result = session.exec(
            delete(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == expected_version,
                col(Contract.is_protected).is_(False),
            )
            .execution_options(synchronize_session=False)
        )
        if delete_result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Contract was changed or protected by another request; reload and retry",
            )
        session.commit()
    except Exception:
        session.rollback()
        raise

    # Delete file if exists (After commit checks pass)
    if file_path_to_delete:
        try:
            delete_upload_file(file_path_to_delete)
        except Exception:
            logger.exception("Could not delete file for contract %s", contract_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/contracts/{contract_id}/toggle-protection", response_model=ContractRead)
def toggle_contract_protection(
    contract_id: int,
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Toggle the protected status of a contract (Admin only or Full Permission?) -> Let's say Full Perm."""
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission (need "full" level to change protection)
    # Admins may remove protection, but it still requires an explicit extra step.
    # So "full" permission or Admin is fine, but the UI flow prevents accidental delete.
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=403, detail="You don't have permission to modify protection status")

    expected_version = version
    if expected_version != contract.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract was changed by another request; reload and retry",
        )
    next_protection = not contract.is_protected
    try:
        claim_result = session.exec(
            update(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == expected_version,
            )
            .values(
                is_protected=next_protection,
                version=expected_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if claim_result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Contract was changed by another request; reload and retry",
            )
        action = "PROTECTED" if next_protection else "UNPROTECTED"
        log_audit(
            session,
            current_user.id,
            f"CONTRACT_{action}",
            f"[CID:{contract_id}] Contract {action}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", "unknown"),
            contract_id=contract_id,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(contract)
    
    return contract_read_for_user(contract, current_user, session)
