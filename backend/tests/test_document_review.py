from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select
from test_review_semantics import extraction, observation

import ai_routes
import ai_service
import document_review
import review_worker
from api_core import ensure_default_workspace, limiter
from main import app, get_current_user
from models import Contract, ContractAttachment, ContractPermission, DocumentReviewRun
from review_analysis import Section


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setattr(ai_routes, "MISTRAL_DOCUMENT_PROCESSING_ENABLED", True)
    monkeypatch.setattr(document_review, "_read_bundle", AsyncMock(return_value=[b"primary", b"attachment"]))
    monkeypatch.setattr(review_worker, "prepare_sections", AsyncMock(return_value=([Section(1, "test.pdf", 1, 1, b"primary")], "fingerprint")))
    monkeypatch.setattr(review_worker, "analyze_bundle", AsyncMock(return_value=[extraction([])]))
    monkeypatch.setattr(review_worker, "scan_section", AsyncMock(return_value={1: "synthetic source"}))
    limiter.reset()


def document(session, user, **values):
    item = Contract(title="Alt", file_path="uploads/test.pdf", notice_period=30, **values)
    session.add(item)
    session.flush()
    session.add(ContractPermission(user_id=user.id, contract_id=item.id, permission_level="write"))
    session.commit()
    return item


def test_scope_has_no_page_cap_includes_invoices_and_protected_excludes_trash(admin_client, session):
    session.add_all([Contract(title=f"Dokument {i}", file_path="uploads/test.pdf", document_type="invoice" if i % 2 else "contract",
                             is_protected=True) for i in range(502)])
    session.add(Contract(title="Papierkorb", file_path="uploads/test.pdf", deleted_at=datetime.now(UTC)))
    session.commit()
    response = admin_client.post("/ai/reviews")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 502
    page = admin_client.get(f"/ai/reviews/{response.json()['id']}?offset=500").json()
    assert len(page["items"]) == 2


def test_review_extracts_bundle_and_applies_only_selected_fields(auth_client, session, test_user, monkeypatch):
    doc = document(session, test_user, document_type="invoice")
    doc_id = doc.id
    session.add(ContractAttachment(contract_id=doc_id, filename="AGB.pdf", file_path="uploads/agb.pdf", size=100))
    session.add(ContractAttachment(contract_id=doc_id, filename="Notiz.txt", file_path="uploads/note.txt", size=30))
    session.commit()
    analyze = AsyncMock(return_value=[extraction([
        observation("title", "Neu", "Neu"),
        observation("invoice_total_gross", 42, "Gesamt brutto 42,00 EUR", currency="EUR"),
    ])])
    monkeypatch.setattr(review_worker, "analyze_bundle", analyze)
    run = auth_client.post("/ai/reviews").json()
    endpoint = f"/ai/reviews/{run['id']}"
    assert auth_client.post(endpoint + "/next").status_code == 202
    assert auth_client.post(endpoint + "/next").status_code == 202
    analyze.assert_awaited_once()
    assert analyze.call_args.args[0][0].ocr_pages == {1: "synthetic source"}
    assert all(call.args[0] == ["uploads/test.pdf", "uploads/agb.pdf"] for call in document_review._read_bundle.call_args_list)
    page = auth_client.get(endpoint).json()
    assert page["remaining"] == 0
    item = page["items"][0]
    assert item["status"] == "issues"
    assert item["result"]["skipped_files"] == ["Notiz.txt"]
    assert session.get(Contract, doc_id).notice_period == 30
    assert session.get(Contract, doc_id).title == "Alt"
    apply = auth_client.post(endpoint + f"/items/{item['id']}/apply", json={"fields": ["notice_period"]})
    assert apply.status_code == 422, apply.text
    session.expire_all()
    stored = session.get(Contract, doc_id)
    assert stored.notice_period == 30
    assert stored.title == "Alt"
    assert stored.version == 1
    # Other selected fields remain reviewable after a partial application.
    assert auth_client.post(endpoint + f"/items/{item['id']}/apply", json={"fields": ["value"]}).status_code == 200
    assert session.get(Contract, doc_id).value == 42
    assert session.get(Contract, doc_id).version == 2
    assert auth_client.post(endpoint + f"/items/{item['id']}/apply", json={"fields": ["title"]}).status_code == 200


