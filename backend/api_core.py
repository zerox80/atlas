"""Shared dependencies and authorization helpers for the API routers."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Annotated, Literal, TypeAlias

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlmodel import Session, col, select

from auth import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY, get_password_hash
from database import get_session
from models import (
    AuditLog,
    Contract,
    ContractList,
    ContractListLink,
    ContractPermission,
    User,
)
from schemas import ContractRead

logger = logging.getLogger(__name__)

PermissionLevel: TypeAlias = Literal["read", "write", "full"]
PERMISSION_LEVEL_RANK: dict[str, int] = {
    "read": 1,
    "write": 2,
    "full": 3,
}

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
            logger.warning(
                "Existing admin user found; ADMIN_PASSWORD is ignored after bootstrap."
            )
        return

    admin_pw = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(16)
    if not os.getenv("ADMIN_PASSWORD"):
        logger.warning(
            "ADMIN_PASSWORD is not set; generated temporary admin password: %s",
            admin_pw,
        )

    admin_user = User(
        username="admin",
        hashed_password=get_password_hash(admin_pw),
        role="admin",
        is_active=True,
    )
    session.add(admin_user)
    session.commit()


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    access_token: Annotated[str | None, Cookie()] = None,
    session: Session = Depends(get_session),
) -> User:
    """Resolve and validate the authenticated user from cookie or bearer token."""
    final_token = access_token or token

    if not final_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from error

    username = payload.get("sub")
    if not isinstance(username, str) or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an active administrator for an endpoint."""
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
    proposed_role: str | None = None,
    proposed_is_active: bool | None = None,
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


def permission_grants(
    assigned_level: str | None,
    required_level: PermissionLevel,
) -> bool:
    """Return whether an assigned permission satisfies a required level."""
    assigned_rank = PERMISSION_LEVEL_RANK.get(assigned_level or "", 0)
    return assigned_rank >= PERMISSION_LEVEL_RANK[required_level]


def contract_permission_level(
    user: User,
    contract_id: int,
    session: Session,
) -> str | None:
    """Load the caller's effective permission level for a contract."""
    if user.role == "admin":
        return "full"
    if user.id is None:
        return None

    permission = session.exec(
        select(ContractPermission)
        .where(ContractPermission.user_id == user.id)
        .where(ContractPermission.contract_id == contract_id)
    ).first()
    return permission.permission_level if permission else None


def check_contract_permission(
    user: User,
    contract_id: int,
    required_level: PermissionLevel,
    session: Session,
) -> bool:
    """Check if user has the required explicit permission level for a contract."""
    assigned_level = contract_permission_level(user, contract_id, session)
    return permission_grants(assigned_level, required_level)


def contract_read_for_user(
    contract: Contract,
    user: User,
    session: Session,
) -> dict[str, object]:
    """Serialize a contract with the caller's effective capabilities."""
    data = ContractRead.model_validate(contract).model_dump()
    assigned_level = (
        contract_permission_level(user, contract.id, session)
        if contract.id is not None
        else None
    )
    data["can_read"] = permission_grants(assigned_level, "read")
    data["can_write"] = permission_grants(assigned_level, "write")
    can_manage = permission_grants(assigned_level, "full")
    data["can_delete"] = can_manage
    data["can_manage_protection"] = can_manage
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
    existing_pairs = {
        (user_id, contract_id)
        for user_id, contract_id in session.exec(
            select(ContractPermission.user_id, ContractPermission.contract_id)
        ).all()
    }

    created = 0
    for contract in contracts:
        if contract.id is None:
            continue
        for user in users:
            if user.id is None:
                continue
            permission_key = (user.id, contract.id)
            if permission_key in existing_pairs:
                continue

            session.add(
                ContractPermission(
                    user_id=user.id,
                    contract_id=contract.id,
                    permission_level="read",
                )
            )
            existing_pairs.add(permission_key)
            created += 1

    session.add(
        AuditLog(
            user_id=None,
            action=ACL_BACKFILL_ACTION,
            details=f"Granted read access for {created} existing user-contract pairs.",
        )
    )
    session.commit()

    if created:
        logger.info(
            "Granted read access for %d existing user-contract pairs.",
            created,
        )

    return created


def allowed_permission_levels(
    required_level: PermissionLevel,
) -> tuple[str, ...]:
    """Return every persisted permission level satisfying the requirement."""
    required_rank = PERMISSION_LEVEL_RANK[required_level]
    return tuple(
        level
        for level, rank in PERMISSION_LEVEL_RANK.items()
        if rank >= required_rank
    )


def filter_contracts_for_user(
    statement,
    user: User,
    required_level: PermissionLevel = "read",
):
    """Apply contract ACLs to a select statement that includes Contract."""
    if user.role == "admin":
        return statement

    return (
        statement
        .join(
            ContractPermission,
            col(ContractPermission.contract_id) == col(Contract.id),
        )
        .where(col(ContractPermission.user_id) == user.id)
        .where(
            col(ContractPermission.permission_level).in_(
                allowed_permission_levels(required_level)
            )
        )
    )


def visible_contract_count_for_list(
    list_id: int,
    user: User,
    session: Session,
) -> int:
    statement = (
        select(func.count(func.distinct(ContractListLink.contract_id)))
        .join(Contract, col(Contract.id) == col(ContractListLink.contract_id))
        .where(col(ContractListLink.list_id) == list_id)
    )
    statement = filter_contracts_for_user(statement, user, "read")
    return session.exec(statement).one() or 0


def get_visible_list_or_404(
    list_id: int,
    user: User,
    session: Session,
) -> ContractList:
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    if (
        user.role != "admin"
        and visible_contract_count_for_list(list_id, user, session) == 0
    ):
        raise HTTPException(status_code=404, detail="List not found")

    return lst
