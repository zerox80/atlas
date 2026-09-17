"""Resumable document review; one leased OCR or analysis request at a time."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlmodel import Session, col, select, update

from ai_client import MODEL
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
from models import (
    Contract,
    DocumentReviewControl,
    DocumentReviewItem,
    DocumentReviewRun,
    DocumentSplitRecord,
    User,
)
from review_analysis import ReviewProcessingError
from review_comparison import result_status
from review_schema import PIPELINE_VERSION, REVIEW_FIELDS
from review_worker import STEP_TIMEOUT, process_review_step
from schemas import ContractUpdate
from security_utils import log_audit

router = APIRouter(prefix="/ai/reviews", tags=["document review"])
MAX_BUNDLE_BYTES = 32 * 1024 * 1024
logger = logging.getLogger("atlas.review")


class ReviewApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[str] = Field(min_length=1, max_length=len(REVIEW_FIELDS))


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: bool = False


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accept: bool


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


def _summary(session: Session, run: DocumentReviewRun) -> dict:
    rows = session.exec(
        select(DocumentReviewItem.status, func.count())
        .where(DocumentReviewItem.run_id == run.id).group_by(DocumentReviewItem.status)
    ).all()
    counts = dict(rows)
    total = sum(counts.values())
    control = session.get(DocumentReviewControl, run.id)
    return {
        "id": run.id, "model": run.model, "created_at": run.created_at,
        "total": total, "counts": counts,
        "remaining": counts.get("pending", 0) + counts.get("processing", 0),
        "running": bool(control and control.running and (counts.get("pending", 0) or counts.get("processing", 0))),
        "run_error": control.error if control else None,
    }


def _guard_active_run(session: Session, user: User, run_id: str | None = None):
    # Lock the same owner row before checking intent/leases; concurrent starts cannot race.
    session.exec(update(User).where(col(User.id) == user.id).values(is_active=User.is_active))
    active = session.exec(select(DocumentReviewRun.id).outerjoin(
        DocumentReviewControl, col(DocumentReviewControl.run_id) == col(DocumentReviewRun.id),
    ).where(DocumentReviewRun.owner_subject == user.auth_subject,
            or_(col(DocumentReviewControl.running).is_(True), col(DocumentReviewRun.lease_until) > datetime.now(UTC)))).all()
    if any(identifier != run_id for identifier in active):
        raise HTTPException(409, "Ein anderer Prüflauf ist noch aktiv. Diesen zuerst pausieren und seine laufende Anfrage abwarten.")


@router.get("")
def list_reviews(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    runs = session.exec(
        select(DocumentReviewRun).where(DocumentReviewRun.owner_subject == user.auth_subject)
        .order_by(col(DocumentReviewRun.created_at).desc()).limit(20)
    ).all()
    return [_summary(session, run) for run in runs]


@router.post("")
@limiter.limit("3/hour")
def create_review(request: Request, body: ReviewCreate | None = None,
                  user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _require_ai_availability("Prüfung")
    if body and body.start:
        _guard_active_run(session, user)
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
    if body and body.start:
        session.add(DocumentReviewControl(run_id=run.id, running=True))
    session.commit()
    logger.info("Review run created run=%s items=%s running=%s", run.id, len(document_ids), bool(body and body.start))
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
        # Checkpoints are private worker state. Expose only progress until complete.
        result.pop("checkpoint", None)
        result.pop("components", None)
        split = session.get(DocumentSplitRecord, item.contract_id)
        if split:
            from review_split_routes import visible_created

            result["split_created"] = visible_created(split, user, session)
        if result and result.get("schema_version") != PIPELINE_VERSION:
            result["legacy_report"] = True
            for change in result.get("changes", []):
                change["can_apply"] = False
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
            raise ReviewProcessingError("BUNDLE_SIZE", "Dokument und Anlagen überschreiten das Prüflimit von 32 MiB.")
        documents.append(data)
    return documents


@router.post("/{run_id}/start", status_code=202)
def start_review(run_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _require_ai_availability("Prüfung")
    run = _run(session, run_id, user)
    if run.model != MODEL:
        raise HTTPException(409, "Das Analysemodell wurde geändert. Bitte einen neuen Prüflauf starten.")
    _guard_active_run(session, user, run_id)
    control = session.get(DocumentReviewControl, run_id) or DocumentReviewControl(run_id=run_id)
    control.running, control.error = True, None
    session.add(control)
    session.commit()
    logger.info("Review run started run=%s", run.id)
    return _summary(session, run)


@router.post("/{run_id}/pause")
def pause_review(run_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    run = _run(session, run_id, user)
    control = session.get(DocumentReviewControl, run_id)
    if control:
        control.running = False
        session.add(control)
        session.commit()
    logger.info("Review run paused run=%s", run.id)
    return _summary(session, run)


@router.post("/{run_id}/next", status_code=202)
@limiter.limit("30/minute")
async def review_next(run_id: str, request: Request, background_tasks: BackgroundTasks,
                      user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return advance_review(run_id, background_tasks, user, session)


def advance_review(run_id: str, background_tasks: BackgroundTasks, user: User, session: Session):
    _require_ai_availability("Prüfung")
    run = _run(session, run_id, user)
    if run.model != MODEL:
        raise HTTPException(409, "Das Analysemodell wurde geändert. Bitte einen neuen Prüflauf starten.")
    now, token = datetime.now(UTC), str(uuid4())
    claimed = session.exec(update(DocumentReviewRun).where(
        col(DocumentReviewRun.id) == run_id,
        or_(col(DocumentReviewRun.lease_until).is_(None), col(DocumentReviewRun.lease_until) < now),
    ).values(lease_token=token, lease_until=now + timedelta(seconds=STEP_TIMEOUT + 30))
      .execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        session.rollback()
        return {"finished": False, "busy": True, "retry_after_ms": 3000}
    item = session.exec(select(DocumentReviewItem).where(
        DocumentReviewItem.run_id == run_id,
        col(DocumentReviewItem.status).in_(["pending", "processing"]),
    ).order_by(col(DocumentReviewItem.id))).first()
    if item is None:
        session.exec(update(DocumentReviewRun).where(col(DocumentReviewRun.id) == run_id)
                     .values(lease_until=None, lease_token=None))
        session.commit()
        return {"finished": True}
    if item.status == "processing":
        # The preceding lease expired, so its worker cannot be trusted to finish.
        # Mark the interruption once and let the queue move to other documents.
        item.status = "error"
        item.error = "Vorheriger Verarbeitungsschritt wurde unterbrochen oder seine Sperre ist abgelaufen. Bereits gescannte Seiten bleiben gespeichert."
        result = json.loads(item.result_json) if item.result_json else {}
        result["diagnostic"] = {"code": "INTERRUPTED", "stage": result.get("progress", {}).get("stage", "unknown"), "message": item.error}
        item.result_json = json.dumps(result, ensure_ascii=False)
        session.add(item)
        session.exec(update(DocumentReviewRun).where(col(DocumentReviewRun.id) == run_id)
                     .values(lease_until=None, lease_token=None))
        session.commit()
        return {"finished": False, "interrupted": True}
    document = _document(session, item.contract_id, user)
    item_id = item.id
    assert item_id is not None
    paths: list[str] = []
    names: list[str] = []
    skipped: list[str] = []
    if document is None:
        item.status, item.error = "skipped", "Dokument gelöscht oder Zugriff entzogen."
    elif document.file_extension != ".pdf":
        item.status, item.error = "skipped", "Die KI-Prüfung unterstützt derzeit nur PDF-Hauptdokumente."
    else:
        paths = [document.file_path]
        names = [Path(document.file_path).name]
        for attachment in document.attachments:
            if Path(attachment.file_path).suffix.lower() == ".pdf":
                paths.append(attachment.file_path)
                names.append(attachment.filename)
            else:
                skipped.append(attachment.filename)
        before = snapshot(document)
        prior = json.loads(item.snapshot_json) if item.snapshot_json else {}
        prior_result = json.loads(item.result_json) if item.result_json else {}
        if prior.get("version") != before["version"] or prior_result.get("schema_version") != PIPELINE_VERSION:
            item.result_json = None
        item.snapshot_json = json.dumps(before, ensure_ascii=False)
        item.status = "processing"
        item.error = None
    session.add(item)
    if not paths:
        session.exec(update(DocumentReviewRun).where(col(DocumentReviewRun.id) == run_id)
                     .values(lease_until=None, lease_token=None))
        session.commit()
        return {"finished": False}
    subject = user.auth_subject
    session.commit()
    background_tasks.add_task(process_review_step, session.get_bind(), run_id, item_id, token,
                              subject, paths, names, skipped)
    return {"finished": False, "busy": True, "item_id": item_id, "retry_after_ms": 3000}


@router.post("/{run_id}/retry")
def retry_errors(run_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _run(session, run_id, user)
    session.exec(update(DocumentReviewItem).where(
        col(DocumentReviewItem.run_id) == run_id, col(DocumentReviewItem.status) == "error"
    ).values(status="pending", error=None))
    session.commit()
    return {"ok": True}


@router.post("/{run_id}/items/{item_id}/decision")
def decide_review(run_id: str, item_id: int, body: ReviewDecision, request: Request,
                  user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _run(session, run_id, user)
    _lock_item(session, run_id, item_id)
    item = session.get(DocumentReviewItem, item_id)
    if not item or item.run_id != run_id or item.status not in {"issues", "hints", "checked", "applied"}:
        raise HTTPException(409, "Die Prüfung ist noch nicht abgeschlossen.")
    document = _document(session, item.contract_id, user, "write" if body.accept else "read")
    if document is None:
        raise HTTPException(404, "Dokument nicht gefunden.")
    result = json.loads(item.result_json or "{}")
    if result.get("schema_version") != PIPELINE_VERSION:
        raise HTTPException(409, "Bitte zuerst einen neuen Prüflauf starten.")
    decision = "accepted" if body.accept else "rejected"
    if result.get("decision"):
        if result["decision"] == decision:
            return {"ok": True}
        raise HTTPException(409, "Über diesen Vorschlag wurde bereits entschieden.")
    if json.loads(item.snapshot_json or "{}").get("version") != document.version:
        raise HTTPException(409, "Dokument inzwischen geändert. Bitte erneut prüfen.")
    fields = [change["field"] for change in result.get("changes", []) if change.get("can_apply")
              and change.get("after") is not None and change.get("status") in {"EXPLICIT_CONFLICT", "NEW_INFORMATION", "DERIVED"}]
    if body.accept and fields:
        _apply_review(run_id, item_id, ReviewApply(fields=fields), user, session, commit=False)
        result = json.loads(item.result_json or "{}")
    result["decision"] = decision
    result["decision_at"] = datetime.now(UTC).isoformat()
    item.result_json = json.dumps(result, ensure_ascii=False)
    session.add(item)
    log_audit(session, user.id, "REVIEW_DECISION", f"[CID:{document.id}] Prüfvorschlag {decision}.",
              contract_id=document.id, commit=False)
    session.commit()
    return {"ok": True}


@router.post("/{run_id}/items/{item_id}/apply")
def apply_review(run_id: str, item_id: int, body: ReviewApply, request: Request,
                 user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return _apply_review(run_id, item_id, body, user, session)


def _lock_item(session: Session, run_id: str, item_id: int):
    session.exec(update(DocumentReviewItem).where(
        col(DocumentReviewItem.id) == item_id, col(DocumentReviewItem.run_id) == run_id,
    ).values(status=DocumentReviewItem.status))
    session.expire_all()


def _apply_review(run_id: str, item_id: int, body: ReviewApply, user: User, session: Session, *, commit=True):
    _run(session, run_id, user)
    _lock_item(session, run_id, item_id)
    item = session.get(DocumentReviewItem, item_id)
    if not item or item.run_id != run_id or item.status not in {"issues", "hints"} or not item.result_json or not item.snapshot_json:
        raise HTTPException(409, "Kein übernehmbarer Prüfvorschlag vorhanden.")
    document = _document(session, item.contract_id, user, "write")
    if document is None:
        raise HTTPException(404, "Dokument nicht gefunden.")
    before = json.loads(item.snapshot_json)
    result = json.loads(item.result_json)
    if result.get("decision"):
        raise HTTPException(409, "Über diesen Vorschlag wurde bereits entschieden.")
    if result.get("schema_version") != PIPELINE_VERSION:
        raise HTTPException(409, "Dieser ältere Bericht kennt keine semantischen Belege. Bitte einen neuen Prüflauf starten.")
    changes = {change["field"]: change for change in result["changes"]}
    if any(field not in changes or not changes[field]["can_apply"] or changes[field]["after"] is None
           or changes[field]["status"] not in {"EXPLICIT_CONFLICT", "NEW_INFORMATION", "DERIVED"} for field in body.fields):
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
    for check in result.get("checks", []):
        if check["field"] in values:
            check.update(before=values[check["field"]], status="CONFIRMED", is_conflict=False, can_apply=False,
                         reason="Vorschlag durch den Nutzer übernommen.")
    result["applied_fields"] = sorted(set(result.get("applied_fields", []) + list(values)))
    item.result_json = json.dumps(result, ensure_ascii=False)
    item.snapshot_json = json.dumps(snapshot(document), ensure_ascii=False)
    item.status = result_status(result)
    if item.status == "checked":
        item.status = "applied"
    session.add(item)
    log_audit(session, user.id, "UPDATE_CONTRACT",
              f"[CID:{document.id}] KI-Prüfung: {', '.join(sorted(values))} übernommen (Modell {MODEL}).",
              contract_id=document.id, commit=False)
    if commit:
        session.commit()
    else:
        session.flush()
    return {"ok": True}
