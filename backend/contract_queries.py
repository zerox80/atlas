"""Contract listing, filtering, export, and form parsing helpers."""

import io
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import case, func, literal, or_
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from api_core import (
    AI_SUPPORTED_FILE_EXTENSION,
    contract_reads_for_user,
    filter_contracts_for_user,
    get_current_user,
)
from database import IS_SQLITE, get_session
from models import Contract, ContractListLink, ContractTagLink, Tag, User
from schemas import (
    MAX_CONTRACT_TAGS,
    MAX_FINANCIAL_VALUE,
    MAX_NOTICE_PERIOD_DAYS,
    ContractRead,
)

router = APIRouter()
EXPORT_MAX_ROWS = 10_000
CALENDAR_MAX_ROWS = 1_000
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")
BUSINESS_TIMEZONE_NAME = os.getenv("BUSINESS_TIMEZONE", "Europe/Berlin")
try:
    BUSINESS_TIMEZONE = ZoneInfo(BUSINESS_TIMEZONE_NAME)
except ZoneInfoNotFoundError as error:
    raise RuntimeError(
        f"Unknown BUSINESS_TIMEZONE: {BUSINESS_TIMEZONE_NAME}"
    ) from error


class ContractCollectionSummary(BaseModel):
    all: int
    active: int
    attention: int
    expired: int
    total_value: float
    current_month_value: float


class ContractPage(BaseModel):
    items: List[ContractRead]
    summary: Optional[ContractCollectionSummary] = None
    has_more: bool
    next_cursor_uploaded_at: Optional[datetime] = None
    next_cursor_id: Optional[int] = None


class DashboardSummary(BaseModel):
    document_count: int
    total_value: float
    active_contract_count: int
    deadline_count: int
    protected_count: int
    invoice_count: int


class DashboardChartPoint(BaseModel):
    month: str
    contracts: float
    invoices: float


class DashboardData(BaseModel):
    business_timezone: str
    summary: DashboardSummary
    chart: List[DashboardChartPoint]
    upcoming: List[ContractRead]
    recent: List[ContractRead]


class CalendarData(BaseModel):
    business_timezone: str
    items: List[ContractRead]
    truncated: bool

# --- Contract Endpoints ---

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


def _business_day_start_utc(now: datetime, day_offset: int = 0) -> datetime:
    local_now = now.astimezone(BUSINESS_TIMEZONE)
    local_start = datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        tzinfo=BUSINESS_TIMEZONE,
    ) + timedelta(days=day_offset)
    return local_start.astimezone(timezone.utc)


def _business_month_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(BUSINESS_TIMEZONE)
    month_start = datetime(local_now.year, local_now.month, 1, tzinfo=BUSINESS_TIMEZONE)
    next_month = (
        datetime(local_now.year + 1, 1, 1, tzinfo=BUSINESS_TIMEZONE)
        if local_now.month == 12
        else datetime(local_now.year, local_now.month + 1, 1, tzinfo=BUSINESS_TIMEZONE)
    )
    return month_start.astimezone(timezone.utc), next_month.astimezone(timezone.utc)


def _cancellation_day(end_date_column, notice_period_column):
    notice_period = func.coalesce(notice_period_column, 30)
    if IS_SQLITE:
        return func.julianday(end_date_column) - notice_period
    return end_date_column - (notice_period * literal(timedelta(days=1)))


def _cancellation_boundary(value):
    return func.julianday(value) if IS_SQLITE else value


