"""Tag and audit-log routes."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, col, delete, select

from api_core import check_contract_permission, get_current_user, require_admin
from database import get_session
from models import AuditLog, Contract, ContractTagLink, Tag, User
from schemas import AuditLogRead, TagCreate, TagRead, TagUpdate
from security_utils import log_audit

router = APIRouter()
CONTRACT_AUDIT_LOG_LIMIT = 100

@router.get("/tags", response_model=List[TagRead])
def get_tags(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Get all tags (requires authentication)"""
    return session.exec(select(Tag)).all()


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
    session.commit()
    session.refresh(new_tag)
    
    log_audit(
        session,
        admin.id,
        "CREATE_TAG",
        f"Created tag '{new_tag.name}'",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
    )
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
        session.commit()
        session.refresh(tag)
        log_audit(
            session,
            admin.id,
            "UPDATE_TAG",
            f"Updated tag '{tag.name}': {'; '.join(changes)}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
        )
    
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
    session.commit()
    
    log_audit(
        session,
        admin.id,
        "DELETE_TAG",
        f"Deleted tag '{tag_name}'",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
    )
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

@router.get("/contracts/{contract_id}/audit", response_model=List[AuditLogRead])
def get_contract_audit_logs(
    contract_id: int, 
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="You don't have permission to access this contract")

    results = session.exec(
        select(AuditLog, User)
        .join(User, isouter=True)
        .where(col(AuditLog.contract_id) == contract_id)
        .order_by(col(AuditLog.timestamp).desc())
        .limit(CONTRACT_AUDIT_LOG_LIMIT)
    ).all()
    
    logs = []
    for log, user in results:
        l_dict = log.model_dump()
        l_dict["username"] = user.username if user else "Unknown"
        logs.append(l_dict)
    return logs


# ========================================
#           ADMIN PANEL ENDPOINTS
# ========================================
