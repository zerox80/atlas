"""Contract-list routes."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, delete, select

from api_core import (
    allowed_permission_levels,
    contract_reads_for_user,
    filter_contracts_for_user,
    get_current_user,
    get_visible_list_or_404,
    require_admin,
    visible_contract_count_for_list,
)
from database import get_session
from models import Contract, ContractList, ContractListLink, ContractPermission, User
from schemas import ContractListCreate, ContractListRead, ContractListUpdate, ContractRead

router = APIRouter()

@router.get("/lists", response_model=List[ContractListRead])
def get_lists(
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Get visible contract lists with permission-aware contract counts."""
    lists = session.exec(select(ContractList).order_by(col(ContractList.name).asc())).all()
    count_statement = (
        select(
            ContractListLink.list_id,
            func.count(func.distinct(ContractListLink.contract_id)),
        )
        .join(Contract, col(Contract.id) == col(ContractListLink.contract_id))
    )
    if current_user.role != "admin":
        count_statement = (
            count_statement
            .join(
                ContractPermission,
                col(ContractPermission.contract_id) == col(Contract.id),
            )
            .where(col(ContractPermission.user_id) == current_user.id)
            .where(
                col(ContractPermission.permission_level).in_(
                    allowed_permission_levels("read")
                )
            )
        )
    counts = dict(
        session.exec(count_statement.group_by(ContractListLink.list_id)).all()
    )

    result = []
    for lst in lists:
        if lst.id is None:
            continue
        count = int(counts.get(lst.id, 0))
        if current_user.role != "admin" and count == 0:
            continue
        result.append({
            "id": lst.id,
            "name": lst.name,
            "description": lst.description,
            "color": lst.color,
            "created_at": lst.created_at,
            "contract_count": count or 0
        })
    return result


@router.post("/lists", response_model=ContractListRead, status_code=201)
def create_list(
    list_data: ContractListCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new contract list."""
    new_list = ContractList(
        name=list_data.name,
        description=list_data.description,
        color=list_data.color
    )
    session.add(new_list)
    session.commit()
    session.refresh(new_list)
    return {
        "id": new_list.id,
        "name": new_list.name,
        "description": new_list.description,
        "color": new_list.color,
        "created_at": new_list.created_at,
        "contract_count": 0
    }


@router.get("/lists/{list_id}", response_model=ContractListRead)
def get_list(
    list_id: int, 
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Get a specific list with its contract count."""
    lst = get_visible_list_or_404(list_id, current_user, session)
    count = visible_contract_count_for_list(list_id, current_user, session)
    
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "created_at": lst.created_at,
        "contract_count": count or 0
    }


@router.put("/lists/{list_id}", response_model=ContractListRead)
def update_list(
    list_id: int,
    list_data: ContractListUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Update a list."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    if list_data.name is not None:
        lst.name = list_data.name
    if list_data.description is not None:
        lst.description = list_data.description
    if list_data.color is not None:
        lst.color = list_data.color
    
    session.add(lst)
    session.commit()
    session.refresh(lst)
    
    count = visible_contract_count_for_list(list_id, admin, session)
    
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "created_at": lst.created_at,
        "contract_count": count or 0
    }


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: int, 
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Delete a list (contracts are NOT deleted, only the association)."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    # Remove all links first
    session.exec(delete(ContractListLink).where(col(ContractListLink.list_id) == list_id))
    session.delete(lst)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lists/{list_id}/contracts/{contract_id}", status_code=201)
def add_contract_to_list(
    list_id: int,
    contract_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Add a contract to a list."""
    # Check list exists
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    # Check contract exists
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check if already linked
    existing = session.exec(
        select(ContractListLink).where(
            ContractListLink.list_id == list_id,
            ContractListLink.contract_id == contract_id
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Contract already in list")
    
    link = ContractListLink(list_id=list_id, contract_id=contract_id)
    session.add(link)
    session.commit()
    return {"ok": True, "message": f"Contract '{contract.title}' added to list '{lst.name}'"}


@router.delete("/lists/{list_id}/contracts/{contract_id}")
def remove_contract_from_list(
    list_id: int,
    contract_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Remove a contract from a list."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    link = session.exec(
        select(ContractListLink).where(
            ContractListLink.list_id == list_id,
            ContractListLink.contract_id == contract_id
        )
    ).first()
    
    if not link:
        raise HTTPException(status_code=404, detail="Contract not in list")
    
    session.delete(link)
    session.commit()
    return {"ok": True, "message": "Contract removed from list"}


@router.get("/lists/{list_id}/contracts", response_model=List[ContractRead])
def get_list_contracts(
    list_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Get all contracts in a specific list."""
    get_visible_list_or_404(list_id, current_user, session)
    
    statement = (
        select(Contract)
        .join(ContractListLink)
        .where(col(ContractListLink.list_id) == list_id)
        .options(selectinload(Contract.tags), selectinload(Contract.lists))  # type: ignore[arg-type]
    )
    statement = filter_contracts_for_user(statement, current_user, "read").distinct()
    contracts = session.exec(statement.offset(offset).limit(limit)).all()
    
    return contract_reads_for_user(contracts, current_user, session)


# ========================================
#           AI FEATURES (Mistral Large 3)
# ========================================

# Imports moved to top


