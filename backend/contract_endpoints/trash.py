"""Recoverable, workspace-scoped document trash endpoints."""

import logging
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, delete, select, update

from api_core import (
    check_contract_permission,
    check_workspace_permission,
    contract_read_for_user,
    contract_reads_for_user,
    filter_contracts_for_user,
    get_current_user,
    has_direct_contract_access_for_list,
)
from database import get_session
from file_utils import delete_upload_file
from models import (
    Contract,
    ContractList,
    ContractListLink,
    ContractPermission,
    ContractTagLink,
    User,
)
from schemas import ContractRead, TrashDocumentPage
from security_utils import log_audit

router = APIRouter()
logger = logging.getLogger(__name__)


def _trash_statement(
    current_user: User,
    list_id: Optional[int],
    document_type: Optional[str],
    query: Optional[str],
):
    statement = select(Contract).where(col(Contract.deleted_at).is_not(None))
    if list_id is not None:
        statement = statement.join(ContractListLink).where(
            col(ContractListLink.list_id) == list_id
        )
    if document_type in {"contract", "invoice"}:
        statement = statement.where(col(Contract.document_type) == document_type)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                col(Contract.title).ilike(pattern),
                col(Contract.description).ilike(pattern),
            )
        )
    return filter_contracts_for_user(
        statement,
        current_user,
        "read",
        list_id=list_id,
    )


@router.get("/trash", response_model=TrashDocumentPage)
def read_trash(
    list_id: Optional[int] = None,
    document_type: Optional[Literal["contract", "invoice"]] = None,
    q: Optional[str] = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return one workspace trash, or the complete trash for administrators."""
    if list_id is None and current_user.role != "admin":
        raise HTTPException(status_code=400, detail="Workspace is required")
    if list_id is not None:
        workspace = session.get(ContractList, list_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if current_user.role != "admin":
            has_workspace_access = check_workspace_permission(
                current_user,
                list_id,
                "read",
                session,
            )
            has_direct_access = has_direct_contract_access_for_list(
                list_id,
                current_user,
                session,
            )
            if not (has_workspace_access or has_direct_access):
                raise HTTPException(status_code=404, detail="Workspace not found")

    statement = _trash_statement(current_user, list_id, document_type, q)
    scope = (
        statement.with_only_columns(Contract.id)
        .order_by(None)
        .distinct()
        .subquery()
    )
    total = int(
        session.exec(select(func.count()).select_from(scope)).one() or 0
    )
    documents = list(
        session.exec(
            statement.distinct()
            .options(
                selectinload(Contract.tags),
                selectinload(Contract.lists),  # type: ignore[arg-type]
            )
            .order_by(col(Contract.deleted_at).desc(), col(Contract.id).desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    deleted_by_ids = {
        document.deleted_by_user_id
        for document in documents
        if document.deleted_by_user_id is not None
    }
    deleted_by_names = (
        dict(
            session.exec(
                select(User.id, User.username).where(col(User.id).in_(deleted_by_ids))
            ).all()
        )
        if deleted_by_ids
        else {}
    )
    items = contract_reads_for_user(documents, current_user, session)
    for item, document in zip(items, documents):
        item["deleted_at"] = document.deleted_at
        item["deleted_by_user_id"] = document.deleted_by_user_id
        item["deleted_by_username"] = deleted_by_names.get(
            document.deleted_by_user_id
        )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _require_trashed_document(
    contract_id: int,
    version: int,
    current_user: User,
    session: Session,
) -> Contract:
    contract = session.get(Contract, contract_id)
    if contract is None or contract.deleted_at is None:
        raise HTTPException(status_code=404, detail="Document not found in trash")
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=404, detail="Document not found in trash")
    if contract.version != version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document was changed by another request; reload and retry",
        )
    return contract


@router.put("/trash/{contract_id}/restore", response_model=ContractRead)
def restore_document(
    contract_id: int,
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = _require_trashed_document(
        contract_id,
        version,
        current_user,
        session,
    )
    try:
        result = session.exec(
            update(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == version,
                col(Contract.deleted_at).is_not(None),
            )
            .values(
                deleted_at=None,
                deleted_by_user_id=None,
                version=version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document was changed by another request; reload and retry",
            )
        log_audit(
            session,
            current_user.id,
            "RESTORE_FROM_TRASH",
            f"[CID:{contract_id}] Restored {contract.document_type} {contract.title}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            contract_id=contract_id,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(contract)
    return contract_read_for_user(contract, current_user, session)


@router.delete(
    "/trash/{contract_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
)
def permanently_delete_document(
    contract_id: int,
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = _require_trashed_document(
        contract_id,
        version,
        current_user,
        session,
    )
    file_path = contract.file_path
    document_title = contract.title
    document_type = contract.document_type
    try:
        session.exec(
            delete(ContractTagLink).where(
                col(ContractTagLink.contract_id) == contract_id
            )
        )
        session.exec(
            delete(ContractListLink).where(
                col(ContractListLink.contract_id) == contract_id
            )
        )
        session.exec(
            delete(ContractPermission).where(
                col(ContractPermission.contract_id) == contract_id
            )
        )
        session.exec(
            update(Contract)
            .where(col(Contract.parent_id) == contract_id)
            .values(parent_id=None)
        )
        result = session.exec(
            delete(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == version,
                col(Contract.deleted_at).is_not(None),
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document was changed by another request; reload and retry",
            )
        log_audit(
            session,
            current_user.id,
            "PERMANENTLY_DELETE_DOCUMENT",
            f"[CID:{contract_id}] Permanently deleted {document_type} {document_title}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            contract_id=contract_id,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    if file_path:
        try:
            delete_upload_file(file_path)
        except Exception:
            logger.exception("Could not delete file for document %s", contract_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
