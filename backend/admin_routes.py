"""Current-user, user administration, and permission routes."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import update
from sqlmodel import Session, col, delete, select

from api_core import ensure_active_admin_remains, get_current_user, require_admin
from auth import get_password_hash
from database import get_session
from models import AuditLog, Contract, ContractPermission, User
from schemas import (
    PermissionCreate,
    PermissionRead,
    UserCreate,
    UserPasswordUpdate,
    UserRead,
    UserUpdate,
)
from security_utils import log_audit

router = APIRouter()


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
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "has_2fa": bool(current_user.totp_secret)
    }


# --- User Management Endpoints ---
@router.get("/admin/users", response_model=List[UserRead])
def list_users(
    admin: User = Depends(require_admin), 
    session: Session = Depends(get_session)
):
    """List all users (Admin only)"""
    users = session.exec(select(User)).all()
    result = []
    for u in users:
        user_dict = {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active if hasattr(u, 'is_active') else True,
            "created_at": u.created_at if hasattr(u, 'created_at') else datetime.now(timezone.utc),
            "has_2fa": bool(u.totp_secret)
        }
        result.append(user_dict)
    return result


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
    
    return {
        "id": new_user.id,
        "username": new_user.username,
        "role": new_user.role,
        "is_active": new_user.is_active,
        "created_at": new_user.created_at,
        "has_2fa": False
    }


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
        session.commit()
        session.refresh(user)
    
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active if hasattr(user, 'is_active') else True,
        "created_at": user.created_at if hasattr(user, 'created_at') else datetime.now(timezone.utc),
        "has_2fa": bool(user.totp_secret)
    }


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
    session.exec(
        delete(ContractPermission).where(col(ContractPermission.user_id) == user_id)
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
@router.get("/admin/permissions", response_model=List[PermissionRead])
def list_permissions(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """List all contract permissions (Admin only)"""
    rows = session.exec(
        select(ContractPermission, User, Contract)
        .join(User, col(User.id) == col(ContractPermission.user_id))
        .join(Contract, col(Contract.id) == col(ContractPermission.contract_id))
    ).all()
    result = []
    for permission, user, contract in rows:
        result.append({
            "id": permission.id,
            "user_id": permission.user_id,
            "contract_id": permission.contract_id,
            "permission_level": permission.permission_level,
            "username": user.username,
            "contract_title": contract.title,
        })
    return result


@router.get("/admin/users/{user_id}/permissions", response_model=List[PermissionRead])
def get_user_permissions(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Get all permissions for a specific user (Admin only)"""
    rows = session.exec(
        select(ContractPermission, User, Contract)
        .join(User, col(User.id) == col(ContractPermission.user_id))
        .join(Contract, col(Contract.id) == col(ContractPermission.contract_id))
        .where(ContractPermission.user_id == user_id)
    ).all()
    result = []
    for permission, user, contract in rows:
        result.append({
            "id": permission.id,
            "user_id": permission.user_id,
            "contract_id": permission.contract_id,
            "permission_level": permission.permission_level,
            "username": user.username,
            "contract_title": contract.title,
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
            "contract_id": existing.contract_id,
            "permission_level": existing.permission_level,
            "username": user.username,
            "contract_title": contract.title
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
        "contract_id": new_perm.contract_id,
        "permission_level": new_perm.permission_level,
        "username": user.username,
        "contract_title": contract.title
    }


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
