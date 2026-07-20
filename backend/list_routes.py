"""Contract-list routes."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, delete, select

from api_core import (
    allowed_permission_levels,
    contract_reads_for_user,
    ensure_default_workspace,
    filter_contracts_for_user,
    get_current_user,
    get_visible_list_or_404,
    permission_grants,
    require_admin,
    resolve_user_default_workspace,
    visible_contract_count_for_list,
    workspace_permission_level,
)
from database import get_session
from models import (
    Contract,
    ContractList,
    ContractListLink,
    ContractListPermission,
    ContractPermission,
    User,
)
from schemas import (
    ContractListBulkResult,
    ContractListBulkUpdate,
    ContractListCreate,
    ContractListRead,
    ContractListUpdate,
    ContractRead,
    ContractSelection,
)

router = APIRouter()

@router.get("/lists", response_model=List[ContractListRead])
def get_lists(
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Get visible contract lists with permission-aware contract counts."""
    lists = session.exec(select(ContractList).order_by(col(ContractList.name).asc())).all()
    owner_names = dict(session.exec(select(User.id, User.username)).all())
    all_counts = dict(session.exec(
        select(
            ContractListLink.list_id,
            func.count(func.distinct(ContractListLink.contract_id)),
        )
        .group_by(ContractListLink.list_id)
    ).all())
    workspace_levels: dict[int, str] = {}
    direct_counts: dict[int, int] = {}
    if current_user.role != "admin":
        workspace_levels = dict(session.exec(
            select(
                ContractListPermission.list_id,
                ContractListPermission.permission_level,
            )
            .where(ContractListPermission.user_id == current_user.id)
        ).all())
        direct_counts = dict(session.exec(
            select(
                ContractListLink.list_id,
                func.count(func.distinct(ContractListLink.contract_id)),
            )
            .join(
                ContractPermission,
                col(ContractPermission.contract_id)
                == col(ContractListLink.contract_id),
            )
            .where(col(ContractPermission.user_id) == current_user.id)
            .where(
                col(ContractPermission.permission_level).in_(
                    allowed_permission_levels("read")
                )
            )
            .group_by(ContractListLink.list_id)
        ).all())

    result = []
    for lst in lists:
        if lst.id is None:
            continue
        assigned_level = (
            "full" if current_user.role == "admin" else workspace_levels.get(lst.id)
        )
        has_workspace_read = permission_grants(assigned_level, "read")
        direct_count = int(direct_counts.get(lst.id, 0))
        if current_user.role != "admin" and not has_workspace_read and direct_count == 0:
            continue
        count = (
            int(all_counts.get(lst.id, 0))
            if has_workspace_read
            else direct_count
        )
        result.append({
            "id": lst.id,
            "owner_user_id": lst.owner_user_id,
            "owner_username": owner_names.get(lst.owner_user_id),
            "name": lst.name,
            "description": lst.description,
            "color": lst.color,
            "is_default": lst.is_default,
            "created_at": lst.created_at,
            "contract_count": count or 0,
            "can_read": True,
            "can_write": permission_grants(assigned_level, "write"),
            "is_preferred_default": current_user.default_workspace_id == lst.id,
        })
    return result


