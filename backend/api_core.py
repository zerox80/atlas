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
from sqlalchemy import and_, exists, false, func, insert, literal, or_, select as sa_select, true
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
    ContractListPermission,
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
DEFAULT_WORKSPACE_NAME = "Default"

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


def strongest_permission_level(levels: Sequence[str | None]) -> str | None:
    """Return the strongest valid permission from multiple independent grants."""
    strongest = max(
        levels,
        key=lambda level: PERMISSION_LEVEL_RANK.get(level or "", 0),
        default=None,
    )
    return strongest if strongest in PERMISSION_LEVEL_RANK else None


def workspace_permission_level(
    user: User,
    list_id: int,
    session: Session,
) -> str | None:
    """Load the caller's explicit permission for one workspace."""
    if user.role == "admin":
        return "full"
    if user.id is None:
        return None

    permission = session.exec(
        select(ContractListPermission)
        .where(ContractListPermission.user_id == user.id)
        .where(ContractListPermission.list_id == list_id)
    ).first()
    return permission.permission_level if permission else None


def check_workspace_permission(
    user: User,
    list_id: int,
    required_level: PermissionLevel,
    session: Session,
) -> bool:
    return permission_grants(
        workspace_permission_level(user, list_id, session),
        required_level,
    )


def user_can_create_documents(user: User, session: Session) -> bool:
    """Uploads require write access to at least one target workspace."""
    if user.role == "admin":
        return True
    if user.id is None:
        return False
    permission_id = session.exec(
        select(ContractListPermission.id)
        .join(
            ContractList,
            col(ContractList.id) == col(ContractListPermission.list_id),
        )
        .where(ContractListPermission.user_id == user.id)
        .where(
            col(ContractListPermission.permission_level).in_(
                allowed_permission_levels("write")
            )
        )
        .where(
            or_(
                col(ContractList.is_default).is_(False),
                ContractList.owner_user_id == user.id,
            )
        )
        .limit(1)
    ).first()
    return permission_id is not None


def ensure_default_workspace(session: Session, owner_user_id: int) -> ContractList:
    """Return one user's isolated Default workspace."""
    workspace = session.exec(
        select(ContractList)
        .where(col(ContractList.is_default).is_(True))
        .where(ContractList.owner_user_id == owner_user_id)
        .order_by(col(ContractList.id))
    ).first()
    created = False
    if workspace is None:
        workspace = ContractList(
            owner_user_id=owner_user_id,
            name=DEFAULT_WORKSPACE_NAME,
            description="Persönlicher Standard-Workspace",
            color="#6366f1",
            is_default=True,
        )
        session.add(workspace)
        session.flush()
        created = True

    if workspace.name != DEFAULT_WORKSPACE_NAME:
        workspace.name = DEFAULT_WORKSPACE_NAME
        session.add(workspace)
        session.flush()
    if created:
        session.add(
            ContractListPermission(
                user_id=owner_user_id,
                list_id=workspace.id,
                permission_level="full",
            )
        )
        owner = session.get(User, owner_user_id)
        if owner is not None and owner.default_workspace_id is None:
            owner.default_workspace_id = workspace.id
            session.add(owner)
        session.flush()
    return workspace


def workspace_can_be_default_for_user(
    user: User,
    workspace: ContractList,
    session: Session,
) -> bool:
    """A default target must be writable and never another user's personal area."""
    if workspace.id is None or user.id is None:
        return False
    if workspace.is_default and workspace.owner_user_id != user.id:
        return False
    return check_workspace_permission(user, workspace.id, "write", session)


def resolve_user_default_workspace(
    session: Session,
    user: User,
) -> ContractList | None:
    """Resolve the explicit target, safely falling back to the personal workspace."""
    preferred = (
        session.get(ContractList, user.default_workspace_id)
        if user.default_workspace_id is not None
        else None
    )
    if preferred is not None and workspace_can_be_default_for_user(
        user,
        preferred,
        session,
    ):
        return preferred

    personal = ensure_default_workspace(session, user.id) if user.id is not None else None
    fallback = (
        personal
        if personal is not None
        and workspace_can_be_default_for_user(user, personal, session)
        else None
    )
    fallback_id = fallback.id if fallback is not None else None
    if user.default_workspace_id != fallback_id:
        user.default_workspace_id = fallback_id
        session.add(user)
        session.flush()
    return fallback