def _contract_state_condition(
    state_filter: Literal["active", "attention", "expired"],
    now: datetime,
    end_date_column=col(Contract.end_date),
    notice_period_column=col(Contract.notice_period),
):
    today_start = _business_day_start_utc(now)
    attention_end_exclusive = _business_day_start_utc(now, 31)
    cancellation_day = _cancellation_day(end_date_column, notice_period_column)
    if state_filter == "expired":
        return end_date_column.is_not(None) & (end_date_column < today_start)
    if state_filter == "attention":
        return (
            end_date_column.is_not(None)
            & (end_date_column >= today_start)
            & (cancellation_day < _cancellation_boundary(attention_end_exclusive))
        )
    return end_date_column.is_(None) | (
        (end_date_column >= today_start)
        & (cancellation_day >= _cancellation_boundary(attention_end_exclusive))
    )


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
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            statement = statement.join(ContractTagLink).join(Tag).where(col(Tag.name).in_(tag_list))

    if list_id is not None:
        statement = statement.join(ContractListLink).where(ContractListLink.list_id == list_id)

    if min_value is not None:
        statement = statement.where(Contract.value >= min_value)
    if max_value is not None:
        statement = statement.where(Contract.value <= max_value)

    if start_date_from:
        statement = statement.where(col(Contract.start_date).is_not(None), col(Contract.start_date) >= start_date_from)
    if start_date_to:
        statement = statement.where(col(Contract.start_date).is_not(None), col(Contract.start_date) <= start_date_to)

    now = datetime.now(timezone.utc)
    today_start = _business_day_start_utc(now)
    if status_filter == "active":
        statement = statement.where(or_(col(Contract.end_date).is_(None), col(Contract.end_date) >= today_start))
    elif status_filter == "expired":
        statement = statement.where(col(Contract.end_date).is_not(None), col(Contract.end_date) < today_start)
    if state_filter is not None:
        statement = statement.where(_contract_state_condition(state_filter, now))

    statement = filter_contracts_for_user(statement, current_user, "read")

    resolved_sort_by = sort_by or "uploaded_at"
    sort_column = CONTRACT_SORT_COLUMNS.get(resolved_sort_by, col(Contract.uploaded_at))
    if (cursor_uploaded_at is not None or cursor_id is not None) and resolved_sort_by != "uploaded_at":
        raise HTTPException(status_code=422, detail="Cursor-Paginierung unterstützt nur uploaded_at.")
    if (cursor_uploaded_at is None) != (cursor_id is None):
        raise HTTPException(status_code=422, detail="cursor_uploaded_at und cursor_id müssen zusammen gesetzt sein.")
    if cursor_uploaded_at is not None and cursor_id is not None:
        if sort_order == "asc":
            statement = statement.where(
                or_(
                    col(Contract.uploaded_at) > cursor_uploaded_at,
                    (col(Contract.uploaded_at) == cursor_uploaded_at) & (col(Contract.id) > cursor_id),
                )
            )
        else:
            statement = statement.where(
                or_(
                    col(Contract.uploaded_at) < cursor_uploaded_at,
                    (col(Contract.uploaded_at) == cursor_uploaded_at) & (col(Contract.id) < cursor_id),
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


def _collection_summary(statement, session: Session) -> ContractCollectionSummary:
    scope = (
        statement.with_only_columns(
            Contract.id,
            Contract.value,
            Contract.start_date,
            Contract.uploaded_at,
            Contract.end_date,
            Contract.notice_period,
        )
        .order_by(None)
        .distinct()
        .subquery()
    )
    now = datetime.now(timezone.utc)
    month_start, next_month = _business_month_bounds_utc(now)
    document_date = func.coalesce(scope.c.start_date, scope.c.uploaded_at)
    row = session.exec(
        select(
            func.count(scope.c.id),
            func.coalesce(func.sum(scope.c.value), 0.0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            _contract_state_condition(
                                "active", now, scope.c.end_date, scope.c.notice_period
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            _contract_state_condition(
                                "attention", now, scope.c.end_date, scope.c.notice_period
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            _contract_state_condition(
                                "expired", now, scope.c.end_date, scope.c.notice_period
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (document_date >= month_start) & (document_date < next_month),
                            scope.c.value,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
        ).select_from(scope)
    ).one()
    return ContractCollectionSummary(
        all=int(row[0] or 0),
        total_value=float(row[1] or 0),
        active=int(row[2] or 0),
        attention=int(row[3] or 0),
        expired=int(row[4] or 0),
        current_month_value=float(row[5] or 0),
    )


def _month_keys(now: datetime) -> list[str]:
    keys: list[str] = []
    for offset in range(5, -1, -1):
        month_index = now.year * 12 + now.month - 1 - offset
        keys.append(f"{month_index // 12:04d}-{month_index % 12 + 1:02d}")
    return keys


def _business_month_key_bounds_utc(month_key: str) -> tuple[datetime, datetime]:
    year, month = (int(part) for part in month_key.split("-", maxsplit=1))
    month_start = datetime(year, month, 1, tzinfo=BUSINESS_TIMEZONE)
    next_month = (
        datetime(year + 1, 1, 1, tzinfo=BUSINESS_TIMEZONE)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=BUSINESS_TIMEZONE)
    )
    return (
        month_start.astimezone(timezone.utc),
        next_month.astimezone(timezone.utc),
    )


@router.get("/contracts/page", response_model=ContractPage)
def read_contract_page(
    q: Optional[str] = Query(default=None, max_length=200),
    list_id: Optional[int] = None,
    document_type: Optional[Literal["contract", "invoice"]] = None,
    is_protected: Optional[bool] = None,
    state: Optional[Literal["active", "attention", "expired"]] = None,
    include_summary: bool = True,
    limit: int = Query(default=40, ge=1, le=100),
    cursor_uploaded_at: Optional[datetime] = None,
    cursor_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return one bounded document page, with aggregates only on the first page."""
    page_statement = build_contract_query(
        current_user=current_user,
        q=q,
        list_id=list_id,
        document_type=document_type,
        is_protected=is_protected,
        state_filter=state,
        cursor_uploaded_at=cursor_uploaded_at,
        cursor_id=cursor_id,
    )
    summary: Optional[ContractCollectionSummary] = None
    if include_summary and cursor_uploaded_at is None and cursor_id is None:
        summary_statement = build_contract_query(
            current_user=current_user,
            list_id=list_id,
            document_type=document_type,
            is_protected=is_protected,
            load_relationships=False,
        )
        summary = _collection_summary(summary_statement, session)

    contracts = list(session.exec(page_statement.limit(limit + 1)).all())
    has_more = len(contracts) > limit
    visible_contracts = contracts[:limit]
    last_contract = visible_contracts[-1] if has_more and visible_contracts else None
    return ContractPage(
        items=contract_reads_for_user(visible_contracts, current_user, session),
        summary=summary,
        has_more=has_more,
        next_cursor_uploaded_at=last_contract.uploaded_at if last_contract else None,
        next_cursor_id=last_contract.id if last_contract else None,
    )


@router.get("/contracts/dashboard", response_model=DashboardData)
def read_contract_dashboard(
    list_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return only the aggregates and top-N rows needed by the dashboard."""
    now = datetime.now(timezone.utc)
    today_start = _business_day_start_utc(now)
    deadline_end_exclusive = _business_day_start_utc(now, 61)
    base_statement = build_contract_query(
        current_user=current_user,
        list_id=list_id,
        load_relationships=False,
    )
    scope = (
        base_statement.with_only_columns(
            Contract.id,
            Contract.document_type,
            Contract.value,
            Contract.start_date,
            Contract.uploaded_at,
            Contract.end_date,
            Contract.notice_period,
            Contract.is_protected,
        )
        .order_by(None)
        .distinct()
        .subquery()
    )
    cancellation_day = _cancellation_day(scope.c.end_date, scope.c.notice_period)
    is_contract = scope.c.document_type == "contract"
    summary_row = session.exec(
        select(
            func.count(scope.c.id),
            func.coalesce(func.sum(scope.c.value), 0.0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            is_contract
                            & (scope.c.end_date.is_(None) | (scope.c.end_date >= today_start)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            is_contract
                            & scope.c.end_date.is_not(None)
                            & (scope.c.end_date >= today_start)
                            & (cancellation_day >= _cancellation_boundary(today_start))
                            & (cancellation_day < _cancellation_boundary(deadline_end_exclusive)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((scope.c.is_protected.is_(True), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((scope.c.document_type == "invoice", 1), else_=0)),
                0,
            ),
        ).select_from(scope)
    ).one()

    month_keys = _month_keys(now.astimezone(BUSINESS_TIMEZONE))
    document_date = func.coalesce(scope.c.start_date, scope.c.uploaded_at)
    chart_expressions: list[Any] = []
    for key in month_keys:
        month_start, next_month = _business_month_key_bounds_utc(key)
        in_month = (document_date >= month_start) & (document_date < next_month)
        chart_expressions.extend(
            [
                func.coalesce(
                    func.sum(
                        case(
                            (
                                in_month
                                & (scope.c.document_type == "contract"),
                                scope.c.value,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                in_month
                                & (scope.c.document_type == "invoice"),
                                scope.c.value,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
            ]
        )
    chart_row = session.exec(
        select(*chart_expressions).select_from(scope)
    ).one()
    chart_by_month = {
        key: (
            float(chart_row[index * 2] or 0),
            float(chart_row[index * 2 + 1] or 0),
        )
        for index, key in enumerate(month_keys)
    }

    recent = session.exec(
        build_contract_query(current_user=current_user, list_id=list_id).limit(6)
    ).all()
    upcoming_cancellation_day = _cancellation_day(
        col(Contract.end_date), col(Contract.notice_period)
    )
    upcoming = session.exec(
        build_contract_query(
            current_user=current_user,
            list_id=list_id,
            document_type="contract",
        )
        .order_by(None)
        .where(
            col(Contract.end_date).is_not(None),
            col(Contract.end_date) >= today_start,
            upcoming_cancellation_day >= _cancellation_boundary(today_start),
            upcoming_cancellation_day < _cancellation_boundary(deadline_end_exclusive),
        )
        .order_by(upcoming_cancellation_day.asc(), col(Contract.id).asc())
        .limit(5)
    ).all()

    return DashboardData(
        business_timezone=BUSINESS_TIMEZONE_NAME,
        summary=DashboardSummary(
            document_count=int(summary_row[0] or 0),
            total_value=float(summary_row[1] or 0),
            active_contract_count=int(summary_row[2] or 0),
            deadline_count=int(summary_row[3] or 0),
            protected_count=int(summary_row[4] or 0),
            invoice_count=int(summary_row[5] or 0),
        ),
        chart=[
            DashboardChartPoint(
                month=key,
                contracts=chart_by_month.get(key, (0.0, 0.0))[0],
                invoices=chart_by_month.get(key, (0.0, 0.0))[1],
            )
            for key in month_keys
        ],
        upcoming=contract_reads_for_user(upcoming, current_user, session),
        recent=contract_reads_for_user(recent, current_user, session),
    )


@router.get("/contracts/calendar", response_model=CalendarData)
def read_contract_calendar(
    start: datetime,
    end: datetime,
    list_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return contracts that create an event inside one bounded calendar window."""
    start_local = (
        start.replace(tzinfo=BUSINESS_TIMEZONE)
        if start.tzinfo is None
        else start.astimezone(BUSINESS_TIMEZONE)
    )
    end_local = (
        end.replace(tzinfo=BUSINESS_TIMEZONE)
        if end.tzinfo is None
        else end.astimezone(BUSINESS_TIMEZONE)
    )
    calendar_span = (end_local.date() - start_local.date()).days
    if calendar_span < 1 or calendar_span > 62:
        raise HTTPException(status_code=422, detail="Calendar range must span between 1 and 62 days.")
    start = start_local.astimezone(timezone.utc)
    end = end_local.astimezone(timezone.utc)

    cancellation_day = _cancellation_day(col(Contract.end_date), col(Contract.notice_period))
    statement = (
        build_contract_query(
            current_user=current_user,
            list_id=list_id,
            document_type="contract",
        )
        .order_by(None)
        .where(
            or_(
                (col(Contract.start_date) >= start) & (col(Contract.start_date) < end),
                (col(Contract.end_date) >= start) & (col(Contract.end_date) < end),
                (
                    col(Contract.end_date).is_not(None)
                    & (cancellation_day >= _cancellation_boundary(start))
                    & (cancellation_day < _cancellation_boundary(end))
                ),
            )
        )
        .order_by(col(Contract.start_date).asc(), col(Contract.id).asc())
    )
    contracts = list(session.exec(statement.limit(CALENDAR_MAX_ROWS + 1)).all())
    truncated = len(contracts) > CALENDAR_MAX_ROWS
    visible_contracts = contracts[:CALENDAR_MAX_ROWS]
    return CalendarData(
        business_timezone=BUSINESS_TIMEZONE_NAME,
        items=contract_reads_for_user(visible_contracts, current_user, session),
        truncated=truncated,
    )

@router.get("/contracts", response_model=List[ContractRead])
def read_contracts(
    q: Optional[str] = Query(default=None, max_length=200),
    tags: Optional[str] = Query(default=None, max_length=500),
    list_id: Optional[int] = None,              # Filter by list
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    start_date_from: Optional[datetime] = None,
    start_date_to: Optional[datetime] = None,
    status: Optional[Literal["active", "expired"]] = None,
    document_type: Optional[Literal["contract", "invoice"]] = None,
    is_protected: Optional[bool] = None,
    sort_by: Literal["title", "value", "start_date", "end_date", "uploaded_at"] = "uploaded_at",
    sort_order: Literal["asc", "desc"] = "desc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    cursor_uploaded_at: Optional[datetime] = None,
    cursor_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """
    Get contracts with optional search and filters.
    Non-admin users only see contracts they have explicit read access to.
    """
    statement = build_contract_query(
        current_user=current_user,
        q=q,
        tags=tags,
        list_id=list_id,
        min_value=min_value,
        max_value=max_value,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
        status_filter=status,
        document_type=document_type,
        is_protected=is_protected,
        sort_by=sort_by,
        sort_order=sort_order,
        cursor_uploaded_at=cursor_uploaded_at,
        cursor_id=cursor_id,
    )
    contracts = session.exec(statement.offset(offset).limit(limit)).all()
    return contract_reads_for_user(contracts, current_user, session)

@router.get("/contracts/export")
def export_contracts(
    q: Optional[str] = Query(default=None, max_length=200),
    tags: Optional[str] = Query(default=None, max_length=500),
    list_id: Optional[int] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    start_date_from: Optional[datetime] = None,
    start_date_to: Optional[datetime] = None,
    status: Optional[Literal["active", "expired"]] = None,
    document_type: Optional[Literal["contract", "invoice"]] = None,
    sort_by: Literal["title", "value", "start_date", "end_date", "uploaded_at"] = "uploaded_at",
    sort_order: Literal["asc", "desc"] = "desc",
    format: Literal["csv", "excel"] = "csv",
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """
    Export filtered contracts as CSV or Excel.
    """
    statement = build_contract_query(
        current_user=current_user,
        q=q,
        tags=tags,
        list_id=list_id,
        min_value=min_value,
        max_value=max_value,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
        status_filter=status,
        document_type=document_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    contracts = session.exec(statement.limit(EXPORT_MAX_ROWS + 1)).all()
    if len(contracts) > EXPORT_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Export is limited to {EXPORT_MAX_ROWS} rows; narrow the filters.",
        )
    
    # --- Data Processing ---
    data = []
    for c in contracts:
        data.append({
            "ID": c.id,
            "Titel": _spreadsheet_safe(c.title),
            "Beschreibung": _spreadsheet_safe(c.description),
            "Wert (€)": c.value,
            "Jährlicher Wert (€)": c.annual_value,
            "Startdatum": c.start_date.strftime("%Y-%m-%d") if c.start_date else "",
            "Enddatum": c.end_date.strftime("%Y-%m-%d") if c.end_date else "",
            "Kündigungsfrist (Tage)": c.notice_period if c.notice_period is not None else "",
            "Geschützt": "Ja" if c.is_protected else "Nein",
            "Tags": _spreadsheet_safe(", ".join([t.name for t in c.tags])),
            "Listen": _spreadsheet_safe(", ".join([contract_list.name for contract_list in c.lists])),
            "Erstellt am": c.uploaded_at.strftime("%Y-%m-%d %H:%M") if c.uploaded_at else ""
        })
        
    df = pd.DataFrame(data)
    
    if format == "excel":
        excel_output = io.BytesIO()
        with pd.ExcelWriter(excel_output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Verträge")
        excel_output.seek(0)
        
        headers = {
            'Content-Disposition': 'attachment; filename="vertrage_export.xlsx"'
        }
        return StreamingResponse(
            excel_output,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        
    csv_output = io.StringIO()
    df.to_csv(csv_output, index=False, sep=";")
    output_bytes = io.BytesIO(csv_output.getvalue().encode("utf-8-sig"))

    headers = {
        "Content-Disposition": 'attachment; filename="vertrage_export.csv"'
    }
    return StreamingResponse(output_bytes, headers=headers, media_type="text/csv")


def _spreadsheet_safe(value: str | None) -> str:
    """Prevent user-controlled text from becoming an Excel/CSV formula."""
    if value is None:
        return ""
    candidate = value.lstrip(" \t\r\n")
    if candidate.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return "'" + value
    return value

def parse_date_form(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BUSINESS_TIMEZONE)
    return parsed.astimezone(timezone.utc)

def parse_float_form(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        parsed = float(val)
    except (ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="Invalid float format")
    if not math.isfinite(parsed) or parsed < 0 or parsed > MAX_FINANCIAL_VALUE:
        raise HTTPException(
            status_code=422,
            detail=f"Value must be finite and between 0 and {MAX_FINANCIAL_VALUE:g}",
        )
    return parsed

def parse_int_form(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    try:
        parsed = int(val)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid int format")
    if parsed < 0 or parsed > MAX_NOTICE_PERIOD_DAYS:
        raise HTTPException(
            status_code=422, detail=f"Notice period must be between 0 and {MAX_NOTICE_PERIOD_DAYS} days"
        )

    return parsed

def parse_tags_form(val: Optional[str]) -> List[str]:
    if not val:
        return []
    if len(val) > 2_550:
        raise HTTPException(status_code=422, detail="Tag input is too long")
    tags = [tag.strip() for tag in val.split(",") if tag.strip()]
    if len(tags) > MAX_CONTRACT_TAGS:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_CONTRACT_TAGS} tags are allowed",
        )
    return tags


def validation_error_detail(exc: ValidationError) -> list[dict]:
    errors = exc.errors()
    for error in errors:
        ctx = error.get("ctx")
        if ctx and "error" in ctx:
            ctx["error"] = str(ctx["error"])
    return jsonable_encoder(errors)


def validate_contract_form(schema_cls, **values):
    try:
        return schema_cls(**values)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=validation_error_detail(exc))


def ensure_ai_supported_contract_file(contract: Contract) -> None:
    if contract.file_extension.lower() != AI_SUPPORTED_FILE_EXTENSION:
        raise HTTPException(
            status_code=400,
            detail="KI-Chat unterstuetzt aktuell nur PDF-Dateien.",
        )