@router.post("/lists", response_model=ContractListRead, status_code=201)
def create_list(
    list_data: ContractListCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new contract list."""
    if list_data.name.strip().casefold() == "default":
        raise HTTPException(status_code=400, detail="'Default' is a reserved workspace name")
    new_list = ContractList(
        owner_user_id=admin.id,
        name=list_data.name,
        description=list_data.description,
        color=list_data.color,
        is_default=False,
    )
    session.add(new_list)
    session.commit()
    session.refresh(new_list)
    return {
        "id": new_list.id,
        "owner_user_id": new_list.owner_user_id,
        "owner_username": admin.username,
        "name": new_list.name,
        "description": new_list.description,
        "color": new_list.color,
        "is_default": new_list.is_default,
        "created_at": new_list.created_at,
        "contract_count": 0,
        "can_read": True,
        "can_write": True,
        "is_preferred_default": admin.default_workspace_id == new_list.id,
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
    assigned_level = workspace_permission_level(current_user, list_id, session)
    owner = session.get(User, lst.owner_user_id) if lst.owner_user_id else None
    
    return {
        "id": lst.id,
        "owner_user_id": lst.owner_user_id,
        "owner_username": owner.username if owner else None,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "is_default": lst.is_default,
        "created_at": lst.created_at,
        "contract_count": count or 0,
        "can_read": True,
        "can_write": permission_grants(assigned_level, "write"),
        "is_preferred_default": current_user.default_workspace_id == lst.id,
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
    
    if lst.is_default and list_data.name is not None and list_data.name != "Default":
        raise HTTPException(status_code=400, detail="The Default workspace cannot be renamed")
    if (
        not lst.is_default
        and list_data.name is not None
        and list_data.name.strip().casefold() == "default"
        and lst.name.strip().casefold() != "default"
    ):
        raise HTTPException(status_code=400, detail="'Default' is a reserved workspace name")

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
    owner = session.get(User, lst.owner_user_id) if lst.owner_user_id else None
    
    return {
        "id": lst.id,
        "owner_user_id": lst.owner_user_id,
        "owner_username": owner.username if owner else None,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "is_default": lst.is_default,
        "created_at": lst.created_at,
        "contract_count": count or 0,
        "can_read": True,
        "can_write": True,
        "is_preferred_default": admin.default_workspace_id == lst.id,
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
    if lst.is_default:
        raise HTTPException(status_code=400, detail="The Default workspace cannot be deleted")

    users_needing_default_fallback = session.exec(
        select(User).where(User.default_workspace_id == list_id)
    ).all()
    for user in users_needing_default_fallback:
        user.default_workspace_id = None
        session.add(user)
    session.flush()

    affected_contract_ids = list(session.exec(
        select(ContractListLink.contract_id).where(
            col(ContractListLink.list_id) == list_id
        )
    ).all())
    session.exec(delete(ContractListLink).where(col(ContractListLink.list_id) == list_id))
    session.exec(
        delete(ContractListPermission).where(
            col(ContractListPermission.list_id) == list_id
        )
    )
    session.delete(lst)
    session.flush()

    for user in users_needing_default_fallback:
        resolve_user_default_workspace(session, user)

    for contract_id in affected_contract_ids:
        remaining_link = session.exec(
            select(ContractListLink).where(
                col(ContractListLink.contract_id) == contract_id
            )
        ).first()
        if remaining_link is None:
            contract = session.get(Contract, contract_id)
            if contract is None:
                continue
            owner_id = contract.owner_user_id or admin.id
            if owner_id is None:
                raise RuntimeError("Document owner could not be resolved")
            if contract.owner_user_id is None:
                contract.owner_user_id = owner_id
                session.add(contract)
            default_workspace = ensure_default_workspace(session, owner_id)
            if default_workspace.id is None:
                raise RuntimeError("Default workspace could not be resolved")
            session.add(
                ContractListLink(
                    contract_id=contract_id,
                    list_id=default_workspace.id,
                )
            )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/contract-list-assignments/personal-default",
    response_model=ContractListBulkResult,
)
def move_contracts_to_personal_defaults(
    selection_data: ContractSelection,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Move every selected contract into its owner's isolated Default."""
    contract_ids = selection_data.contract_ids
    contracts = session.exec(
        select(Contract).where(col(Contract.id).in_(contract_ids))
    ).all()
    contracts_by_id = {
        contract.id: contract for contract in contracts if contract.id is not None
    }
    missing_ids = [
        contract_id for contract_id in contract_ids if contract_id not in contracts_by_id
    ]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"{len(missing_ids)} selected contract(s) no longer exist",
        )

    target_list_ids: dict[int, int] = {}
    defaults_by_owner: dict[int, ContractList] = {}
    for contract_id in contract_ids:
        contract = contracts_by_id[contract_id]
        owner_id = contract.owner_user_id or admin.id
        if owner_id is None:
            raise RuntimeError("Document owner could not be resolved")
        if contract.owner_user_id is None:
            contract.owner_user_id = owner_id
            session.add(contract)
        default_workspace = defaults_by_owner.get(owner_id)
        if default_workspace is None:
            default_workspace = ensure_default_workspace(session, owner_id)
            defaults_by_owner[owner_id] = default_workspace
        if default_workspace.id is None:
            raise RuntimeError("Default workspace could not be resolved")
        target_list_ids[contract_id] = default_workspace.id

    current_rows = session.exec(
        select(ContractListLink.contract_id, ContractListLink.list_id).where(
            col(ContractListLink.contract_id).in_(contract_ids)
        )
    ).all()
    current_list_ids = {contract_id: set() for contract_id in contract_ids}
    for contract_id, assigned_list_id in current_rows:
        current_list_ids[contract_id].add(assigned_list_id)

    changed_contract_ids = [
        contract_id
        for contract_id in contract_ids
        if current_list_ids[contract_id] != {target_list_ids[contract_id]}
    ]
    if changed_contract_ids:
        session.exec(
            delete(ContractListLink).where(
                col(ContractListLink.contract_id).in_(changed_contract_ids)
            )
        )
        session.flush()
        for contract_id in changed_contract_ids:
            session.add(
                ContractListLink(
                    contract_id=contract_id,
                    list_id=target_list_ids[contract_id],
                )
            )

    session.commit()
    return {
        "operation": "move_to_default",
        "changed_count": len(changed_contract_ids),
        "assignments": [
            {
                "contract_id": contract_id,
                "list_ids": [target_list_ids[contract_id]],
            }
            for contract_id in contract_ids
        ],
    }


