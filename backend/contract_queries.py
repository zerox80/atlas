"""Contract listing, filtering, export, and form parsing helpers."""

import io
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from api_core import (
    AI_SUPPORTED_FILE_EXTENSION,
    contract_reads_for_user,
    filter_contracts_for_user,
    get_current_user,
)
from database import get_session
from models import Contract, ContractListLink, ContractTagLink, Tag, User
from schemas import ContractRead

router = APIRouter()
EXPORT_MAX_ROWS = 10_000
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")

# --- Contract Endpoints ---

CONTRACT_SORT_COLUMNS: dict[str, Any] = {
    "title": col(Contract.title),
    "value": col(Contract.value),
    "start_date": col(Contract.start_date),
    "end_date": col(Contract.end_date),
    "uploaded_at": col(Contract.uploaded_at),
}


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
    document_type: Optional[str] = None,
    is_protected: Optional[bool] = None,
    sort_by: Optional[str] = "uploaded_at",
    sort_order: Optional[str] = "desc",
    cursor_uploaded_at: Optional[datetime] = None,
    cursor_id: Optional[int] = None,
):
    """Build the shared filtered contract query used by list and export endpoints."""
    statement = select(Contract)

    if document_type in {"contract", "invoice"}:
        statement = statement.where(col(Contract.document_type) == document_type)
    if is_protected is not None:
        statement = statement.where(col(Contract.is_protected) == is_protected)

    if q:
        search_term = f"%{q}%"
        statement = statement.where(
            or_(
                col(Contract.title).ilike(search_term),
                col(Contract.description).ilike(search_term),
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
    if status_filter == "active":
        statement = statement.where(or_(col(Contract.end_date).is_(None), col(Contract.end_date) >= now))
    elif status_filter == "expired":
        statement = statement.where(col(Contract.end_date).is_not(None), col(Contract.end_date) < now)

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

    return statement.distinct().options(
        selectinload(Contract.tags),
        selectinload(Contract.lists),  # type: ignore[arg-type]
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
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format")

def parse_float_form(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid float format")

def parse_int_form(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid int format")


def parse_tags_form(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [tag.strip() for tag in val.split(",") if tag.strip()]


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
