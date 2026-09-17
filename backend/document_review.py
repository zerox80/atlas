"""Resumable document review; one bounded, leased request per document."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlmodel import Session, col, select, update

from ai_client import AI_REQUEST_TIMEOUT_SECONDS, MODEL
from ai_routes import _require_ai_availability
from api_core import (
    check_contract_permission,
    filter_contracts_for_user,
    get_current_user,
    limiter,
)
from contract_endpoints.helpers import resolve_tags
from contract_queries.business_time import BUSINESS_TIMEZONE
from contract_queries.forms import parse_date_form, validate_cancellation_date
from database import get_session
from file_utils import resolve_file_path
from models import Contract, DocumentReviewItem, DocumentReviewRun, User
from schemas import ContractAnalysisResult, ContractUpdate
from security_utils import log_audit

router = APIRouter(prefix="/ai/reviews", tags=["document review"])
logger = logging.getLogger(__name__)
REVIEW_FIELDS = ("title", "description", "value", "annual_value", "start_date", "end_date", "notice_period", "tags")
REVIEW_TIMEOUT = AI_REQUEST_TIMEOUT_SECONDS * 2
MAX_BUNDLE_BYTES = 32 * 1024 * 1024


class ReviewApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[str] = Field(min_length=1, max_length=len(REVIEW_FIELDS))


def _run(session: Session, run_id: str, user: User) -> DocumentReviewRun:
    run = session.get(DocumentReviewRun, run_id)
    if run is None or run.owner_subject != user.auth_subject:
        raise HTTPException(404, "Prüflauf nicht gefunden.")
    return run


def _document(session: Session, document_id: int, user: User, level="read") -> Contract | None:
    document = session.get(Contract, document_id)
    if (document is None or document.deleted_at is not None
            or not check_contract_permission(user, document_id, level, session)):
        return None
    return document


def snapshot(document: Contract) -> dict:
    result = {field: getattr(document, field) for field in REVIEW_FIELDS if field != "tags"}
    for field in ("start_date", "end_date"):
        value = result[field]
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            result[field] = value.astimezone(BUSINESS_TIMEZONE).date().isoformat()
    result["tags"] = sorted(tag.name for tag in document.tags)
    result["version"] = document.version
    return result


def differences(before: dict, analysis: dict) -> list[dict]:
    changes = []
    for field in REVIEW_FIELDS:
        old, new = before[field], analysis.get(field)
        if field == "tags":
            new = sorted(new or [])
        if field in {"start_date", "end_date"} and new:
            parsed = parse_date_form(new)
            new = parsed.astimezone(BUSINESS_TIMEZONE).date().isoformat() if parsed else None
        if isinstance(old, float) and isinstance(new, (int, float)) and abs(old - new) < 0.005:
            continue
        if old == new or (field == "description" and not old and not new):
            continue
        changes.append({
            "field": field, "before": old, "after": new,
            "can_apply": not (field in {"title", "value"} and new is None),
        })
    return changes


def _summary(session: Session, run: DocumentReviewRun) -> dict:
    rows = session.exec(
        select(DocumentReviewItem.status, func.count())
        .where(DocumentReviewItem.run_id == run.id).group_by(DocumentReviewItem.status)
    ).all()
    counts = dict(rows)
    total = sum(counts.values())
    return {
        "id": run.id, "model": run.model, "created_at": run.created_at,
        "total": total, "counts": counts,
        "remaining": counts.get("pending", 0) + counts.get("processing", 0),
    }


@router.get("")
def list_reviews(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    runs = session.exec(
        select(DocumentReviewRun).where(DocumentReviewRun.owner_subject == user.auth_subject)
        .order_by(col(DocumentReviewRun.created_at).desc()).limit(20)
    ).all()
    return [_summary(session, run) for run in runs]


@router.post("")
@limiter.limit("3/hour")
def create_review(request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _require_ai_availability("Prüfung")
    # All accessible contracts AND invoices, including protected documents,
    # independent of pagination, search filters, and the selected workspace.
    document_ids = session.exec(filter_contracts_for_user(
        select(Contract.id).where(col(Contract.deleted_at).is_(None)), user
    )).all()
    run = DocumentReviewRun(owner_subject=user.auth_subject, model=MODEL)
    session.add(run)
    session.flush()
    for document_id in document_ids:
        session.add(DocumentReviewItem(run_id=run.id, contract_id=document_id))
    session.commit()
    return _summary(session, run)


@router.get("/{run_id}")
def read_review(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    run = _run(session, run_id, user)
    items = session.exec(select(DocumentReviewItem).where(DocumentReviewItem.run_id == run_id)
                         .order_by(col(DocumentReviewItem.id)).offset(offset).limit(limit)).all()
    output: list[dict] = []
    for item in items:
        document = _document(session, item.contract_id, user)
        if document is None:
            output.append({"id": item.id, "status": "unavailable", "title": "Dokument nicht mehr zugänglich"})
            continue
        result = json.loads(item.result_json) if item.result_json else {}
        output.append({
            "id": item.id, "contract_id": document.id, "title": document.title,
            "document_type": document.document_type, "status": item.status,
            "error": item.error, "result": result,
            "can_write": check_contract_permission(user, item.contract_id, "write", session),
        })
    return {**_summary(session, run), "items": output, "offset": offset, "limit": limit}


async def _read_bundle(paths: list[str]) -> list[bytes]:
    documents = []
    total = 0
    for path in paths:
        resolved = resolve_file_path(path)
        async with aiofiles.open(resolved, "rb") as source:
            data = await source.read(MAX_BUNDLE_BYTES - total + 1)
        total += len(data)
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("Dokument und Anlagen überschreiten das Prüflimit von 32 MiB.")
        documents.append(data)
    return documents


@router.post("/{run_id}/next")
@limiter.limit("30/minute")
async def review_next(run_id: str, request: Request, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)):
    _require_ai_availability("Prüfung")
    run = _run(session, run_id, user)
    if run.model != MODEL:
        raise HTTPException(409, "Das Analysemodell wurde geändert. Bitte einen neuen Prüflauf starten.")
    now, token = datetime.now(UTC), str(uuid4())
    claimed = session.exec(update(DocumentReviewRun).where(
        col(DocumentReviewRun.id) == run_id,
        or_(col(DocumentReviewRun.lease_until).is_(None), col(DocumentReviewRun.lease_until) < now),
    ).values(lease_token=token, lease_until=now + timedelta(seconds=REVIEW_TIMEOUT + 30))
      .execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Dieses Dokument wird bereits geprüft. Bitte kurz warten.")
    item = session.exec(select(DocumentReviewItem).where(
        DocumentReviewItem.run_id == run_id,
        col(DocumentReviewItem.status).in_(["pending", "processing"]),
    ).order_by(col(DocumentReviewItem.id))).first()
    if item is None:
        session.exec(update(DocumentReviewRun).where(col(DocumentReviewRun.id) == run_id)
                     .values(lease_until=None, lease_token=None))
        session.commit()
        return {"finished": True}
    document = _document(session, item.contract_id, user)
    item_id, document_id = item.id, item.contract_id
    paths: list[str] = []
    skipped: list[str] = []
    if document is None:
        item.status, item.error = "skipped", "Dokument gelöscht oder Zugriff entzogen."
    elif document.file_extension != ".pdf":
        item.status, item.error = "skipped", "Die KI-Prüfung unterstützt derzeit nur PDF-Hauptdokumente."
    else:
        paths = [document.file_path]
        for attachment in document.attachments:
            if Path(attachment.file_path).suffix.lower() == ".pdf":
                paths.append(attachment.file_path)
            else:
                skipped.append(attachment.filename)
        before = snapshot(document)
        item.snapshot_json = json.dumps(before, ensure_ascii=False)
        item.status = "processing"
        document_type = document.document_type
    session.add(item)
    if not paths:
        session.exec(update(DocumentReviewRun).where(col(DocumentReviewRun.id) == run_id)
                     .values(lease_until=None, lease_token=None))
        session.commit()
        return {"finished": False}
    owner_id, subject = user.id, user.auth_subject
    session.commit()
    # End read transactions before the slow external request.
    try:
        from ai_service import analyze_document_bundle

        async with asyncio.timeout(REVIEW_TIMEOUT):
            documents = await _read_bundle(paths)
            analysis = ContractAnalysisResult.model_validate(await analyze_document_bundle(
                documents, document_type=document_type, owner_id=owner_id
            )).model_dump()
        changes = differences(before, analysis)
        warnings = list(analysis["analysis_warnings"])
        if skipped:
            warnings.append(f"Nicht geprüft (kein PDF): {', '.join(skipped)}")
        if document_type == "contract" and analysis["notice_period"] is None:
            warnings.append("Keine eindeutig in Tagen belegte Kündigungsfrist.")
        result = {"changes": changes, "warnings": warnings,
                  "notice_period_evidence": analysis["notice_period_evidence"],
                  "checked_files": len(paths), "skipped_files": skipped}
        status = "issues" if changes or warnings else "checked"
        error = None
    except Exception as exc:  # noqa: BLE001 - isolate per-document failures and redact provider payloads
        # Provider errors may contain document text. Never expose/log their body.
        logger.warning("Document review %s failed (%s)", item_id, type(exc).__name__)
        status, result = "error", None
        error = "Prüfung fehlgeschlagen (Datei, KI-Antwort, Kapazität oder Zeitlimit). Erneut versuchen."
    current_user = session.exec(select(User).where(User.auth_subject == subject)).first()
    document = _document(session, document_id, current_user) if current_user and current_user.is_active else None
    if document is None:
        status, result, error = "skipped", None, "Dokument gelöscht oder Zugriff entzogen."
    elif document.version != before["version"]:
        status, result, error = "error", None, "Dokument während der Prüfung geändert. Erneut prüfen."
    # A timed-out worker cannot overwrite a later claim's result.
    owned = session.exec(update(DocumentReviewRun).where(
        col(DocumentReviewRun.id) == run_id, col(DocumentReviewRun.lease_token) == token
    ).values(lease_token=None, lease_until=None))
    if owned.rowcount == 1:
        session.exec(update(DocumentReviewItem).where(col(DocumentReviewItem.id) == item_id).values(
            status=status, error=error, result_json=json.dumps(result, ensure_ascii=False) if result else None
        ))
        session.commit()
    else:
        session.rollback()
    return {"finished": False}


@router.post("/{run_id}/retry")
def retry_errors(run_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _run(session, run_id, user)
    session.exec(update(DocumentReviewItem).where(
        col(DocumentReviewItem.run_id) == run_id, col(DocumentReviewItem.status) == "error"
    ).values(status="pending", error=None))
    session.commit()
    return {"ok": True}


@router.post("/{run_id}/items/{item_id}/apply")
def apply_review(run_id: str, item_id: int, body: ReviewApply, request: Request,
                 user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _run(session, run_id, user)
    item = session.get(DocumentReviewItem, item_id)
    if not item or item.run_id != run_id or item.status != "issues" or not item.result_json or not item.snapshot_json:
        raise HTTPException(409, "Kein übernehmbarer Prüfvorschlag vorhanden.")
    document = _document(session, item.contract_id, user, "write")
    if document is None:
        raise HTTPException(404, "Dokument nicht gefunden.")
    before = json.loads(item.snapshot_json)
    result = json.loads(item.result_json)
    changes = {change["field"]: change for change in result["changes"]}
    if any(field not in changes or not changes[field]["can_apply"] for field in body.fields):
        raise HTTPException(422, "Ungültige Feldauswahl.")
    values = {field: changes[field]["after"] for field in set(body.fields)}
    for field in ("start_date", "end_date"):
        if field in values:
            values[field] = parse_date_form(values[field])
    validated = ContractUpdate.model_validate(values).model_dump(exclude_unset=True)
    validate_cancellation_date(validated.get("end_date", document.end_date),
                               validated.get("notice_period", document.notice_period))
    session.autoflush = False
    # Validate tag permissions before claiming the document version.
    resolved_tags = resolve_tags(session, validated["tags"], allow_create=user.role == "admin") if "tags" in validated else []
    claimed = session.exec(update(Contract).where(
        col(Contract.id) == document.id, col(Contract.version) == before["version"],
        col(Contract.deleted_at).is_(None),
    ).values(version=before["version"] + 1).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Dokument inzwischen geändert. Bitte erneut prüfen.")
    for field, value in validated.items():
        if field == "tags":
            document.tags = resolved_tags
        else:
            setattr(document, field, value)
    document.version = before["version"] + 1
    session.add(document)
    result["changes"] = [change for change in result["changes"] if change["field"] not in values]
    result["applied_fields"] = sorted(set(result.get("applied_fields", []) + list(values)))
    item.result_json = json.dumps(result, ensure_ascii=False)
    item.snapshot_json = json.dumps(snapshot(document), ensure_ascii=False)
    item.status = "issues" if result["changes"] else "applied"
    session.add(item)
    log_audit(session, user.id, "UPDATE_CONTRACT",
              f"[CID:{document.id}] KI-Prüfung: {', '.join(sorted(values))} übernommen (Modell {MODEL}).",
              contract_id=document.id, commit=False)
    session.commit()
    return {"ok": True}