@router.post(
    "/lists/{list_id}/contract-assignments",
    response_model=ContractListBulkResult,
)
def update_contract_list_assignments(
    list_id: int,
    assignment_data: ContractListBulkUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Add or remove many contracts in one atomic workspace operation."""
    workspace = session.get(ContractList, list_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="List not found")
    if workspace.is_default:
        raise HTTPException(
            status_code=400,
            detail="Personal Default workspaces are managed automatically",
        )

    contract_ids = assignment_data.contract_ids
    contracts = session.exec(
        select(Contract).where(col(Contract.id).in_(contract_ids))
    ).all()
    contracts_by_id = {
        contract.id: contract for contract in contracts if contract.id is not None
    }
    missing_ids = [
        contract_id for contract_id in contract_ids if contract_id not in contracts_by_id
    ]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"{len(missing_ids)} selected contract(s) no longer exist",
        )

    existing_target_ids = set(
        session.exec(
            select(ContractListLink.contract_id)
            .where(col(ContractListLink.list_id) == list_id)
            .where(col(ContractListLink.contract_id).in_(contract_ids))
        ).all()
    )
    changed_count = 0

    if assignment_data.operation == "add":
        for contract_id in contract_ids:
            if contract_id not in existing_target_ids:
                session.add(
                    ContractListLink(contract_id=contract_id, list_id=list_id)
                )
                changed_count += 1
        session.flush()
        session.exec(
            delete(ContractListLink)
            .where(col(ContractListLink.contract_id).in_(contract_ids))
            .where(
                col(ContractListLink.list_id).in_(
                    select(ContractList.id).where(
                        col(ContractList.is_default).is_(True)
                    )
                )
            )
        )
    else:
        changed_count = len(existing_target_ids)
        if existing_target_ids:
            session.exec(
                delete(ContractListLink)
                .where(col(ContractListLink.list_id) == list_id)
                .where(
                    col(ContractListLink.contract_id).in_(
                        list(existing_target_ids)
                    )
                )
            )
        session.flush()
        remaining_contract_ids = set(
            session.exec(
                select(ContractListLink.contract_id).where(
                    col(ContractListLink.contract_id).in_(contract_ids)
                )
            ).all()
        )
        defaults_by_owner: dict[int, ContractList] = {}
        for contract_id in contract_ids:
            if contract_id in remaining_contract_ids:
                continue
            contract = contracts_by_id[contract_id]
            owner_id = contract.owner_user_id or admin.id
            if owner_id is None:
                raise RuntimeError("Document owner could not be resolved")
            if contract.owner_user_id is None:
                contract.owner_user_id = owner_id
                session.add(contract)
            default_workspace = defaults_by_owner.get(owner_id)
            if default_workspace is None:
                default_workspace = ensure_default_workspace(session, owner_id)
                defaults_by_owner[owner_id] = default_workspace
            if default_workspace.id is None:
                raise RuntimeError("Default workspace could not be resolved")
            session.add(
                ContractListLink(
                    contract_id=contract_id,
                    list_id=default_workspace.id,
                )
            )

    session.flush()
    assignment_rows = session.exec(
        select(ContractListLink.contract_id, ContractListLink.list_id).where(
            col(ContractListLink.contract_id).in_(contract_ids)
        )
    ).all()
    list_ids_by_contract = {contract_id: [] for contract_id in contract_ids}
    for contract_id, assigned_list_id in assignment_rows:
        list_ids_by_contract[contract_id].append(assigned_list_id)
    session.commit()
    return {
        "operation": assignment_data.operation,
        "changed_count": changed_count,
        "assignments": [
            {
                "contract_id": contract_id,
                "list_ids": list_ids_by_contract[contract_id],
            }
            for contract_id in contract_ids
        ],
    }


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

    if lst.is_default:
        if contract.owner_user_id != lst.owner_user_id:
            raise HTTPException(
                status_code=400,
                detail="A document can only use its owner's Default workspace",
            )
        non_default_link = session.exec(
            select(ContractListLink)
            .join(
                ContractList,
                col(ContractList.id) == col(ContractListLink.list_id),
            )
            .where(col(ContractListLink.contract_id) == contract_id)
            .where(col(ContractList.is_default).is_(False))
        ).first()
        if non_default_link is not None:
            raise HTTPException(
                status_code=400,
                detail="Only unassigned documents belong in the Default workspace",
            )

    link = ContractListLink(list_id=list_id, contract_id=contract_id)
    session.add(link)
    if not lst.is_default:
        session.exec(
            delete(ContractListLink)
            .where(col(ContractListLink.contract_id) == contract_id)
            .where(
                col(ContractListLink.list_id).in_(
                    select(ContractList.id).where(
                        col(ContractList.is_default).is_(True)
                    )
                )
            )
        )
    session.commit()
    assigned_list_ids = list(
        session.exec(
            select(ContractListLink.list_id).where(
                col(ContractListLink.contract_id) == contract_id
            )
        ).all()
    )
    return {
        "ok": True,
        "message": f"Contract '{contract.title}' added to list '{lst.name}'",
        "list_ids": assigned_list_ids,
    }


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
    if lst.is_default:
        raise HTTPException(
            status_code=400,
            detail="Documents without another workspace must remain in Default",
        )

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
    session.flush()
    remaining_link = session.exec(
        select(ContractListLink).where(
            col(ContractListLink.contract_id) == contract_id
        )
    ).first()
    if remaining_link is None:
        owner_id = contract.owner_user_id or admin.id
        if owner_id is None:
            raise RuntimeError("Document owner could not be resolved")
        if contract.owner_user_id is None:
            contract.owner_user_id = owner_id
            session.add(contract)
        default_workspace = ensure_default_workspace(session, owner_id)
        if default_workspace.id is None:
            raise RuntimeError("Default workspace could not be resolved")
        session.add(
            ContractListLink(
                contract_id=contract_id,
                list_id=default_workspace.id,
            )
        )
    session.commit()
    assigned_list_ids = list(
        session.exec(
            select(ContractListLink.list_id).where(
                col(ContractListLink.contract_id) == contract_id
            )
        ).all()
    )
    return {
        "ok": True,
        "message": "Contract removed from list",
        "list_ids": assigned_list_ids,
    }


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
    statement = filter_contracts_for_user(
        statement,
        current_user,
        "read",
        list_id=list_id,
    ).distinct()
    contracts = session.exec(statement.offset(offset).limit(limit)).all()
    
    return contract_reads_for_user(contracts, current_user, session)


# ========================================
#           AI FEATURES (Mistral Large 3)
# ========================================

# Imports moved to top


