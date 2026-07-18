"""Parsing and validation helpers shared by contract mutation routes."""

import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from api_core import AI_SUPPORTED_FILE_EXTENSION
from models import Contract
from schemas import MAX_CONTRACT_TAGS, MAX_FINANCIAL_VALUE, MAX_NOTICE_PERIOD_DAYS

from .business_time import BUSINESS_TIMEZONE


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
            status_code=422,
            detail=(
                "Notice period must be between 0 and "
                f"{MAX_NOTICE_PERIOD_DAYS} days"
            ),
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
