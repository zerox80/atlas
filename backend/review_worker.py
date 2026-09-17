"""Process one persisted review section after the HTTP response has been sent."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, select, update

from ai_client import AI_REQUEST_TIMEOUT_SECONDS, MODEL, OCR_MODEL
from models import DocumentReviewItem, DocumentReviewRun, User
from review_analysis import ReviewProcessingError, analyze_section, prepare_sections
from review_comparison import build_review_result, result_status
from review_errors import error_details
from review_schema import PIPELINE_VERSION
from review_sections import expanded_sections, section_key

# Guard one stage, with time for local preparation/persistence around a request.
# A section can contain multiple text fragments and a format correction per fragment.
STEP_TIMEOUT = AI_REQUEST_TIMEOUT_SECONDS + 30
logger = logging.getLogger(__name__)


async def process_review_section(bind, run_id: str, item_id: int, token: str,
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
        checkpoint = result.get("checkpoint", {"completed": 0, "extractions": []})
        result = {"schema_version": PIPELINE_VERSION, "checkpoint": checkpoint,
                  "progress": result.get("progress", {}), "model": MODEL, "ocr_model": OCR_MODEL}
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
        if stage in {"analysis", "analysis_retry"} and section is not None:
            result["progress"]["ocr_completed_pages"] = result["progress"]["completed_pages"] + section.last_page - section.first_page + 1
            if section.ocr_pages is not None:
                cached = checkpoint.setdefault("ocr", {"document": section.document, "pages": {}})
                cached["pages"].update({str(page): text for page, text in section.ocr_pages.items()})
        if save("processing") != "processing":
            raise ReviewProcessingError("DOCUMENT_CHANGED", "Dokument wurde geändert oder ist nicht mehr zugänglich.")

    async def heartbeat():
        while True:
            await asyncio.sleep(5)
            result["progress"]["heartbeat_at"] = datetime.now(UTC).isoformat()
            if save("processing") != "processing":
                return

    heartbeat_task = None
    section = None
    stage = "read"
    try:
        if document is None or owner_id is None:
            raise ReviewProcessingError("DOCUMENT_UNAVAILABLE", "Dokument ist nicht mehr zugänglich.")
        async with asyncio.timeout(STEP_TIMEOUT) as step_deadline:
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
                raise ReviewProcessingError("CONFIG_CHANGED", "Abschnittsgröße oder KI-Modell wurde geändert. Bitte einen neuen Prüflauf starten.")
            checkpoint["plan"] = plan
            sections = expanded_sections(sections, checkpoint.get("splits", []))
            completed = checkpoint["completed"]
            if not sections or completed >= len(sections):
                raise ReviewProcessingError("INVALID_CHECKPOINT", "Zwischenstand passt nicht zu den Dokumenten. Bitte einen neuen Prüflauf starten.")
            section = sections[completed]
            # Restore OCR only after checking the file fingerprint and model plan.
            # Retain the remaining parent pages when an AI timeout split its PDF.
            cached = checkpoint.get("ocr", {})
            if cached.get("document") == section.document:
                pages = cached.get("pages", {})
                expected = range(section.first_page, section.last_page + 1)
                if all(isinstance(pages.get(str(page)), str) for page in expected):
                    section.ocr_pages = {page: pages[str(page)] for page in expected}
            else:
                checkpoint.pop("ocr", None)
            files = [{"name": name, "pages": sum(part.last_page - part.first_page + 1 for part in sections if part.document == number)}
                     for number, name in enumerate(names, 1)]
            result["progress"].update(completed_sections=completed, total_sections=len(sections),
                                      completed_pages=sum(part.last_page - part.first_page + 1 for part in sections[:completed]),
                                      total_pages=sum(part.last_page - part.first_page + 1 for part in sections),
                                      document_name=section.name, first_page=section.first_page, last_page=section.last_page,
                                      files=files)
            extractions = await analyze_section(section, owner_id, progress)
            checkpoint["extractions"].extend(extractions)
            checkpoint["completed"] = completed + 1
            if "ocr" in checkpoint:
                checkpoint["ocr"]["pages"] = {page: text for page, text in checkpoint["ocr"]["pages"].items()
                                               if int(page) > section.last_page}
                if not checkpoint["ocr"]["pages"]:
                    checkpoint.pop("ocr")
            result["progress"].pop("retry_message", None)
            result["progress"]["completed_sections"] = completed + 1
            result["progress"]["completed_pages"] += section.last_page - section.first_page + 1
            if completed + 1 == len(sections):
                final = build_review_result(before, checkpoint["extractions"], document_type)
                final.update(progress={**result["progress"], "stage": "complete"},
                             checked_files=len(paths), skipped_files=skipped, model=MODEL, ocr_model=OCR_MODEL)
                if skipped:
                    final["warnings"].append(f"Nicht geprüft (kein PDF): {', '.join(skipped)}")
                result = final
                save(result_status(final), release=True)
            else:
                result["progress"]["stage"] = "waiting"
                save("pending", release=True)
    except asyncio.CancelledError:
        result["diagnostic"] = {"code": "INTERRUPTED", "stage": result["progress"].get("stage", stage),
                                "message": "Backend-Verarbeitung wurde unterbrochen. Fertige Abschnitte bleiben gespeichert."}
        save("error", result["diagnostic"]["message"], release=True)
        raise
    except Exception as exc:  # noqa: BLE001 - persist per-document failure without provider contents
        # Deliberately never log provider bodies, which can include document contents.
        logger.warning("Review item %s failed at %s (%s)", item_id, result["progress"].get("stage", stage), type(exc).__name__)
        result["diagnostic"] = error_details(exc, result["progress"].get("stage", stage), AI_REQUEST_TIMEOUT_SECONDS)
        try:
            if result["diagnostic"]["code"] in {"TIMEOUT", "PROVIDER_HTTP_504"} and section and section.first_page < section.last_page:
                checkpoint.setdefault("splits", []).append(section_key(section))
                reason = "Anbieter-Zeitlimit (HTTP 504)" if result["diagnostic"]["http_status"] == 504 else "Zeitlimit"
                result["progress"].update(stage="retrying", total_sections=len(sections) + 1,
                                          retry_message=f"{reason} bei Seiten {section.first_page}–{section.last_page}. "
                                          "Dieser Seitenblock wird in kleineren Paketen erneut geprüft; fertige Seiten bleiben gespeichert.")
                result.pop("diagnostic", None)
                save("pending", release=True)
            else:
                result["progress"].pop("retry_message", None)
                save("error", result["diagnostic"]["message"], release=True)
        except ReviewProcessingError:
            pass  # A newer token owns the item now.
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
