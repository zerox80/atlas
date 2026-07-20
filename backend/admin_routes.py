"""Current-user, user administration, and permission routes."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, update
from sqlmodel import Session, col, delete, select

from api_core import (
    ensure_default_workspace,
    ensure_active_admin_remains,
    get_current_user,
    require_admin,
    resolve_user_default_workspace,
    user_can_create_documents,
    workspace_can_be_default_for_user,
)
from auth import get_password_hash
from database import get_session
from models import (
    AuditLog,
    Contract,
    ContractList,
    ContractListLink,
    ContractListPermission,
    ContractPermission,
    User,
)
from schemas import (
    DefaultWorkspaceOptionRead,
    DefaultWorkspaceUpdate,
    PermissionCreate,
    PermissionPage,
    PermissionRead,
    UserCreate,
    UserPasswordUpdate,
    UserRead,
    UserUpdate,
    WorkspacePermissionCreate,
)
from security_utils import log_audit

router = APIRouter()


def _user_read_payload(session: Session, user: User) -> dict[str, object]:
    workspace = (
        session.get(ContractList, user.default_workspace_id)
        if user.default_workspace_id is not None
        else None
    )
    owner = (
        session.get(User, workspace.owner_user_id)
        if workspace is not None and workspace.owner_user_id is not None
        else None
    )
    workspace_name = None
    if workspace is not None:
        workspace_name = (
            f"{workspace.name} · {owner.username}" if owner else workspace.name
        )
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "has_2fa": bool(user.totp_secret),
        "default_workspace_id": user.default_workspace_id,
        "default_workspace_name": workspace_name,
    }


def _increment_token_version(session: Session, user: User) -> None:
    """Atomically revoke the user's issued JWTs and expire stale ORM state."""
    if user.id is None:
        raise RuntimeError("Cannot revoke sessions for a user without an ID")

    session.flush()
    session.exec(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
        .execution_options(synchronize_session=False)
    )
    session.expire(user, ["token_version"])


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get current authenticated user info"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "has_2fa": bool(current_user.totp_secret),
        "can_create_documents": user_can_create_documents(current_user, session),
        "default_workspace_id": current_user.default_workspace_id,
    }


# --- User Management Endpoints ---
@router.get("/admin/users", response_model=List[UserRead])
def list_users(
    admin: User = Depends(require_admin), 
    session: Session = Depends(get_session)
):
    """List all users (Admin only)"""
    users = session.exec(select(User)).all()
    return [_user_read_payload(session, user) for user in users]


@router.post("/admin/users", response_model=UserRead)
def create_user(
    request: Request,
    user_data: UserCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new user (Admin only)"""
    # Check if username exists
    existing = session.exec(select(User).where(User.username == user_data.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    new_user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        role="user",
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    session.add(new_user)
    session.flush()
    if new_user.id is None:
        raise RuntimeError("New user has no database ID")
    ensure_default_workspace(session, new_user.id)
    log_audit(
        session,
        admin.id,
        "CREATE_USER",
        f"Created user '{new_user.username}'",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    session.refresh(new_user)
    
    return _user_read_payload(session, new_user)


@router.put("/admin/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    request: Request,
    user_data: UserUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Update a user (Admin only)"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    changes = []
    password_changed = False

    if user.id == admin.id:
        if user_data.role is not None and user_data.role != "admin":
            raise HTTPException(status_code=400, detail="Cannot demote yourself")
        if user_data.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    ensure_active_admin_remains(
        session,
        user,
        proposed_role=user_data.role,
        proposed_is_active=user_data.is_active,
    )
    
    if user_data.username is not None and user_data.username != user.username:
        # Check if new username exists
        existing = session.exec(select(User).where(User.username == user_data.username)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        changes.append(f"username: '{user.username}' -> '{user_data.username}'")
        user.username = user_data.username
    
    if user_data.password is not None:
        user.hashed_password = get_password_hash(user_data.password)
        password_changed = True
        changes.append("password: updated")
    
    if user_data.role is not None and user_data.role != user.role:
        changes.append(f"role: '{user.role}' -> '{user_data.role}'")
        user.role = user_data.role
    
    if user_data.is_active is not None and hasattr(user, 'is_active'):
        if user_data.is_active != user.is_active:
            changes.append(f"is_active: {user.is_active} -> {user_data.is_active}")
            user.is_active = user_data.is_active
    
    if changes:
        session.add(user)
        if password_changed:
            _increment_token_version(session, user)
        log_audit(
            session,
            admin.id,
            "UPDATE_USER",
            f"Updated user '{user.username}': {'; '.join(changes)}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            commit=False,
        )
        session.flush()
        resolve_user_default_workspace(session, user)
        session.commit()
        session.refresh(user)

    return _user_read_payload(session, user)


@router.get(
    "/admin/users/{user_id}/default-workspace-options",
    response_model=List[DefaultWorkspaceOptionRead],
)
def get_default_workspace_options(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """List writable targets while excluding another user's personal area."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    workspaces = session.exec(
        select(ContractList).order_by(col(ContractList.name), col(ContractList.id))
    ).all()
    owner_names = dict(session.exec(select(User.id, User.username)).all())
    return [
        {
            "id": workspace.id,
            "name": workspace.name,
            "owner_user_id": workspace.owner_user_id,
            "owner_username": owner_names.get(workspace.owner_user_id),
            "is_personal": workspace.is_default,
        }
        for workspace in workspaces
        if workspace_can_be_default_for_user(user, workspace, session)
    ]


