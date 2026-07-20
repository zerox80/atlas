"""Filtered contract listing and export endpoints."""

import io
from datetime import datetime
from typing import List, Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api_core import contract_reads_for_user, get_current_user
from database import get_session
from models import User
from schemas import ContractRead

from .filters import build_contract_query


router = APIRouter()
EXPORT_MAX_ROWS = 10_000
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


@router.get("/contracts", response_model=List[ContractRead])
def read_contracts(
    q: Optional[str] = Query(default=None, max_length=200),
    tags: Optional[str] = Query(default=None, max_length=500),
    list_id: Optional[int] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    start_date_from: Optional[datetime] = None,
    start_date_to: Optional[datetime] = None,
    status: Optional[Literal["active", "expired"]] = None,
    document_type: Optional[Literal["contract", "invoice"]] = None,
    is_protected: Optional[bool] = None,
    sort_by: Literal[
        "title", "value", "start_date", "end_date", "uploaded_at"
    ] = "uploaded_at",
    sort_order: Literal["asc", "desc"] = "desc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    cursor_uploaded_at: Optional[datetime] = None,
    cursor_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get contracts with optional search, filters, and access control."""
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
    sort_by: Literal[
        "title", "value", "start_date", "end_date", "uploaded_at"
    ] = "uploaded_at",
    sort_order: Literal["asc", "desc"] = "desc",
    format: Literal["csv", "excel"] = "csv",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Export filtered contracts as CSV or Excel."""
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

    visible_contracts = contract_reads_for_user(contracts, current_user, session)
    data = [
        {
            "ID": contract["id"],
            "Titel": _spreadsheet_safe(contract["title"]),
            "Beschreibung": _spreadsheet_safe(contract["description"]),
            "Wert (€)": contract["value"],
            "Jährlicher Wert (€)": contract["annual_value"],
            "Startdatum": (
                contract["start_date"].strftime("%Y-%m-%d")
                if contract["start_date"]
                else ""
            ),
            "Enddatum": (
                contract["end_date"].strftime("%Y-%m-%d")
                if contract["end_date"]
                else ""
            ),
            "Kündigungsfrist (Tage)": (
                contract["notice_period"]
                if contract["notice_period"] is not None
                else ""
            ),
            "Geschützt": "Ja" if contract["is_protected"] else "Nein",
            "Tags": _spreadsheet_safe(
                ", ".join(tag["name"] for tag in contract["tags"])
            ),
            "Listen": _spreadsheet_safe(
                ", ".join(
                    workspace["name"] for workspace in contract["lists"]
                )
            ),
            "Erstellt am": (
                contract["uploaded_at"].strftime("%Y-%m-%d %H:%M")
                if contract["uploaded_at"]
                else ""
            ),
        }
        for contract in visible_contracts
    ]
    data_frame = pd.DataFrame(data)

    if format == "excel":
        excel_output = io.BytesIO()
        with pd.ExcelWriter(excel_output, engine="openpyxl") as writer:
            data_frame.to_excel(writer, index=False, sheet_name="Verträge")
        excel_output.seek(0)
        return StreamingResponse(
            excel_output,
            headers={
                "Content-Disposition": 'attachment; filename="vertrage_export.xlsx"'
            },
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    csv_output = io.StringIO()
    data_frame.to_csv(csv_output, index=False, sep=";")
    output_bytes = io.BytesIO(csv_output.getvalue().encode("utf-8-sig"))
    return StreamingResponse(
        output_bytes,
        headers={"Content-Disposition": 'attachment; filename="vertrage_export.csv"'},
        media_type="text/csv",
    )


def _spreadsheet_safe(value: str | None) -> str:
    """Prevent user-controlled text from becoming an Excel/CSV formula."""
    if value is None:
        return ""
    candidate = value.lstrip(" \t\r\n")
    if candidate.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return "'" + value
    return value