def backfill_default_workspace_links(session: Session) -> int:
    """Create personal Defaults and attach orphaned documents by owner."""
    users = session.exec(select(User).order_by(col(User.id))).all()
    fallback_owner_id = next(
        (user.id for user in users if user.role == "admin" and user.id is not None),
        next((user.id for user in users if user.id is not None), None),
    )
    defaults_by_owner: dict[int, ContractList] = {}
    for user in users:
        if user.id is not None:
            defaults_by_owner[user.id] = ensure_default_workspace(session, user.id)

    # Keep a valid explicit selection, but never infer a shared workspace from
    # permissions. Invalid selections fall back only to the user's own area.
    for user in users:
        resolve_user_default_workspace(session, user)

    orphaned_contracts = session.exec(
        select(Contract)
        .where(
            ~exists(
                sa_select(1)
                .select_from(ContractListLink.__table__)
                .where(ContractListLink.contract_id == Contract.id)
            )
        )
    ).all()
    created = 0
    for contract in orphaned_contracts:
        owner_id = contract.owner_user_id or fallback_owner_id
        if owner_id is None:
            continue
        if contract.owner_user_id is None:
            contract.owner_user_id = owner_id
            session.add(contract)
        default_workspace = defaults_by_owner.get(owner_id)
        if default_workspace is None:
            default_workspace = ensure_default_workspace(session, owner_id)
            defaults_by_owner[owner_id] = default_workspace
        if default_workspace.id is None:
            raise RuntimeError("Default workspace could not be created")
        session.add(
            ContractListLink(
                contract_id=contract.id,
                list_id=default_workspace.id,
            )
        )
        created += 1
    session.commit()
    return created


def _contract_access_context(
    user: User,
    contract_id: int,
    session: Session,
) -> tuple[str | None, set[int] | None]:
    """Resolve effective access and which workspace names may be disclosed."""
    if user.role == "admin":
        return "full", None
    if user.id is None:
        return None, set()

    direct = session.exec(
        select(ContractPermission.permission_level)
        .where(ContractPermission.user_id == user.id)
        .where(ContractPermission.contract_id == contract_id)
    ).first()
    workspace_rows = session.exec(
        select(
            ContractListPermission.list_id,
            ContractListPermission.permission_level,
        )
        .join(
            ContractListLink,
            col(ContractListLink.list_id) == col(ContractListPermission.list_id),
        )
        .where(ContractListPermission.user_id == user.id)
        .where(ContractListLink.contract_id == contract_id)
    ).all()
    effective_level = strongest_permission_level(
        [direct, *(permission_level for _, permission_level in workspace_rows)]
    )
    visible_list_ids = (
        None
        if permission_grants(direct, "read")
        else {
            list_id
            for list_id, permission_level in workspace_rows
            if permission_grants(permission_level, "read")
        }
    )
    return effective_level, visible_list_ids


def contract_permission_level(
    user: User,
    contract_id: int,
    session: Session,
) -> str | None:
    """Load the strongest direct or workspace permission for a contract."""
    return _contract_access_context(user, contract_id, session)[0]


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
_VISIBLE_LISTS_NOT_LOADED = object()


