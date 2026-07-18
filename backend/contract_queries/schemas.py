"""Response models for contract collection endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from schemas import ContractRead


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
