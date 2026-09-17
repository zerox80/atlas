"""Process one OCR packet or the single final document analysis after the HTTP response has been sent."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, select, update

from ai_client import AI_REQUEST_TIMEOUT_SECONDS, MODEL, OCR_MODEL, rate_limit_observer
from ai_observability import review_context
from models import DocumentReviewItem, DocumentReviewRun, User
from review_analysis import REVIEW_REASONING_EFFORT, ReviewProcessingError, analyze_bundle, prepare_sections, scan_section
from review_comparison import build_review_result, result_status
from review_errors import error_details
from review_schema import PIPELINE_VERSION

# Guard one stage, with time for local preparation/persistence around a request.
# Each job performs one OCR request or one final analysis; completed OCR survives retries.
STEP_TIMEOUT = AI_REQUEST_TIMEOUT_SECONDS + 30
logger = logging.getLogger("atlas.review")


async def process_review_step(bind, run_id: str, item_id: int, token: str,
                                 subject: str, paths: list[str], names: list[str], skipped: list[str]):
    # A separate session owns the job; request dependency sessions may close as
    # soon as the small 202 response is delivered.
    from document_review import _document, _read_bundle

    with Session(bind) as session:
        item = session.get(DocumentReviewItem, item_id)
        if item is None or not item.snapshot_json:
            return
        before = json.loads(item.snapshot_json)
        result = json.loads(item.result_json) if item.result_json else {}
        checkpoint = result.get("checkpoint", {"completed": 0, "ocr": {}})
        result = {"schema_version": PIPELINE_VERSION, "checkpoint": checkpoint,
                  "progress": result.get("progress", {}), "model": MODEL, "ocr_model": OCR_MODEL,
                  "reasoning_effort": REVIEW_REASONING_EFFORT}
        user = session.exec(select(User).where(User.auth_subject == subject)).first()
        document = _document(session, item.contract_id, user) if user and user.is_active else None
        document_id = item.contract_id
        owner_id = user.id if user else None
        document_type = document.document_type if document else "contract"
        session.rollback()

    lease_until = datetime.now(UTC) + timedelta(seconds=STEP_TIMEOUT + 30)

    def save(status: str, error: str | None = None, release: bool = False):
        with Session(bind) as session:
            # The token also prevents a canceled or expired worker overwriting a retry.
            owned = session.exec(update(DocumentReviewRun).where(
                col(DocumentReviewRun.id) == run_id, col(DocumentReviewRun.lease_token) == token,
            ).values(**({"lease_token": None, "lease_until": None} if release else
                        {"lease_token": token, "lease_until": lease_until})))
            if owned.rowcount != 1:
                session.rollback()
                raise ReviewProcessingError("LEASE_LOST", "Dieser Verarbeitungsschritt wurde bereits von einem anderen Versuch übernommen.")
            current_user = session.exec(select(User).where(User.auth_subject == subject)).first()
            current = _document(session, document_id, current_user) if current_user and current_user.is_active else None
            if current is None:
                status, error, payload = "skipped", "Dokument gelöscht oder Zugriff entzogen.", None
            elif current.version != before["version"]:
                status, error, payload = "error", "Dokument während der Prüfung geändert. Ein erneuter Versuch beginnt mit der neuen Version.", None
            else:
                payload = json.dumps(result, ensure_ascii=False)
            session.exec(update(DocumentReviewItem).where(col(DocumentReviewItem.id) == item_id)
                         .values(status=status, error=error, result_json=payload))
            session.commit()
            return status

    def progress(stage: str):
        nonlocal lease_until
        started = datetime.now(UTC)
        now = started.isoformat()
        # Only actual stage transitions renew the deadline/lease. Heartbeats must
        # never keep a stuck provider call alive indefinitely.
        step_deadline.reschedule(asyncio.get_running_loop().time() + STEP_TIMEOUT)
        lease_until = started + timedelta(seconds=STEP_TIMEOUT + 30)
        result["progress"].update(stage=stage, stage_started_at=now, heartbeat_at=now,
                                  request_timeout_seconds=AI_REQUEST_TIMEOUT_SECONDS)
        if save("processing") != "processing":
            raise ReviewProcessingError("DOCUMENT_CHANGED", "Dokument wurde geändert oder ist nicht mehr zugänglich.")
        logger.info("Review stage run=%s item=%s stage=%s", run_id, item_id, stage)

    def rate_limited(attempt: int, delay: float):
        # A retry never renews the total request deadline.
        if delay:
            result["progress"].update(retry_attempt=attempt, retry_at=(datetime.now(UTC) + timedelta(seconds=min(delay, STEP_TIMEOUT))).isoformat())
        else:
            result["progress"].pop("retry_at", None)
            result["progress"].pop("retry_attempt", None)
        if save("processing") != "processing":
            raise ReviewProcessingError("DOCUMENT_CHANGED", "Dokument wurde geändert oder ist nicht mehr zugänglich.")

    async def heartbeat():
        while True:
            await asyncio.sleep(5)
            result["progress"]["heartbeat_at"] = datetime.now(UTC).isoformat()
            if save("processing") != "processing":
                return

    heartbeat_task = None
    stage = "read"
    context_token = review_context.set(f"run={run_id} item={item_id}")
    retry_token = rate_limit_observer.set(rate_limited)
    try:
        if document is None or owner_id is None:
            raise ReviewProcessingError("DOCUMENT_UNAVAILABLE", "Dokument ist nicht mehr zugänglich.")
        async with asyncio.timeout(STEP_TIMEOUT) as step_deadline:
            result["progress"].pop("retry_at", None)
            result["progress"].pop("retry_attempt", None)
            result["progress"].pop("section_timeout_seconds", None)
            result["progress"].update(section_started_at=datetime.now(UTC).isoformat())
            progress("read")
            heartbeat_task = asyncio.create_task(heartbeat())
            documents = await _read_bundle(paths)
            stage = "prepare"
            progress(stage)
            sections, fingerprint = await prepare_sections(documents, names)
            if checkpoint.get("fingerprint", fingerprint) != fingerprint:
                raise ReviewProcessingError("FILE_CHANGED", "Die PDF-Dateien wurden verändert. Bitte einen neuen Prüflauf starten.")
            checkpoint["fingerprint"] = fingerprint
            plan = {"sections": [[part.document, part.first_page, part.last_page] for part in sections],
                    "ocr_model": OCR_MODEL, "model": MODEL}
            if checkpoint.get("plan", plan) != plan:
                raise ReviewProcessingError("CONFIG_CHANGED", "OCR-Paketgröße oder KI-Modell wurde geändert. Bitte einen neuen Prüflauf starten.")
            checkpoint["plan"] = plan
            completed = checkpoint["completed"]
            if not sections or not 0 <= completed <= len(sections):
                raise ReviewProcessingError("INVALID_CHECKPOINT", "Zwischenstand passt nicht zu den Dokumenten. Bitte einen neuen Prüflauf starten.")
            # Restore all previous OCR packets after checking bytes and the scan plan.
            for part in sections[:completed]:
                cached = checkpoint["ocr"].get(str(part.document), {})
                expected = range(part.first_page, part.last_page + 1)
                if not all(isinstance(cached.get(str(page)), str) for page in expected):
                    raise ReviewProcessingError("INVALID_CHECKPOINT", "Gespeicherte OCR-Seiten fehlen. Bitte einen neuen Prüflauf starten.")
                part.ocr_pages = {page: cached[str(page)] for page in expected}
            total_pages = sum(part.last_page - part.first_page + 1 for part in sections)
            scanned_pages = sum(part.last_page - part.first_page + 1 for part in sections[:completed])
            files = [{"name": name, "pages": sum(part.last_page - part.first_page + 1 for part in sections if part.document == number)}
                     for number, name in enumerate(names, 1)]
            result["progress"].update(completed_sections=completed, total_sections=len(sections),
                                      completed_pages=0, ocr_completed_pages=scanned_pages, total_pages=total_pages, files=files)
            if completed < len(sections):
                section = sections[completed]
                result["progress"].update(document_name=section.name, first_page=section.first_page, last_page=section.last_page)
                pages = await scan_section(section, owner_id, progress)
                checkpoint["ocr"].setdefault(str(section.document), {}).update({str(page): text for page, text in pages.items()})
                checkpoint["completed"] = completed + 1
                result["progress"].update(completed_sections=completed + 1,
                                          ocr_completed_pages=scanned_pages + len(pages),
                                          stage="analysis_pending" if completed + 1 == len(sections) else "waiting")
                save("pending", release=True)
                logger.info("Review OCR saved run=%s item=%s scanned_pages=%s total_pages=%s", run_id, item_id,
                            result["progress"]["ocr_completed_pages"], total_pages)
            else:
                for key in ("document_name", "first_page", "last_page"):
                    result["progress"].pop(key, None)
                extractions = await analyze_bundle(sections, progress)
                final = build_review_result(before, extractions, document_type)
                final.update(progress={**result["progress"], "stage": "complete", "completed_pages": total_pages},
                             checked_files=len(paths), skipped_files=skipped, model=MODEL, ocr_model=OCR_MODEL,
                             reasoning_effort=REVIEW_REASONING_EFFORT)
                if skipped:
                    final["warnings"].append(f"Nicht geprüft (kein PDF): {', '.join(skipped)}")
                result = final
                saved_status = save(result_status(final), release=True)
                logger.info("Review document saved run=%s item=%s pages=%s status=%s", run_id, item_id, total_pages, saved_status)
    except asyncio.CancelledError:
        result["diagnostic"] = {"code": "INTERRUPTED", "stage": result["progress"].get("stage", stage),
                                "message": "Backend-Verarbeitung wurde unterbrochen. Bereits gescannte Seiten bleiben gespeichert."}
        save("error", result["diagnostic"]["message"], release=True)
        raise
    except Exception as exc:  # noqa: BLE001 - persist per-document failure without provider contents
        # Deliberately never log provider bodies, which can include document contents.
        result["diagnostic"] = error_details(exc, result["progress"].get("stage", stage), AI_REQUEST_TIMEOUT_SECONDS)
        logger.warning("Review step failed run=%s item=%s stage=%s code=%s error_type=%s",
                       run_id, item_id, result["progress"].get("stage", stage), result["diagnostic"]["code"], type(exc).__name__)
        try:
            save("error", result["diagnostic"]["message"], release=True)
        except ReviewProcessingError:
            pass  # A newer token owns the item now.
    finally:
        rate_limit_observer.reset(retry_token)
        review_context.reset(context_token)
        if heartbeat_task:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
