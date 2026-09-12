"""Contract-list routes."""


from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, col, select

from api_core import (
    allowed_permission_levels,
    get_current_user,
    permission_grants,
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
    ContractListRead,
)

router = APIRouter()

@router.get("/lists", response_model=list[ContractListRead])
def get_lists(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Get visible contract lists with permission-aware contract counts."""
    lists = session.exec(select(ContractList).order_by(col(ContractList.name).asc())).all()
    if current_user.role == "admin" and not current_user.show_other_user_workspaces:
        lists = [
            workspace
            for workspace in lists
            if not workspace.is_default
            or workspace.owner_user_id == current_user.id
        ]
    owner_names = dict(session.exec(select(User.id, User.username)).all())
    all_counts = dict(session.exec(
        select(
            ContractListLink.list_id,
            func.count(func.distinct(ContractListLink.contract_id)),
        )
        .join(Contract, col(Contract.id) == col(ContractListLink.contract_id))
        .where(col(Contract.deleted_at).is_(None))
        .group_by(col(ContractListLink.list_id))
    ).all())
    workspace_levels: dict[int, str] = {}
    direct_counts: dict[int | None, int] = {}
    direct_access_list_ids: set[int | None] = set()
    if current_user.role != "admin":
        workspace_levels = dict(session.exec(
            select(
                ContractListPermission.list_id,
                ContractListPermission.permission_level,
            )
            .where(col(ContractListPermission.user_id) == current_user.id)
        ).all())
        direct_counts = dict(session.exec(
            select(
                col(ContractListLink.list_id),
                func.count(func.distinct(ContractListLink.contract_id)),
            )
            .join(
                ContractPermission,
                col(ContractPermission.contract_id)
                == col(ContractListLink.contract_id),
            )
            .join(Contract, col(Contract.id) == col(ContractListLink.contract_id))
            .where(col(ContractPermission.user_id) == current_user.id)
            .where(col(Contract.deleted_at).is_(None))
            .where(
                col(ContractPermission.permission_level).in_(
                    allowed_permission_levels("read")
                )
            )
            .group_by(col(ContractListLink.list_id))
        ).all())
        direct_access_list_ids = set(
            session.exec(
                select(col(ContractListLink.list_id))
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
                .distinct()
            )
            .all()
        )

    result = []
    for lst in lists:
        if lst.id is None:
            continue
        assigned_level = (
            "full" if current_user.role == "admin" else workspace_levels.get(lst.id)
        )
        has_workspace_read = permission_grants(assigned_level, "read")
        direct_count = int(direct_counts.get(lst.id, 0))
        has_direct_access = lst.id in direct_access_list_ids
        if (
            current_user.role != "admin"
            and not has_workspace_read
            and not has_direct_access
        ):
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
