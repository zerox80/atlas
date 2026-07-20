"""Shared SQL query construction for contract collections."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from api_core import filter_contracts_for_user
from database import IS_SQLITE
from models import Contract, ContractListLink, ContractTagLink, Tag, User

from .business_time import business_day_start_utc, contract_state_condition


CONTRACT_SORT_COLUMNS: dict[str, Any] = {
    "title": col(Contract.title),
    "value": col(Contract.value),
    "start_date": col(Contract.start_date),
    "end_date": col(Contract.end_date),
    "uploaded_at": col(Contract.uploaded_at),
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _case_insensitive_contains(column, value: str):
    """Build a contains predicate with Unicode-aware SQLite case folding."""
    if IS_SQLITE:
        expression = func.unicode_casefold(column)
        normalized_value = value.casefold()
    else:
        expression = func.lower(column)
        normalized_value = value.lower()
    return expression.like(f"%{_escape_like(normalized_value)}%", escape="\\")


def build_contract_query(
    current_user: User,
    q: Optional[str] = None,
    tags: Optional[str] = None,
    list_id: Optional[int] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    start_date_from: Optional[datetime] = None,
    start_date_to: Optional[datetime] = None,
    status_filter: Optional[str] = None,
    state_filter: Optional[Literal["active", "attention", "expired"]] = None,
    document_type: Optional[str] = None,
    is_protected: Optional[bool] = None,
    sort_by: Optional[str] = "uploaded_at",
    sort_order: Optional[str] = "desc",
    cursor_uploaded_at: Optional[datetime] = None,
    cursor_id: Optional[int] = None,
    load_relationships: bool = True,
):
    """Build the shared filtered contract query used by list and export endpoints."""
    statement = select(Contract)

    if document_type in {"contract", "invoice"}:
        statement = statement.where(col(Contract.document_type) == document_type)
    if is_protected is not None:
        statement = statement.where(col(Contract.is_protected) == is_protected)

    if q:
        matching_tag_contracts = (
            select(ContractTagLink.contract_id)
            .join(Tag, col(Tag.id) == col(ContractTagLink.tag_id))
            .where(_case_insensitive_contains(col(Tag.name), q))
        )
        statement = statement.where(
            or_(
                _case_insensitive_contains(col(Contract.title), q),
                _case_insensitive_contains(col(Contract.description), q),
                col(Contract.id).in_(matching_tag_contracts),
            )
        )

    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if tag_list:
            statement = statement.join(ContractTagLink).join(Tag).where(
                col(Tag.name).in_(tag_list)
            )

    if list_id is not None:
        statement = statement.join(ContractListLink).where(
            ContractListLink.list_id == list_id
        )
    if min_value is not None:
        statement = statement.where(Contract.value >= min_value)
    if max_value is not None:
        statement = statement.where(Contract.value <= max_value)
    if start_date_from:
        statement = statement.where(
            col(Contract.start_date).is_not(None),
            col(Contract.start_date) >= start_date_from,
        )
    if start_date_to:
        statement = statement.where(
            col(Contract.start_date).is_not(None),
            col(Contract.start_date) <= start_date_to,
        )

    now = datetime.now(timezone.utc)
    today_start = business_day_start_utc(now)
    if status_filter == "active":
        statement = statement.where(
            or_(col(Contract.end_date).is_(None), col(Contract.end_date) >= today_start)
        )
    elif status_filter == "expired":
        statement = statement.where(
            col(Contract.end_date).is_not(None), col(Contract.end_date) < today_start
        )
    if state_filter is not None:
        statement = statement.where(contract_state_condition(state_filter, now))

    statement = filter_contracts_for_user(
        statement,
        current_user,
        "read",
        list_id=list_id,
    )
    resolved_sort_by = sort_by or "uploaded_at"
    sort_column = CONTRACT_SORT_COLUMNS.get(
        resolved_sort_by, col(Contract.uploaded_at)
    )
    if (cursor_uploaded_at is not None or cursor_id is not None) and resolved_sort_by != "uploaded_at":
        raise HTTPException(
            status_code=422,
            detail="Cursor-Paginierung unterstützt nur uploaded_at.",
        )
    if (cursor_uploaded_at is None) != (cursor_id is None):
        raise HTTPException(
            status_code=422,
            detail="cursor_uploaded_at und cursor_id müssen zusammen gesetzt sein.",
        )
    if cursor_uploaded_at is not None and cursor_id is not None:
        if sort_order == "asc":
            statement = statement.where(
                or_(
                    col(Contract.uploaded_at) > cursor_uploaded_at,
                    (col(Contract.uploaded_at) == cursor_uploaded_at)
                    & (col(Contract.id) > cursor_id),
                )
            )
        else:
            statement = statement.where(
                or_(
                    col(Contract.uploaded_at) < cursor_uploaded_at,
                    (col(Contract.uploaded_at) == cursor_uploaded_at)
                    & (col(Contract.id) < cursor_id),
                )
            )
    if sort_order == "asc":
        statement = statement.order_by(sort_column.asc(), col(Contract.id).asc())
    else:
        statement = statement.order_by(sort_column.desc(), col(Contract.id).desc())

    statement = statement.distinct()
    if load_relationships:
        statement = statement.options(
            selectinload(Contract.tags),
            selectinload(Contract.lists),  # type: ignore[arg-type]
        )
    return statement
