"""Business-timezone boundaries and SQL date expressions."""

import os
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, literal
from sqlmodel import col

from database import IS_SQLITE
from models import Contract


BUSINESS_TIMEZONE_NAME = os.getenv("BUSINESS_TIMEZONE", "Europe/Berlin")
try:
    BUSINESS_TIMEZONE = ZoneInfo(BUSINESS_TIMEZONE_NAME)
except ZoneInfoNotFoundError as error:
    raise RuntimeError(
        f"Unknown BUSINESS_TIMEZONE: {BUSINESS_TIMEZONE_NAME}"
    ) from error


def business_day_start_utc(now: datetime, day_offset: int = 0) -> datetime:
    local_now = now.astimezone(BUSINESS_TIMEZONE)
    local_start = datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        tzinfo=BUSINESS_TIMEZONE,
    ) + timedelta(days=day_offset)
    return local_start.astimezone(timezone.utc)


def business_month_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(BUSINESS_TIMEZONE)
    month_start = datetime(local_now.year, local_now.month, 1, tzinfo=BUSINESS_TIMEZONE)
    next_month = (
        datetime(local_now.year + 1, 1, 1, tzinfo=BUSINESS_TIMEZONE)
        if local_now.month == 12
        else datetime(local_now.year, local_now.month + 1, 1, tzinfo=BUSINESS_TIMEZONE)
    )
    return month_start.astimezone(timezone.utc), next_month.astimezone(timezone.utc)


def cancellation_day(end_date_column, notice_period_column):
    notice_period = func.coalesce(notice_period_column, 30)
    if IS_SQLITE:
        return func.business_cancellation_julianday(
            end_date_column,
            notice_period_column,
        )
    return end_date_column - (notice_period * literal(timedelta(days=1)))


def sqlite_business_cancellation_julianday(
    end_date_value: object,
    notice_period_value: object,
) -> float | None:
    """Return the UTC Julian day for a local-calendar cancellation deadline."""
    if end_date_value is None:
        return None

    if isinstance(end_date_value, datetime):
        end_date = end_date_value
    else:
        try:
            end_date = datetime.fromisoformat(
                str(end_date_value).replace("Z", "+00:00")
            )
        except ValueError:
            return None
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    try:
        notice_period = (
            int(notice_period_value) if notice_period_value is not None else 30
        )
    except (TypeError, ValueError, OverflowError):
        notice_period = 30

    local_end_date = end_date.astimezone(BUSINESS_TIMEZONE).date()
    local_deadline_date = local_end_date - timedelta(days=notice_period)
    local_deadline = datetime.combine(
        local_deadline_date,
        time.min,
        tzinfo=BUSINESS_TIMEZONE,
    )
    deadline_utc = local_deadline.astimezone(timezone.utc)
    return deadline_utc.timestamp() / 86_400 + 2_440_587.5


def cancellation_boundary(value):
    return func.julianday(value) if IS_SQLITE else value


def contract_state_condition(
    state_filter: Literal["active", "attention", "expired"],
    now: datetime,
    end_date_column=col(Contract.end_date),
    notice_period_column=col(Contract.notice_period),
):
    today_start = business_day_start_utc(now)
    attention_end_exclusive = business_day_start_utc(now, 31)
    cancellation = cancellation_day(end_date_column, notice_period_column)
    if state_filter == "expired":
        return end_date_column.is_not(None) & (end_date_column < today_start)
    if state_filter == "attention":
        return (
            end_date_column.is_not(None)
            & (end_date_column >= today_start)
            & (cancellation < cancellation_boundary(attention_end_exclusive))
        )
    return end_date_column.is_(None) | (
        (end_date_column >= today_start)
        & (cancellation >= cancellation_boundary(attention_end_exclusive))
    )


def month_keys(now: datetime) -> list[str]:
    keys: list[str] = []
    for offset in range(5, -1, -1):
        month_index = now.year * 12 + now.month - 1 - offset
        keys.append(f"{month_index // 12:04d}-{month_index % 12 + 1:02d}")
    return keys


def business_month_key_bounds_utc(month_key: str) -> tuple[datetime, datetime]:
    year, month = (int(part) for part in month_key.split("-", maxsplit=1))
    month_start = datetime(year, month, 1, tzinfo=BUSINESS_TIMEZONE)
    next_month = (
        datetime(year + 1, 1, 1, tzinfo=BUSINESS_TIMEZONE)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=BUSINESS_TIMEZONE)
    )
    return month_start.astimezone(timezone.utc), next_month.astimezone(timezone.utc)