def contract_read_for_user(
    contract: Contract,
    user: User,
    session: Session,
    assigned_level: str | None | object = _PERMISSION_NOT_LOADED,
    visible_list_ids: set[int] | None | object = _VISIBLE_LISTS_NOT_LOADED,
) -> dict[str, object]:
    """Serialize a contract with the caller's effective capabilities."""
    data = ContractRead.model_validate(contract).model_dump()
    data["business_timezone"] = BUSINESS_TIMEZONE_NAME
    if (
        assigned_level is _PERMISSION_NOT_LOADED
        or visible_list_ids is _VISIBLE_LISTS_NOT_LOADED
    ):
        resolved_level, resolved_visible_lists = (
            _contract_access_context(user, contract.id, session)
            if contract.id is not None
            else (None, set())
        )
        if assigned_level is _PERMISSION_NOT_LOADED:
            assigned_level = resolved_level
        if visible_list_ids is _VISIBLE_LISTS_NOT_LOADED:
            visible_list_ids = resolved_visible_lists
    effective_level = assigned_level if isinstance(assigned_level, str) else None
    if isinstance(visible_list_ids, set):
        data["lists"] = [
            workspace
            for workspace in data.get("lists", [])
            if workspace.get("id") in visible_list_ids
        ]
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
            contract_read_for_user(contract, user, session, "full", None)
            for contract in contracts
        ]

    contract_ids = [contract.id for contract in contracts if contract.id is not None]
    direct_permissions_by_contract: dict[int, str] = {}
    workspace_permissions_by_contract: dict[int, list[tuple[int, str]]] = {}
    if user.id is not None and contract_ids:
        permissions = session.exec(
            select(ContractPermission)
            .where(ContractPermission.user_id == user.id)
            .where(col(ContractPermission.contract_id).in_(contract_ids))
        ).all()
        direct_permissions_by_contract = {
            permission.contract_id: permission.permission_level
            for permission in permissions
        }
        workspace_permissions = session.exec(
            select(
                ContractListLink.contract_id,
                ContractListPermission.list_id,
                ContractListPermission.permission_level,
            )
            .join(
                ContractListPermission,
                col(ContractListPermission.list_id) == col(ContractListLink.list_id),
            )
            .where(ContractListPermission.user_id == user.id)
            .where(col(ContractListLink.contract_id).in_(contract_ids))
        ).all()
        for contract_id, list_id, permission_level in workspace_permissions:
            workspace_permissions_by_contract.setdefault(contract_id, []).append(
                (list_id, permission_level)
            )

    result: list[dict[str, object]] = []
    for contract in contracts:
        direct_level = (
            direct_permissions_by_contract.get(contract.id)
            if contract.id is not None
            else None
        )
        workspace_levels = (
            workspace_permissions_by_contract.get(contract.id, [])
            if contract.id is not None
            else []
        )
        effective_level = strongest_permission_level(
            [direct_level, *(level for _, level in workspace_levels)]
        )
        visible_list_ids = (
            None
            if permission_grants(direct_level, "read")
            else {
                list_id
                for list_id, level in workspace_levels
                if permission_grants(level, "read")
            }
        )
        result.append(
            contract_read_for_user(
                contract,
                user,
                session,
                effective_level,
                visible_list_ids,
            )
        )
    return result


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
    list_id: int | None = None,
):
    """Apply direct and workspace ACLs to a statement containing Contract."""
    if user.role == "admin":
        return statement
    if user.id is None:
        return statement.where(false())

    contract_permissions = ContractPermission.__table__
    direct_permission_exists = exists(
        sa_select(1)
        .select_from(contract_permissions)
        .where(
            contract_permissions.c.contract_id == Contract.id,
            contract_permissions.c.user_id == user.id,
            contract_permissions.c.permission_level.in_(
                allowed_permission_levels(required_level)
            ),
        )
    )

    list_permissions = ContractListPermission.__table__
    list_links = ContractListLink.__table__
    workspace_conditions = [
        list_links.c.contract_id == Contract.id,
        list_permissions.c.user_id == user.id,
        list_permissions.c.permission_level.in_(
            allowed_permission_levels(required_level)
        ),
    ]
    if list_id is not None:
        # A request scoped to workspace B must not inherit access through A.
        workspace_conditions.append(list_permissions.c.list_id == list_id)
        workspace_conditions.append(list_links.c.list_id == list_id)

    workspace_permission_exists = exists(
        sa_select(1)
        .select_from(
            list_permissions.join(
                list_links,
                list_links.c.list_id == list_permissions.c.list_id,
            )
        )
        .where(*workspace_conditions)
    )
    return statement.where(
        or_(direct_permission_exists, workspace_permission_exists)
    )


def direct_visible_contract_count_for_list(
    list_id: int,
    user: User,
    session: Session,
) -> int:
    if user.id is None:
        return 0
    statement = (
        select(func.count(func.distinct(ContractListLink.contract_id)))
        .join(
            ContractPermission,
            col(ContractPermission.contract_id) == col(ContractListLink.contract_id),
        )
        .where(col(ContractListLink.list_id) == list_id)
        .where(col(ContractPermission.user_id) == user.id)
        .where(
            col(ContractPermission.permission_level).in_(
                allowed_permission_levels("read")
            )
        )
    )
    return session.exec(statement).one() or 0


def visible_contract_count_for_list(
    list_id: int,
    user: User,
    session: Session,
) -> int:
    if user.role != "admin" and not check_workspace_permission(
        user,
        list_id,
        "read",
        session,
    ):
        return direct_visible_contract_count_for_list(list_id, user, session)

    statement = (
        select(func.count(func.distinct(ContractListLink.contract_id)))
        .where(col(ContractListLink.list_id) == list_id)
    )
    return session.exec(statement).one() or 0


def get_visible_list_or_404(
    list_id: int,
    user: User,
    session: Session,
) -> ContractList:
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    has_workspace_access = check_workspace_permission(user, list_id, "read", session)
    has_direct_document_access = (
        direct_visible_contract_count_for_list(list_id, user, session) > 0
    )
    if user.role != "admin" and not (
        has_workspace_access or has_direct_document_access
    ):
        raise HTTPException(status_code=404, detail="List not found")

    return lst
