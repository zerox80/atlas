"""Tag and audit-log routes."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import or_
from sqlmodel import Session, col, delete, select

from api_core import (
    check_contract_permission,
    filter_contracts_for_user,
    get_current_user,
    require_admin,
)
from database import get_session
from models import AuditLog, Contract, ContractTagLink, Tag, User
from schemas import (
    AuditLogRead,
    ContractAuditLogPage,
    ContractAuditLogRead,
    TagCreate,
    TagRead,
    TagUpdate,
)
from security_utils import log_audit

router = APIRouter()

@router.get("/tags", response_model=List[TagRead])
def get_tags(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Return only tags attached to documents visible to the caller."""
    if current_user.role == "admin":
        return session.exec(select(Tag).order_by(col(Tag.name))).all()
    statement = (
        select(Tag)
        .join(ContractTagLink, col(ContractTagLink.tag_id) == col(Tag.id))
        .join(Contract, col(Contract.id) == col(ContractTagLink.contract_id))
    )
    statement = filter_contracts_for_user(statement, current_user, "read")
    return session.exec(statement.distinct().order_by(col(Tag.name))).all()


@router.post("/tags", response_model=TagRead, status_code=201)
def create_tag(
    tag_data: TagCreate,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new tag (Admin only)"""
    # Check if tag name already exists
    existing = session.exec(select(Tag).where(Tag.name == tag_data.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag mit diesem Namen existiert bereits")
    
    new_tag = Tag(name=tag_data.name, color=tag_data.color)
    session.add(new_tag)
    session.flush()
    log_audit(
        session,
        admin.id,
        "CREATE_TAG",
        f"Created tag '{new_tag.name}'",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    session.refresh(new_tag)
    return new_tag


@router.put("/tags/{tag_id}", response_model=TagRead)
def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Update an existing tag (Admin only)"""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden")
    
    changes = []
    
    if tag_data.name is not None and tag_data.name != tag.name:
        # Check if new name already exists
        existing = session.exec(select(Tag).where(Tag.name == tag_data.name)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Tag mit diesem Namen existiert bereits")
        changes.append(f"name: '{tag.name}' -> '{tag_data.name}'")
        tag.name = tag_data.name
    
    if tag_data.color is not None and tag_data.color != tag.color:
        changes.append(f"color: '{tag.color}' -> '{tag_data.color}'")
        tag.color = tag_data.color
    
    if changes:
        session.add(tag)
        log_audit(
            session,
            admin.id,
            "UPDATE_TAG",
            f"Updated tag '{tag.name}': {'; '.join(changes)}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            commit=False,
        )
        session.commit()
        session.refresh(tag)
    
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Delete a tag (Admin only). Removes tag from all contracts."""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden")
    
    tag_name = tag.name
    
    # Remove all contract-tag links first
    session.exec(delete(ContractTagLink).where(col(ContractTagLink.tag_id) == tag_id))
    
    session.delete(tag)
    log_audit(
        session,
        admin.id,
        "DELETE_TAG",
        f"Deleted tag '{tag_name}'",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/audit-logs", response_model=List[AuditLogRead])
def get_audit_logs(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    results = session.exec(
        select(AuditLog, User)
        .join(User, isouter=True)
        .order_by(col(AuditLog.timestamp).desc())
        .limit(100)
    ).all()
    logs = []
    for log, user in results:
        l_dict = log.model_dump()
        l_dict["username"] = user.username if user else "Unknown"
        logs.append(l_dict)
    return logs

@router.get(
    "/contracts/{contract_id}/audit",
    response_model=ContractAuditLogPage,
)
def get_contract_audit_logs(
    contract_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    cursor_timestamp: Optional[datetime] = None,
    cursor_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=404, detail="Contract not found")

    if (cursor_timestamp is None) != (cursor_id is None):
        raise HTTPException(
            status_code=422,
            detail="cursor_timestamp and cursor_id must be provided together",
        )

    statement = (
        select(AuditLog, User)
        .join(User, isouter=True)
        .where(col(AuditLog.contract_id) == contract_id)
    )
    if cursor_timestamp is not None and cursor_id is not None:
        statement = statement.where(
            or_(
                col(AuditLog.timestamp) < cursor_timestamp,
                (col(AuditLog.timestamp) == cursor_timestamp)
                & (col(AuditLog.id) < cursor_id),
            )
        )
    statement = statement.order_by(
        col(AuditLog.timestamp).desc(), col(AuditLog.id).desc()
    )
    results = list(session.exec(statement.limit(limit + 1)).all())
    has_more = len(results) > limit
    visible_results = results[:limit]

    logs: list[dict[str, object]] = []
    for log, user in visible_results:
        logs.append(
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": user.username if user else "Unknown",
                "action": log.action,
                "details": log.details,
                "timestamp": log.timestamp,
            }
        )
    last_log = visible_results[-1][0] if has_more and visible_results else None
    return {
        "items": logs,
        "has_more": has_more,
        "next_cursor_timestamp": last_log.timestamp if last_log else None,
        "next_cursor_id": last_log.id if last_log else None,
    }


# ========================================
#           ADMIN PANEL ENDPOINTS
# ========================================
