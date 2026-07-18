"""Paged, dashboard, and calendar contract endpoints."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlmodel import Session, col, select

from api_core import contract_reads_for_user, get_current_user
from database import get_session
from models import Contract, User

from .business_time import (
    BUSINESS_TIMEZONE,
    BUSINESS_TIMEZONE_NAME,
    business_day_start_utc,
    business_month_bounds_utc,
    business_month_key_bounds_utc,
    cancellation_boundary,
    cancellation_day,
    contract_state_condition,
    month_keys,
)
from .filters import build_contract_query
from .schemas import (
    CalendarData,
    ContractCollectionSummary,
    ContractPage,
    DashboardChartPoint,
    DashboardData,
    DashboardSummary,
)


router = APIRouter()
CALENDAR_MAX_ROWS = 1_000


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
    month_start, next_month = business_month_bounds_utc(now)
    document_date = func.coalesce(scope.c.start_date, scope.c.uploaded_at)
    row = session.exec(
        select(
            func.count(scope.c.id),
            func.coalesce(func.sum(scope.c.value), 0.0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            contract_state_condition(
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
                            contract_state_condition(
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
                            contract_state_condition(
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
                            (document_date >= month_start)
                            & (document_date < next_month),
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
            q=q,
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
    today_start = business_day_start_utc(now)
    deadline_end_exclusive = business_day_start_utc(now, 61)
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
    cancellation = cancellation_day(scope.c.end_date, scope.c.notice_period)
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
                            & (
                                scope.c.end_date.is_(None)
                                | (scope.c.end_date >= today_start)
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
                            is_contract
                            & scope.c.end_date.is_not(None)
                            & (scope.c.end_date >= today_start)
                            & (cancellation >= cancellation_boundary(today_start))
                            & (
                                cancellation
                                < cancellation_boundary(deadline_end_exclusive)
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((scope.c.is_protected.is_(True), 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((scope.c.document_type == "invoice", 1), else_=0)), 0
            ),
        ).select_from(scope)
    ).one()

    keys = month_keys(now.astimezone(BUSINESS_TIMEZONE))
    document_date = func.coalesce(scope.c.start_date, scope.c.uploaded_at)
    chart_expressions: list[Any] = []
    for key in keys:
        month_start, next_month = business_month_key_bounds_utc(key)
        in_month = (document_date >= month_start) & (document_date < next_month)
        chart_expressions.extend(
            [
                func.coalesce(
                    func.sum(
                        case(
                            (
                                in_month & (scope.c.document_type == "contract"),
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
                                in_month & (scope.c.document_type == "invoice"),
                                scope.c.value,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
            ]
        )
    chart_row = session.exec(select(*chart_expressions).select_from(scope)).one()
    chart_by_month = {
        key: (
            float(chart_row[index * 2] or 0),
            float(chart_row[index * 2 + 1] or 0),
        )
        for index, key in enumerate(keys)
    }

    recent = session.exec(
        build_contract_query(current_user=current_user, list_id=list_id).limit(6)
    ).all()
    upcoming_cancellation = cancellation_day(
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
            upcoming_cancellation >= cancellation_boundary(today_start),
            upcoming_cancellation < cancellation_boundary(deadline_end_exclusive),
        )
        .order_by(upcoming_cancellation.asc(), col(Contract.id).asc())
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
            for key in keys
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
        raise HTTPException(
            status_code=422,
            detail="Calendar range must span between 1 and 62 days.",
        )
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    cancellation = cancellation_day(
        col(Contract.end_date), col(Contract.notice_period)
    )
    statement = (
        build_contract_query(
            current_user=current_user,
            list_id=list_id,
            document_type="contract",
        )
        .order_by(None)
        .where(
            (
                ((col(Contract.start_date) >= start_utc) & (col(Contract.start_date) < end_utc))
                | ((col(Contract.end_date) >= start_utc) & (col(Contract.end_date) < end_utc))
                | (
                    col(Contract.end_date).is_not(None)
                    & (cancellation >= cancellation_boundary(start_utc))
                    & (cancellation < cancellation_boundary(end_utc))
                )
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
