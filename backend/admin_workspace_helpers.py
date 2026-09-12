"""Default-workspace selection and permission helpers for user administration."""

from fastapi import HTTPException
from sqlmodel import Session, select

from api_core import (
    resolve_user_default_workspace,
    workspace_can_be_selected_as_default,
)
from models import ContractList, ContractListPermission, User


def _ensure_default_workspace_permission(
    session: Session,
    user: User,
    workspace: ContractList,
) -> bool:
    """Grant the minimum workspace permission implied by a default target."""
    if user.role == "admin":
        return False
    if user.id is None or workspace.id is None:
        raise RuntimeError("Default workspace permission could not be resolved")

    desired_level = (
        "full"
        if workspace.is_default and workspace.owner_user_id == user.id
        else "write"
    )
    permission = session.exec(
        select(ContractListPermission)
        .where(ContractListPermission.user_id == user.id)
        .where(ContractListPermission.list_id == workspace.id)
    ).first()
    if permission is None:
        session.add(
            ContractListPermission(
                user_id=user.id,
                list_id=workspace.id,
                permission_level=desired_level,
            )
        )
        session.flush()
        return True

    current_level = permission.permission_level
    needs_upgrade = (
        desired_level == "full" and current_level != "full"
    ) or (
        desired_level == "write" and current_level not in {"write", "full"}
    )
    if not needs_upgrade:
        return False
    permission.permission_level = desired_level
    session.add(permission)
    session.flush()
    return True


def _get_default_workspace_target(
    session: Session,
    user: User,
    workspace_id: int | None,
) -> ContractList | None:
    if workspace_id is None:
        return None
    workspace = session.get(ContractList, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not workspace_can_be_selected_as_default(user, workspace):
        raise HTTPException(
            status_code=400,
            detail=(
                "Another user's personal Default cannot be selected as the "
                "upload target"
            ),
        )
    return workspace


def _apply_default_workspace_target(
    session: Session,
    user: User,
    workspace: ContractList | None,
) -> tuple[int | None, int | None, bool]:
    previous_workspace_id = user.default_workspace_id
    permission_changed = (
        _ensure_default_workspace_permission(session, user, workspace)
        if workspace is not None
        else False
    )
    user.default_workspace_id = workspace.id if workspace is not None else None
    session.add(user)
    if workspace is None:
        resolve_user_default_workspace(session, user)
    return previous_workspace_id, user.default_workspace_id, permission_changed


def _is_personal_default_owner_permission(
    user_id: int,
    workspace: ContractList | None,
) -> bool:
    """Identify the mandatory owner ACL of one personal Default workspace."""
    return bool(
        workspace is not None
        and workspace.is_default
        and workspace.owner_user_id == user_id
    )