def test_permission_revocation_hides_results_and_blocks_apply(auth_client, session, test_user, monkeypatch):
    doc = document(session, test_user)
    doc_id = doc.id
    session.add(Contract(title="Geheim", file_path="uploads/secret.pdf"))
    session.commit()
    monkeypatch.setattr(review_worker, "analyze_bundle", AsyncMock(return_value=[extraction([observation("title", "Privater Befund", "Privater Befund")])]))
    run = auth_client.post("/ai/reviews").json()
    assert run["total"] == 1
    endpoint = f"/ai/reviews/{run['id']}"
    auth_client.post(endpoint + "/next")
    auth_client.post(endpoint + "/next")
    item_id = auth_client.get(endpoint).json()["items"][0]["id"]
    permission = session.exec(select(ContractPermission).where(ContractPermission.contract_id == doc_id)).one()
    session.delete(permission)
    session.commit()
    page = auth_client.get(endpoint)
    assert "Privater Befund" not in page.text and '"Alt"' not in page.text
    assert auth_client.post(endpoint + f"/items/{item_id}/apply", json={"fields": ["title"]}).status_code == 404


def test_foreign_review_is_private(auth_client, session, test_user, admin_user):
    run = auth_client.post("/ai/reviews").json()
    app.dependency_overrides[get_current_user] = lambda: admin_user
    assert auth_client.get(f"/ai/reviews/{run['id']}").status_code == 404
    assert auth_client.post(f"/ai/reviews/{run['id']}/next").status_code == 404


def test_failures_are_resumable_leased_and_do_not_expose_provider_text(auth_client, session, test_user, monkeypatch):
    doc = document(session, test_user)
    run = auth_client.post("/ai/reviews").json()
    endpoint = f"/ai/reviews/{run['id']}"
    monkeypatch.setattr(review_worker, "analyze_bundle", AsyncMock(side_effect=RuntimeError("SECRET SIGNATURE")))
    auth_client.post(endpoint + "/next")
    auth_client.post(endpoint + "/next")
    page = auth_client.get(endpoint)
    assert page.json()["counts"]["error"] == 1
    assert "SECRET" not in page.text
    auth_client.post(endpoint + "/retry")
    assert auth_client.get(endpoint).json()["remaining"] == 1
    stored = session.get(DocumentReviewRun, run["id"])
    stored.lease_until = datetime.now(UTC) + timedelta(minutes=1)
    session.add(stored)
    session.commit()
    response = auth_client.post(endpoint + "/next")
    assert response.status_code == 202 and response.json()["busy"]
    stored.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    session.add(stored)
    session.commit()
    monkeypatch.setattr(review_worker, "analyze_bundle", AsyncMock(return_value=[extraction([observation("title", "Neu", "Neu")])]))
    assert auth_client.post(endpoint + "/next").status_code == 202
    item = auth_client.get(endpoint).json()["items"][0]
    doc.version += 1
    session.add(doc)
    session.commit()
    assert auth_client.post(endpoint + f"/items/{item['id']}/apply", json={"fields": ["title"]}).status_code == 409
    assert session.get(Contract, doc.id).title == "Alt"


def test_missing_notice_stays_null_on_create_and_can_be_cleared(auth_client, session, test_user):
    workspace = ensure_default_workspace(session, test_user.id)
    session.commit()
    response = auth_client.post("/contracts", data={"title": "Keine Frist", "list_id": workspace.id},
                                files={"file": ("test.txt", b"test", "text/plain")})
    assert response.status_code == 200, response.text
    assert response.json()["notice_period"] is None
    doc = document(session, test_user)
    response = auth_client.put(f"/contracts/{doc.id}", data={"version": doc.version, "notice_period": ""})
    assert response.status_code == 200, response.text
    assert response.json()["notice_period"] is None


def test_unknown_notice_has_no_deadline():
    from contract_queries.business_time import (
        cancellation_deadline_utc,
        sqlite_business_cancellation_julianday,
    )
    assert cancellation_deadline_utc(datetime.now(UTC), None) is None
    assert sqlite_business_cancellation_julianday("2026-12-01", None) is None


async def test_bundle_refuses_truncated_ocr_instead_of_reporting_success(monkeypatch):
    monkeypatch.setattr(ai_service, "get_client", lambda: object())
    monkeypatch.setattr(ai_service, "validate_pdf_for_ai", AsyncMock())
    monkeypatch.setattr(ai_service, "_processed_document_payload", AsyncMock(return_value=("ocr", "[Dokumenttext wegen Kontextlimit gekürzt]")))
    complete = AsyncMock()
    monkeypatch.setattr(ai_service, "complete_chat_with_timeout", complete)
    with pytest.raises(ValueError, match="vollständige Prüfung"):
        await ai_service.analyze_document_bundle([b"pdf"])
    complete.assert_not_called()
