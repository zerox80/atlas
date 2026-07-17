"""Shared dependencies and authorization helpers for the API routers."""

from __future__ import annotations

import os
import secrets
from typing import Annotated, List, Optional

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlmodel import Session, col, select

from auth import ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash
from database import get_session
from models import AuditLog, Contract, ContractList, ContractListLink, ContractPermission, User
from schemas import ContractRead

PRODUCTION_MODE = os.getenv("PRODUCTION", "false").lower() == "true"
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
ACL_BACKFILL_ACTION = "ACL_BACKFILL_V1"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_EXEMPT_PATHS = {"/token", "/csrf-token"}
MISTRAL_DOCUMENT_PROCESSING_ENABLED = (
    os.getenv("MISTRAL_DOCUMENT_PROCESSING_ENABLED", "true").lower() == "true"
)
AI_SUPPORTED_FILE_EXTENSION = ".pdf"

limiter = Limiter(key_func=get_remote_address)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def request_is_https(request: Request) -> bool:
    """Detect HTTPS when running behind a reverse proxy."""
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def set_csrf_cookie(response: Response, request: Request) -> str:
    """Set a readable CSRF cookie used with the HttpOnly auth cookie."""
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=request_is_https(request),
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return csrf_token



def bootstrap_admin_user(session: Session) -> None:
    """Create the initial admin account without resetting existing credentials."""
    user = session.exec(select(User).where(User.username == "admin")).first()
    if user:
        if os.getenv("ADMIN_PASSWORD"):
            print("Existing admin user found. ADMIN_PASSWORD is ignored after bootstrap.")
        return

    admin_pw = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(16)
    if not os.getenv("ADMIN_PASSWORD"):
        print(f"\n[SECURITY ALERT] ADMIN_PASSWORD not set. Generated temporary password: {admin_pw}\n")

    admin_user = User(
        username="admin",
        hashed_password=get_password_hash(admin_pw),
        role="admin",
        is_active=True,
    )
    session.add(admin_user)
    session.commit()

async def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)] = None, 
    access_token: Annotated[Optional[str], Cookie()] = None,
    session: Session = Depends(get_session)
):
    # Prioritize Cookie, fall back to Header (for API testing tools if needed, but we can enforce Cookie)
    final_token = access_token if access_token else token
    
    if not final_token:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    from jose import JWTError, jwt
    from auth import SECRET_KEY, ALGORITHM
    from schemas import TokenData
    
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        token_data = TokenData(username=username)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        
    user = session.exec(select(User).where(User.username == token_data.username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is deactivated")
    return user


# Helper dependency for admin-only endpoints
def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def active_admin_count(session: Session) -> int:
    count = session.exec(
        select(func.count(col(User.id)))
        .where(col(User.role) == "admin")
        .where(col(User.is_active).is_(True))
    ).one()
    return int(count or 0)


def ensure_active_admin_remains(
    session: Session,
    user: User,
    proposed_role: Optional[str] = None,
    proposed_is_active: Optional[bool] = None,
) -> None:
    current_is_active = bool(getattr(user, "is_active", True))
    next_role = proposed_role if proposed_role is not None else user.role
    next_is_active = proposed_is_active if proposed_is_active is not None else current_is_active

    removes_active_admin = (
        user.role == "admin"
        and current_is_active
        and (next_role != "admin" or not next_is_active)
    )
    if removes_active_admin and active_admin_count(session) <= 1:
        raise HTTPException(status_code=400, detail="At least one active admin must remain")



# Helper to check contract permission
def check_contract_permission(user: User, contract_id: int, required_level: str, session: Session) -> bool:
    """Check if user has the required explicit permission level for a contract."""
    if user.role == "admin":
        return True
    
    permission = session.exec(
        select(ContractPermission)
        .where(ContractPermission.user_id == user.id)
        .where(ContractPermission.contract_id == contract_id)
    ).first()
    
    if not permission:
        return False
    
    level_hierarchy = {"read": 1, "write": 2, "full": 3}
    return level_hierarchy.get(permission.permission_level, 0) >= level_hierarchy.get(required_level, 0)


def contract_read_for_user(contract: Contract, user: User, session: Session) -> dict:
    """Serialize a contract with the caller's effective capabilities."""
    data = ContractRead.model_validate(contract).model_dump()
    can_full = check_contract_permission(user, contract.id, "full", session) if contract.id is not None else False
    data["can_read"] = (
        check_contract_permission(user, contract.id, "read", session)
        if contract.id is not None
        else False
    )
    data["can_write"] = (
        check_contract_permission(user, contract.id, "write", session)
        if contract.id is not None
        else False
    )
    data["can_delete"] = can_full
    data["can_manage_protection"] = can_full
    return data


def backfill_existing_contract_read_permissions(session: Session) -> int:
    """Preserve pre-ACL read access for contracts that existed before this rollout."""
    already_ran = session.exec(
        select(AuditLog).where(AuditLog.action == ACL_BACKFILL_ACTION)
    ).first()
    if already_ran:
        return 0

    contracts = session.exec(select(Contract)).all()
    users = session.exec(
        select(User)
        .where(col(User.role) != "admin")
        .where(col(User.is_active).is_(True))
    ).all()

    created = 0
    for contract in contracts:
        if contract.id is None:
            continue
        for user in users:
            if user.id is None:
                continue
            existing_permission = session.exec(
                select(ContractPermission)
                .where(ContractPermission.user_id == user.id)
                .where(ContractPermission.contract_id == contract.id)
            ).first()
            if existing_permission:
                continue

            session.add(ContractPermission(
                user_id=user.id,
                contract_id=contract.id,
                permission_level="read",
            ))
            created += 1

    session.add(AuditLog(
        user_id=None,
        action=ACL_BACKFILL_ACTION,
        details=f"Granted read access for {created} existing user-contract pairs.",
    ))
    session.commit()

    if created:
        print(f"[ACL_BACKFILL] Granted read access for {created} existing user-contract pairs.")

    return created


def allowed_permission_levels(required_level: str) -> List[str]:
    level_hierarchy = {"read": 1, "write": 2, "full": 3}
    required_rank = level_hierarchy.get(required_level, 0)
    return [level for level, rank in level_hierarchy.items() if rank >= required_rank]


def filter_contracts_for_user(statement, user: User, required_level: str = "read"):
    """Apply contract ACLs to a select statement that includes Contract."""
    if user.role == "admin":
        return statement

    return (
        statement
        .join(ContractPermission, col(ContractPermission.contract_id) == col(Contract.id))
        .where(col(ContractPermission.user_id) == user.id)
        .where(col(ContractPermission.permission_level).in_(allowed_permission_levels(required_level)))
    )


def visible_contract_count_for_list(list_id: int, user: User, session: Session) -> int:
    statement = (
        select(func.count(func.distinct(ContractListLink.contract_id)))
        .join(Contract, col(Contract.id) == col(ContractListLink.contract_id))
        .where(col(ContractListLink.list_id) == list_id)
    )
    statement = filter_contracts_for_user(statement, user, "read")
    return session.exec(statement).one() or 0


def get_visible_list_or_404(list_id: int, user: User, session: Session) -> ContractList:
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    if user.role != "admin" and visible_contract_count_for_list(list_id, user, session) == 0:
        raise HTTPException(status_code=404, detail="List not found")

    return lst