@router.put(
    "/admin/users/{user_id}/default-workspace",
    response_model=UserRead,
)
def set_default_workspace(
    user_id: int,
    request: Request,
    workspace_data: DefaultWorkspaceUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Set the explicit upload target without changing any permission."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    workspace = (
        session.get(ContractList, workspace_data.list_id)
        if workspace_data.list_id is not None
        else None
    )
    if workspace_data.list_id is not None and workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace is not None and not workspace_can_be_default_for_user(
        user,
        workspace,
        session,
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "The default workspace must be writable and cannot be another "
                "user's personal Default"
            ),
        )

    previous_workspace_id = user.default_workspace_id
    user.default_workspace_id = workspace.id if workspace is not None else None
    session.add(user)
    if workspace is None:
        resolve_user_default_workspace(session, user)
    log_audit(
        session,
        admin.id,
        "SET_DEFAULT_WORKSPACE",
        (
            f"Changed default workspace for '{user.username}' from "
            f"'{previous_workspace_id}' to '{user.default_workspace_id}'"
        ),
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    session.refresh(user)
    return _user_read_payload(session, user)


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Permanently delete a user while preserving anonymized audit history."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    ensure_active_admin_remains(session, user, proposed_is_active=False)

    username = user.username
    replacement_owner_id = admin.id
    if replacement_owner_id is None:
        raise RuntimeError("Replacement owner has no database ID")
    replacement_default = ensure_default_workspace(session, replacement_owner_id)
    if replacement_default.id is None:
        raise RuntimeError("Replacement Default workspace could not be resolved")

    owned_default_ids = list(session.exec(
        select(ContractList.id)
        .where(ContractList.owner_user_id == user_id)
        .where(col(ContractList.is_default).is_(True))
    ).all())
    affected_contract_ids: list[int] = []
    users_needing_default_fallback: list[User] = []
    if owned_default_ids:
        default_users = session.exec(
            select(User).where(col(User.default_workspace_id).in_(owned_default_ids))
        ).all()
        for default_user in default_users:
            default_user.default_workspace_id = None
            session.add(default_user)
            if default_user.id != user_id:
                users_needing_default_fallback.append(default_user)
        session.flush()
        affected_contract_ids = list(session.exec(
            select(ContractListLink.contract_id).where(
                col(ContractListLink.list_id).in_(owned_default_ids)
            )
        ).all())
        session.exec(
            delete(ContractListLink).where(
                col(ContractListLink.list_id).in_(owned_default_ids)
            )
        )
        session.exec(
            delete(ContractListPermission).where(
                col(ContractListPermission.list_id).in_(owned_default_ids)
            )
        )
        session.exec(
            delete(ContractList).where(col(ContractList.id).in_(owned_default_ids))
        )
        session.flush()
        for default_user in users_needing_default_fallback:
            resolve_user_default_workspace(session, default_user)

    session.exec(
        update(Contract)
        .where(Contract.owner_user_id == user_id)
        .values(owner_user_id=replacement_owner_id)
    )
    session.exec(
        update(ContractList)
        .where(ContractList.owner_user_id == user_id)
        .values(owner_user_id=replacement_owner_id)
    )
    session.flush()
    for contract_id in affected_contract_ids:
        if session.exec(
            select(ContractListLink).where(
                col(ContractListLink.contract_id) == contract_id
            )
        ).first() is None:
            session.add(
                ContractListLink(
                    contract_id=contract_id,
                    list_id=replacement_default.id,
                )
            )

    session.exec(
        delete(ContractPermission).where(col(ContractPermission.user_id) == user_id)
    )
    session.exec(
        delete(ContractListPermission).where(
            col(ContractListPermission.user_id) == user_id
        )
    )
    session.exec(
        update(AuditLog)
        .where(AuditLog.user_id == user_id)
        .values(user_id=None)
    )
    session.delete(user)

    log_audit(
        session,
        admin.id,
        "DELETE_USER",
        f"Deleted user '{username}'",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
    )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put('/admin/users/{user_id}/password', status_code=status.HTTP_204_NO_CONTENT)
def update_user_password(
    user_id: int,
    request: Request,
    password_data: UserPasswordUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    '''Reset a user's password without changing other account properties.'''
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    user.hashed_password = get_password_hash(password_data.password)
    session.add(user)
    _increment_token_version(session, user)
    log_audit(
        session,
        admin.id,
        'RESET_USER_PASSWORD',
        f'Reset password for user {user.username!r}',
        request.client.host if request.client else 'unknown',
        request.headers.get('user-agent'),
        commit=False,
    )
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Permission Management Endpoints ---
@router.get("/admin/permissions", response_model=PermissionPage)
def list_permissions(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """List workspace permissions first, followed by document exceptions."""
    workspace_total = int(
        session.exec(
            select(func.count(col(ContractListPermission.id)))
            .join(User, col(User.id) == col(ContractListPermission.user_id))
            .join(
                ContractList,
                col(ContractList.id) == col(ContractListPermission.list_id),
            )
        ).one()
        or 0
    )
    document_total = int(
        session.exec(
            select(func.count(col(ContractPermission.id)))
            .join(User, col(User.id) == col(ContractPermission.user_id))
            .join(Contract, col(Contract.id) == col(ContractPermission.contract_id))
        ).one()
        or 0
    )
    total = workspace_total + document_total
    result: list[dict[str, object]] = []

    if offset < workspace_total:
        workspace_rows = session.exec(
            select(ContractListPermission, User, ContractList)
            .join(User, col(User.id) == col(ContractListPermission.user_id))
            .join(
                ContractList,
                col(ContractList.id) == col(ContractListPermission.list_id),
            )
            .order_by(col(ContractListPermission.id).desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for permission, user, workspace in workspace_rows:
            owner = (
                session.get(User, workspace.owner_user_id)
                if workspace.owner_user_id
                else None
            )
            target_name = (
                f"{workspace.name} · {owner.username}"
                if owner
                else workspace.name
            )
            result.append({
                "id": permission.id,
                "user_id": permission.user_id,
                "scope_type": "workspace",
                "list_id": permission.list_id,
                "permission_level": permission.permission_level,
                "username": user.username,
                "list_name": workspace.name,
                "target_name": target_name,
            })

    remaining = limit - len(result)
    if remaining > 0:
        document_offset = max(offset - workspace_total, 0)
        document_rows = session.exec(
            select(ContractPermission, User, Contract)
            .join(User, col(User.id) == col(ContractPermission.user_id))
            .join(Contract, col(Contract.id) == col(ContractPermission.contract_id))
            .order_by(col(ContractPermission.id).desc())
            .offset(document_offset)
            .limit(remaining)
        ).all()
        for permission, user, contract in document_rows:
            result.append({
                "id": permission.id,
                "user_id": permission.user_id,
                "scope_type": "document",
                "contract_id": permission.contract_id,
                "permission_level": permission.permission_level,
                "username": user.username,
                "contract_title": contract.title,
                "target_name": contract.title,
            })

    return {
        "items": result,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/admin/users/{user_id}/permissions", response_model=List[PermissionRead])
def get_user_permissions(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Get every workspace and document permission for a user."""
    result: list[dict[str, object]] = []
    workspace_rows = session.exec(
        select(ContractListPermission, User, ContractList)
        .join(User, col(User.id) == col(ContractListPermission.user_id))
        .join(
            ContractList,
            col(ContractList.id) == col(ContractListPermission.list_id),
        )
        .where(ContractListPermission.user_id == user_id)
    ).all()
    for permission, user, workspace in workspace_rows:
        owner = (
            session.get(User, workspace.owner_user_id)
            if workspace.owner_user_id
            else None
        )
        target_name = (
            f"{workspace.name} · {owner.username}" if owner else workspace.name
        )
        result.append({
            "id": permission.id,
            "user_id": permission.user_id,
            "scope_type": "workspace",
            "list_id": permission.list_id,
            "permission_level": permission.permission_level,
            "username": user.username,
            "list_name": workspace.name,
            "target_name": target_name,
        })
    document_rows = session.exec(
        select(ContractPermission, User, Contract)
        .join(User, col(User.id) == col(ContractPermission.user_id))
        .join(Contract, col(Contract.id) == col(ContractPermission.contract_id))
        .where(ContractPermission.user_id == user_id)
    ).all()
    for permission, user, contract in document_rows:
        result.append({
            "id": permission.id,
            "user_id": permission.user_id,
            "scope_type": "document",
            "contract_id": permission.contract_id,
            "permission_level": permission.permission_level,
            "username": user.username,
            "contract_title": contract.title,
            "target_name": contract.title,
        })
    return result


@router.post("/admin/permissions", response_model=PermissionRead)
def create_permission(
    request: Request,
    perm_data: PermissionCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new contract permission (Admin only)"""
    # Validate user and contract exist
    user = session.get(User, perm_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    contract = session.get(Contract, perm_data.contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check if permission already exists
    existing = session.exec(
        select(ContractPermission)
        .where(ContractPermission.user_id == perm_data.user_id)
        .where(ContractPermission.contract_id == perm_data.contract_id)
    ).first()
    
    if existing:
        # Update existing permission
        existing.permission_level = perm_data.permission_level
        session.add(existing)
        log_audit(session, admin.id, "UPDATE_PERMISSION", 
                  (
                      f"Updated permission for '{user.username}' on contract "
                      f"'{contract.title}' to '{perm_data.permission_level}'"
                  ),
                  request.client.host if request.client else "unknown", request.headers.get("user-agent"), commit=False)
        session.commit()
        session.refresh(existing)
        
        return {
            "id": existing.id,
            "user_id": existing.user_id,
            "scope_type": "document",
            "contract_id": existing.contract_id,
            "permission_level": existing.permission_level,
            "username": user.username,
            "contract_title": contract.title,
            "target_name": contract.title,
        }
    
    new_perm = ContractPermission(
        user_id=perm_data.user_id,
        contract_id=perm_data.contract_id,
        permission_level=perm_data.permission_level
    )
    session.add(new_perm)
    session.flush()
    log_audit(session, admin.id, "CREATE_PERMISSION", 
              f"Granted '{perm_data.permission_level}' permission to '{user.username}' for contract '{contract.title}'",
              request.client.host if request.client else "unknown", request.headers.get("user-agent"), commit=False)
    session.commit()
    session.refresh(new_perm)
    
    return {
        "id": new_perm.id,
        "user_id": new_perm.user_id,
        "scope_type": "document",
        "contract_id": new_perm.contract_id,
        "permission_level": new_perm.permission_level,
        "username": user.username,
        "contract_title": contract.title,
        "target_name": contract.title,
    }


@router.post("/admin/workspace-permissions", response_model=PermissionRead)
def create_workspace_permission(
    request: Request,
    perm_data: WorkspacePermissionCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Create or update a user's permission for an entire workspace."""
    user = session.get(User, perm_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    workspace = session.get(ContractList, perm_data.list_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    permission = session.exec(
        select(ContractListPermission)
        .where(ContractListPermission.user_id == perm_data.user_id)
        .where(ContractListPermission.list_id == perm_data.list_id)
    ).first()
    action = "UPDATE_WORKSPACE_PERMISSION" if permission else "CREATE_WORKSPACE_PERMISSION"
    if permission:
        permission.permission_level = perm_data.permission_level
    else:
        permission = ContractListPermission(
            user_id=perm_data.user_id,
            list_id=perm_data.list_id,
            permission_level=perm_data.permission_level,
        )
    session.add(permission)
    session.flush()
    resolve_user_default_workspace(session, user)
    log_audit(
        session,
        admin.id,
        action,
        (
            f"Granted '{perm_data.permission_level}' workspace permission to "
            f"'{user.username}' for '{workspace.name}'"
        ),
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    session.refresh(permission)
    owner = (
        session.get(User, workspace.owner_user_id)
        if workspace.owner_user_id
        else None
    )
    target_name = f"{workspace.name} · {owner.username}" if owner else workspace.name
    return {
        "id": permission.id,
        "user_id": permission.user_id,
        "scope_type": "workspace",
        "list_id": permission.list_id,
        "permission_level": permission.permission_level,
        "username": user.username,
        "list_name": workspace.name,
        "target_name": target_name,
    }


@router.delete(
    "/admin/workspace-permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_workspace_permission(
    permission_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    permission = session.get(ContractListPermission, permission_id)
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    user = session.get(User, permission.user_id)
    workspace = session.get(ContractList, permission.list_id)
    session.delete(permission)
    session.flush()
    if user is not None:
        resolve_user_default_workspace(session, user)
    log_audit(
        session,
        admin.id,
        "DELETE_WORKSPACE_PERMISSION",
        (
            f"Revoked workspace permission from "
            f"'{user.username if user else 'Unknown'}' for "
            f"'{workspace.name if workspace else 'Unknown'}'"
        ),
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/admin/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(
    permission_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Delete a contract permission (Admin only)"""
    perm = session.get(ContractPermission, permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    user = session.get(User, perm.user_id)
    contract = session.get(Contract, perm.contract_id)
    
    session.delete(perm)
    log_audit(
        session,
        admin.id,
        "DELETE_PERMISSION",
        (
            f"Revoked permission from '{user.username if user else 'Unknown'}' "
            f"for contract '{contract.title if contract else 'Unknown'}'"
        ),
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ========================================
#           CONTRACT LISTS ENDPOINTS
# ========================================
