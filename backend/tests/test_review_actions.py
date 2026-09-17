"""Confirmed review actions, real PDF page extraction and source preservation."""

import hashlib
import json
from pathlib import Path

import fitz
import pytest
from sqlmodel import select
from test_review_semantics import extraction, observation

from document_review import snapshot
from models import Contract, ContractPermission, DocumentReviewItem, DocumentReviewRun
from review_comparison import build_review_result
from review_schema import DocumentSuggestion, PIPELINE_VERSION
from review_splits import verify_suggestions


def make_review(session, user, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("uploads").mkdir()
    texts = ["Veeam Rechnung\nGesamt brutto 119,00 EUR", "VMware Vertrag", "VMware Bedingungen"]
    with fitz.open() as pdf:
        for text in texts:
            pdf.new_page().insert_text((40, 60), text)
        data = pdf.tobytes()
    Path("uploads/original.pdf").write_bytes(data)
    source = Contract(title="Sammlung", value=500, file_path="uploads/original.pdf", owner_user_id=user.id,
                      is_protected=True)
    session.add(source)
    session.flush()
    session.add(ContractPermission(user_id=user.id, contract_id=source.id, permission_level="write"))
    run = DocumentReviewRun(owner_subject=user.auth_subject, model="test")
    session.add(run)
    session.flush()
    suggestions = [DocumentSuggestion.model_validate({"title": title, "document_type": kind,
        "pages": [{"document": 1, "page": page} for page in pages], "reason": "Eigenständiges Dokument",
        "evidence": {"document": 1, "page": pages[0], "quote": texts[pages[0] - 1].split("\n")[0]},
        "observations": facts}) for title, kind, pages, facts in [
            ("Veeam", "invoice", [1], [observation("invoice_total_gross", 119, "Gesamt brutto 119,00 EUR", currency="EUR")]),
            ("VMware", "contract", [2, 3], []),
        ]]
    proposals = verify_suggestions(suggestions, {1: dict(enumerate(texts, 1))}, {1: "original.pdf"})
    assert len(proposals) == 2
    result = build_review_result(snapshot(source), [extraction([observation("title", "Neuer Titel", "Neuer Titel")])], "contract")
    result.update(split_proposals=proposals, source_fingerprint=hashlib.sha256(hashlib.sha256(data).digest()).hexdigest())
    item = DocumentReviewItem(run_id=run.id, contract_id=source.id, status="hints",
                              result_json=json.dumps(result), snapshot_json=json.dumps(snapshot(source)))
    session.add(item)
    session.commit()
    return source, item, f"/ai/reviews/{run.id}/items/{item.id}", suggestions


@pytest.mark.parametrize("accept", [True, False])
def test_yes_no_is_persisted_atomic_and_idempotent(auth_client, session, test_user, tmp_path, monkeypatch, accept):
    source, item, url, _ = make_review(session, test_user, tmp_path, monkeypatch)
    for _ in range(2):
        response = auth_client.post(url + "/decision", json={"accept": accept})
        assert response.status_code == 200, response.text
    session.refresh(source)
    session.refresh(item)
    assert source.title == ("Neuer Titel" if accept else "Sammlung")
    assert source.version == (2 if accept else 1)
    assert json.loads(item.result_json)["decision"] == ("accepted" if accept else "rejected")
    assert auth_client.post(url + "/decision", json={"accept": not accept}).status_code == 409
    assert auth_client.post(url + "/apply", json={"fields": ["title"]}).status_code == 409


def test_no_changes_still_has_a_recordable_keep_proposal(auth_client, session, test_user, tmp_path, monkeypatch):
    source, item, url, _ = make_review(session, test_user, tmp_path, monkeypatch)
    item.result_json = json.dumps(build_review_result(snapshot(source), [extraction([])], "contract"))
    item.status = "checked"
    session.add(item)
    session.commit()
    assert auth_client.post(url + "/decision", json={"accept": True}).status_code == 200
    session.refresh(source)
    assert source.version == 1 and source.value == 500


def test_split_creates_real_independent_pdfs_once_and_preserves_original(auth_client, session, test_user, tmp_path, monkeypatch):
    source, item, url, _ = make_review(session, test_user, tmp_path, monkeypatch)
    original = Path(source.file_path).read_bytes()
    response = auth_client.post(url + "/split", json={"accept": True, "selected": [0, 1]})
    assert response.status_code == 200, response.text
    created = response.json()["created"]
    assert len(created) == 2
    assert auth_client.post(url + "/split", json={"accept": True, "selected": [0, 1]}).json()["created"] == created
    documents = [session.get(Contract, entry["id"]) for entry in created]
    assert documents[0].value == 119 and documents[1].value is None
    for doc, count, name in zip(documents, [1, 2], ["Veeam", "VMware"], strict=True):
        with fitz.open(doc.file_path) as pdf:
            assert len(pdf) == count and name in pdf[0].get_text()
        assert doc.is_protected and doc.owner_user_id == test_user.id
        acl = session.exec(select(ContractPermission).where(ContractPermission.contract_id == doc.id)).one()
        assert acl.user_id == test_user.id and acl.permission_level == "write"
    assert Path(source.file_path).read_bytes() == original
    session.refresh(source)
    assert source.title == "Sammlung" and source.value == 500 and source.version == 1
    # A later review cannot duplicate a completed split either.
    run = DocumentReviewRun(owner_subject=test_user.auth_subject, model="test")
    session.add(run)
    session.flush()
    later = DocumentReviewItem(run_id=run.id, contract_id=source.id, status="hints", result_json=item.result_json,
                               snapshot_json=item.snapshot_json)
    session.add(later)
    session.commit()
    assert auth_client.post(f"/ai/reviews/{run.id}/items/{later.id}/split", json={"accept": True, "selected": [0, 1]}).json()["created"] == created
    assert len(session.exec(select(Contract)).all()) == 3


@pytest.mark.parametrize("failure", ["version", "bytes", "permission", "selection", "declined"])
def test_split_rejects_unsafe_or_declined_creation(auth_client, session, test_user, tmp_path, monkeypatch, failure):
    source, item, url, _ = make_review(session, test_user, tmp_path, monkeypatch)
    if failure == "version":
        source.version += 1
        session.add(source)
        session.commit()
    if failure == "bytes":
        Path(source.file_path).write_bytes(b"changed")
    if failure == "permission":
        source.owner_user_id = None
        permission = session.exec(select(ContractPermission)).one()
        session.delete(permission)
        session.add(source)
        session.commit()
    if failure == "declined":
        assert auth_client.post(url + "/split", json={"accept": False}).status_code == 200
    response = auth_client.post(url + "/split", json={"accept": True, "selected": [99] if failure == "selection" else [0, 1]})
    assert response.status_code in {404, 409, 422}, response.text
    assert len(session.exec(select(Contract)).all()) == 1
    assert len(list(Path("uploads").iterdir())) == 1


def test_failed_second_pdf_rolls_back_database_and_first_file(auth_client, session, test_user, tmp_path, monkeypatch):
    import review_split_routes

    _, _, url, _ = make_review(session, test_user, tmp_path, monkeypatch)
    original_save = review_split_routes.save_upload_file
    calls = 0

    async def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            from fastapi import HTTPException
            raise HTTPException(507, "Quota exceeded")
        return await original_save(*args, **kwargs)

    monkeypatch.setattr(review_split_routes, "save_upload_file", fail_second)
    assert auth_client.post(url + "/split", json={"accept": True, "selected": [0, 1]}).status_code == 507
    assert len(session.exec(select(Contract)).all()) == 1
    assert len(list(Path("uploads").iterdir())) == 1


def test_mixed_sources_never_overwrite_original_total():
    before = {"title": "Sammlung", "description": None, "value": 500, "annual_value": None,
              "start_date": None, "end_date": None, "notice_period": None, "tags": []}
    extracted = extraction([observation("invoice_total_gross", 119, "Gesamt brutto 119,00 EUR", currency="EUR")])
    extracted["split_proposals"] = [{"title": "A"}, {"title": "B"}]
    result = build_review_result(before, [extracted], "invoice")
    value = next(check for check in result["checks"] if check["field"] == "value")
    assert not value["can_apply"] and value["status"] == "AMBIGUOUS"
    assert result["schema_version"] == PIPELINE_VERSION
