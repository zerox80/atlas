"""Create independent PDFs only after an explicit review decision."""

import asyncio
import hashlib
import json
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, col, select, update

from api_core import check_contract_permission, check_workspace_permission, get_current_user
from contract_queries.forms import parse_date_form, validate_cancellation_date
from database import get_session
from document_review import _document, _lock_item, _read_bundle, _run
from file_utils import delete_upload_file, save_upload_file
from models import Contract, ContractPermission, DocumentReviewItem, DocumentSplitRecord, User
from review_schema import PIPELINE_VERSION
from schemas import ContractCreate
from security_utils import log_audit

router = APIRouter(prefix="/ai/reviews", tags=["document review"])


class SplitDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    accept: bool
    selected: list[int] = Field(default_factory=list, max_length=20)


def _extract_pdfs(data: list[bytes], proposals: list[dict]) -> list[bytes]:
    outputs = []
    used: set[tuple[int, int]] = set()
    with ExitStack() as stack:
        sources = [stack.enter_context(fitz.open(stream=pdf, filetype="pdf")) for pdf in data]
        for proposal in proposals:
            pages = proposal.get("pages", [])
            if not pages:
                raise HTTPException(409, "Seitenzuordnung fehlt. Bitte erneut prüfen.")
            with fitz.open() as target:
                for part in sorted(pages, key=lambda part: (part["document"], part["page"])):
                    doc, page = part["document"], part["page"]
                    if (doc < 1 or doc > len(sources) or page < 1 or page > len(sources[doc - 1])
                            or (doc, page) in used):
                        raise HTTPException(409, "Ungültige oder überlappende Seitenzuordnung. Bitte erneut prüfen.")
                    used.add((doc, page))
                    target.insert_pdf(sources[doc - 1], from_page=page - 1, to_page=page - 1)
                outputs.append(target.tobytes(garbage=3, deflate=True))
    return outputs


def visible_created(record: DocumentSplitRecord, user: User, session: Session) -> list[dict]:
    return [entry for entry in json.loads(record.created_json)
            if _document(session, entry["id"], user) is not None]


@router.post("/{run_id}/items/{item_id}/split")
async def decide_split(run_id: str, item_id: int, body: SplitDecision,
                       user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _run(session, run_id, user)
    _lock_item(session, run_id, item_id)
    item = session.get(DocumentReviewItem, item_id)
    if not item or item.run_id != run_id or item.status not in {"issues", "hints", "checked", "applied"}:
        raise HTTPException(409, "Die Prüfung ist noch nicht abgeschlossen.")
    source = _document(session, item.contract_id, user, "write" if body.accept else "read")
    if source is None:
        raise HTTPException(404, "Dokument nicht gefunden.")
    # Serialize splits from separate review runs against the same original.
    session.exec(update(Contract).where(col(Contract.id) == source.id).values(version=Contract.version))
    session.refresh(source)
    record = session.get(DocumentSplitRecord, item.contract_id)
    if record:
        return {"ok": True, "created": visible_created(record, user, session), "already_created": True}
    result = json.loads(item.result_json or "{}")
    proposals = result.get("split_proposals", [])
    if result.get("schema_version") != PIPELINE_VERSION or len(proposals) < 2:
        raise HTTPException(409, "Kein belegter Aufteilungsvorschlag vorhanden. Bitte erneut prüfen.")
    if not body.accept:
        result["split_declined"] = True
        item.result_json = json.dumps(result, ensure_ascii=False)
        session.add(item)
        session.commit()
        return {"ok": True, "created": []}
    if result.get("split_declined"):
        raise HTTPException(409, "Diese Aufteilung wurde abgelehnt. Für einen neuen Vorschlag erneut prüfen.")
    if json.loads(item.snapshot_json or "{}").get("version") != source.version:
        raise HTTPException(409, "Original inzwischen geändert. Bitte erneut prüfen.")
    if (not body.selected or len(set(body.selected)) != len(body.selected)
            or any(index < 0 or index >= len(proposals) for index in body.selected)):
        raise HTTPException(422, "Bitte gültige Einträge auswählen.")
    if any(not check_workspace_permission(user, workspace.id, "write", session) for workspace in source.lists):
        raise HTTPException(403, "Für neue Einträge sind Schreibrechte in den Arbeitsbereichen des Originals erforderlich.")
    paths = [source.file_path] + [attachment.file_path for attachment in source.attachments
                                  if Path(attachment.file_path).suffix.lower() == ".pdf"]
    data = await _read_bundle(paths)
    fingerprint = hashlib.sha256(b"".join(hashlib.sha256(pdf).digest() for pdf in data)).hexdigest()
    if fingerprint != result.get("source_fingerprint"):
        raise HTTPException(409, "Die PDF-Dateien wurden seit der Prüfung geändert. Bitte erneut prüfen.")
    selected = [proposals[index] for index in sorted(body.selected)]
    pdfs = await asyncio.to_thread(_extract_pdfs, data, selected)
    permissions = session.exec(select(ContractPermission).where(ContractPermission.contract_id == source.id)).all()
    created, files = [], []
    try:
        for proposal, pdf in zip(selected, pdfs, strict=True):
            values = dict(proposal["values"], document_type=proposal["document_type"])
            for field in ("start_date", "end_date"):
                if field in values:
                    values[field] = parse_date_form(values[field])
            validated = ContractCreate.model_validate(values).model_dump(exclude={"tags"})
            validate_cancellation_date(validated["end_date"], validated["notice_period"])
            upload = UploadFile(file=BytesIO(pdf), filename="document.pdf")
            try:
                path = await save_upload_file(upload)
            finally:
                await upload.close()
            files.append(path)
            document = Contract(**validated, file_path=path, owner_user_id=source.owner_user_id,
                                is_protected=source.is_protected)
            document.lists = list(source.lists)
            session.add(document)
            session.flush()
            for permission in permissions:
                session.add(ContractPermission(user_id=permission.user_id, contract_id=document.id,
                                               permission_level=permission.permission_level))
            session.flush()
            if not check_contract_permission(user, document.id, "write", session):
                raise HTTPException(403, "Die Berechtigungen konnten nicht vollständig übernommen werden.")
            created.append({"id": document.id, "title": document.title, "document_type": document.document_type})
            log_audit(session, user.id, "CREATE_CONTRACT", f"[CID:{document.id}] Aus Dokument {source.id} erstellt; Original erhalten.",
                      contract_id=document.id, commit=False)
        session.add(DocumentSplitRecord(contract_id=item.contract_id, source_fingerprint=fingerprint,
                                        created_json=json.dumps(created, ensure_ascii=False)))
        result["split_created"] = created
        item.result_json = json.dumps(result, ensure_ascii=False)
        session.add(item)
        log_audit(session, user.id, "SPLIT_DOCUMENT", f"[CID:{source.id}] {len(created)} eigenständige Dokumente mit eigenen PDFs angelegt.",
                  contract_id=source.id, commit=False)
        session.commit()
    except BaseException:
        session.rollback()
        for path in files:
            delete_upload_file(path)
        raise
    return {"ok": True, "created": created}
