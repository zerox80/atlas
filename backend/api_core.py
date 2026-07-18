"""Shared dependencies and authorization helpers for the API routers."""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Sequence
from typing import Annotated, Literal, TypeAlias

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import and_, exists, func, insert, literal, select as sa_select, true
from sqlmodel import Session, col, select

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    SECRET_KEY,
    TOKEN_VERSION_CLAIM,
    get_password_hash,
)
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
SECURE_COOKIES = os.getenv("SECURE_COOKIES", str(PRODUCTION_MODE)).lower() == "true"
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
ACL_BACKFILL_ACTION = "ACL_BACKFILL_V1"
BUSINESS_TIMEZONE_NAME = os.getenv("BUSINESS_TIMEZONE", "Europe/Berlin")
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
    """Decide whether authentication cookies must carry the Secure attribute."""
    return SECURE_COOKIES or request.url.scheme == "https"


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

    configured_password = os.getenv("ADMIN_PASSWORD")
    if not configured_password or len(configured_password) < 12:
        raise RuntimeError(
            "ADMIN_PASSWORD must contain at least 12 characters for initial admin bootstrap."
        )

    admin_user = User(
        username="admin",
        hashed_password=get_password_hash(configured_password),
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

    auth_subject = payload.get("sub")
    if not isinstance(auth_subject, str) or not auth_subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    token_version = payload.get(TOKEN_VERSION_CLAIM)
    if type(token_version) is not int:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
        )

    user = session.exec(
        select(User).where(User.auth_subject == auth_subject)
    ).first()
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
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
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


_PERMISSION_NOT_LOADED = object()


def contract_read_for_user(
    contract: Contract,
    user: User,
    session: Session,
    assigned_level: str | None | object = _PERMISSION_NOT_LOADED,
) -> dict[str, object]:
    """Serialize a contract with the caller's effective capabilities."""
    data = ContractRead.model_validate(contract).model_dump()
    data["business_timezone"] = BUSINESS_TIMEZONE_NAME
    if assigned_level is _PERMISSION_NOT_LOADED:
        assigned_level = (
            contract_permission_level(user, contract.id, session)
            if contract.id is not None
            else None
        )
    effective_level = assigned_level if isinstance(assigned_level, str) else None
    data["can_read"] = permission_grants(effective_level, "read")
    data["can_write"] = permission_grants(effective_level, "write")
    can_manage = permission_grants(effective_level, "full")
    data["can_delete"] = can_manage
    data["can_manage_protection"] = can_manage
    return data


def contract_reads_for_user(
    contracts: Sequence[Contract],
    user: User,
    session: Session,
) -> list[dict[str, object]]:
    """Serialize many contracts while loading ACLs in a single query."""
    if user.role == "admin":
        return [
            contract_read_for_user(contract, user, session, "full")
            for contract in contracts
        ]

    contract_ids = [contract.id for contract in contracts if contract.id is not None]
    permissions_by_contract: dict[int, str] = {}
    if user.id is not None and contract_ids:
        permissions = session.exec(
            select(ContractPermission)
            .where(ContractPermission.user_id == user.id)
            .where(col(ContractPermission.contract_id).in_(contract_ids))
        ).all()
        permissions_by_contract = {
            permission.contract_id: permission.permission_level
            for permission in permissions
        }

    return [
        contract_read_for_user(
            contract,
            user,
            session,
            permissions_by_contract.get(contract.id) if contract.id is not None else None,
        )
        for contract in contracts
    ]


def backfill_existing_contract_read_permissions(session: Session) -> int:
    """Preserve pre-ACL read access for contracts that existed before this rollout."""
    already_ran = session.exec(
        select(AuditLog).where(AuditLog.action == ACL_BACKFILL_ACTION)
    ).first()
    if already_ran:
        return 0

    users = User.__table__
    contracts = Contract.__table__
    permissions = ContractPermission.__table__
    permission_exists = exists(
        sa_select(1)
        .select_from(permissions)
        .where(
            and_(
                permissions.c.user_id == users.c.id,
                permissions.c.contract_id == contracts.c.id,
            )
        )
    )
    insert_missing_permissions = insert(permissions).from_select(
        ["user_id", "contract_id", "permission_level"],
        sa_select(users.c.id, contracts.c.id, literal("read"))
        .select_from(users.join(contracts, true()))
        .where(users.c.role != "admin")
        .where(users.c.is_active.is_(True))
        .where(~permission_exists),
    )
    result = session.execute(insert_missing_permissions)
    created = max(result.rowcount or 0, 0)

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
