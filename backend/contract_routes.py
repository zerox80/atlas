"""Contract creation, update, download, deletion, and protection routes."""

import mimetypes
import os
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from api_core import check_contract_permission, contract_read_for_user, get_current_user
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
    tags: Annotated[Optional[str], Form()] = "",
    document_type: Annotated[str, Form()] = "contract",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
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

    # 1. Validate File
    try:
        await validate_file(file)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid file")

    # 2. Save File
    try:
        file_path = await save_upload_file(file)
    except HTTPException as e:
        raise e
        
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
            commit=False,
        )
        session.commit()
        session.refresh(contract)
    except Exception:
        session.rollback()
        delete_upload_file(file_path)
        raise

    return contract_read_for_user(contract, current_user, session)

# Removed unused StreamingResponse import
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
        print(f"[ERROR] File not found on disk: {contract.file_path}")
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
    )
    
    # Determine basic mime types to avoid browser confusion
    # Determine basic mime types to avoid browser confusion
    import mimetypes
    media_type, _ = mimetypes.guess_type(resolved_path)
    
    # Check explicitly for pdf to be sure
    _, ext = os.path.splitext(resolved_path)
    if ext.lower() == ".pdf":
        media_type = "application/pdf"
        
    if not media_type:
        media_type = "application/octet-stream"
        
    # Ensure extension is in filename
    filename = f"{contract.title}{ext}"
    
    from fastapi.responses import FileResponse
    return FileResponse(resolved_path, media_type=media_type, filename=filename)

@router.put("/contracts/{contract_id}", response_model=ContractRead)
async def update_contract(
    contract_id: int, 
    request: Request,
    title: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
    start_date: Annotated[Optional[str], Form()] = None,
    end_date: Annotated[Optional[str], Form()] = None,
    value: Annotated[Optional[str], Form()] = None,
    annual_value: Annotated[Optional[str], Form()] = None,
    notice_period: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None,
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

    changes = []
    
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
        # Validate and Save
        try:
            await validate_file(file)
            new_file_path = await save_upload_file(file)
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
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
            session.add(contract)
            diff_summary = "; ".join(changes)
            log_audit(
                session,
                current_user.id,
                "UPDATE_CONTRACT",
                f"[CID:{contract_id}] Updated Contract. Changes: {diff_summary}",
                request.client.host if request.client else "unknown",
                request.headers.get("user-agent"),
                commit=False,
            )
            session.commit()
            session.refresh(contract)
    except Exception:
        session.rollback()
        if new_file_path:
            delete_upload_file(new_file_path)
        raise

    if old_file_path and old_file_path != contract.file_path:
        delete_upload_file(old_file_path)
    
    return contract_read_for_user(contract, current_user, session)

@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: int, 
    request: Request,
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
    
    # Save file path before deleting record
    file_path_to_delete = contract.file_path
    contract_title = contract.title

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
        commit=False,
    )
    session.delete(contract)
    session.commit()

    # Delete file if exists (After commit checks pass)
    if file_path_to_delete:
        try:
            delete_upload_file(file_path_to_delete)
        except Exception as e:
            print(f"Error deleting file: {e}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/contracts/{contract_id}/toggle-protection", response_model=ContractRead)
def toggle_contract_protection(
    contract_id: int,
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
        
    contract.is_protected = not contract.is_protected
    action = "PROTECTED" if contract.is_protected else "UNPROTECTED"
    log_audit(
        session, 
        current_user.id, 
        f"CONTRACT_{action}", 
        f"[CID:{contract_id}] Contract {action}", 
        "unknown",
        "unknown",
        commit=False,
    )
    session.add(contract)
    session.commit()
    session.refresh(contract)
    
    return contract_read_for_user(contract, current_user, session)

