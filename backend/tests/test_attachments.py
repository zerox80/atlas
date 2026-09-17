"""Multi-file documents remain atomic and inherit all document permissions."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import select

import contract_endpoints.attachments as attachment_storage
from api_core import limiter
from models import Contract, ContractAttachment, ContractPermission


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    limiter.reset()


def create_document(client, attachments=None):
    files = [("file", ("vertrag.txt", b"Hauptvertrag", "text/plain"))]
    files.extend(
        ("attachments", (name, content, "application/pdf"))
        for name, content in (attachments or [("Zusatz.pdf", b"%PDF-1.4\nZusatz")])
    )
    response = client.post("/contracts", data={"title": "Vertrag mit Anlagen"}, files=files)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_and_download_multiple_files_as_one_document(auth_client, session):
    document = create_document(auth_client, [
        ("Zusatz.pdf", b"%PDF-1.4\nZusatz"),
        ("Bedingungen.pdf", b"%PDF-1.4\nBedingungen"),
    ])
    assert len(session.exec(select(Contract)).all()) == 1
    assert len(document["attachments"]) == 2
    assert auth_client.get(f"/contracts/{document['id']}/download").content == b"Hauptvertrag"
    for attachment in document["attachments"]:
        assert "file_path" not in attachment
        assert attachment["size"] > 0
        response = auth_client.get(f"/contracts/{document['id']}/attachments/{attachment['id']}/download")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-1.4")
        assert attachment["filename"] in response.headers["content-disposition"]
    assert auth_client.get("/contracts").json()[0]["attachments"] == document["attachments"]


@pytest.mark.parametrize("extra_files, status", [
    ([("attachments", ("bad.pdf", b"\x00invalid", "application/pdf"))], 400),
    ([("attachments", (f"{i}.txt", b"text", "text/plain")) for i in range(10)], 422),
    ([("attachments", ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain"))], 413),
])
def test_rejects_invalid_batch_without_partial_document(auth_client, session, extra_files, status):
    response = auth_client.post("/contracts", data={"title": "Rejected"}, files=[
        ("file", ("main.txt", b"main", "text/plain")), *extra_files,
    ])
    assert response.status_code == status, response.text
    assert session.exec(select(Contract)).all() == []
    assert list(Path("uploads").glob("*")) == []


def test_failed_attachment_save_cleans_entire_batch(auth_client, session, monkeypatch):
    original_save = attachment_storage.save_upload_file

    async def failing_save(file):
        if file.filename == "fail.txt":
            raise HTTPException(status_code=507, detail="Storage full")
        return await original_save(file)

    monkeypatch.setattr(attachment_storage, "save_upload_file", failing_save)
    response = auth_client.post("/contracts", data={"title": "Rejected"}, files=[
        ("file", ("main.txt", b"main", "text/plain")),
        ("attachments", ("ok.txt", b"ok", "text/plain")),
        ("attachments", ("fail.txt", b"fail", "text/plain")),
    ])
    assert response.status_code == 507
    assert session.exec(select(Contract)).all() == []
    assert session.exec(select(ContractAttachment)).all() == []
    assert list(Path("uploads").glob("*")) == []


def test_edit_adds_and_removes_attachments_without_replacing_main(auth_client, session):
    document = create_document(auth_client)
    old_attachment = session.get(ContractAttachment, document["attachments"][0]["id"])
    old_path = old_attachment.file_path
    response = auth_client.put(f"/contracts/{document['id']}", data={
        "version": document["version"], "removed_attachment_ids": [old_attachment.id],
    }, files=[("attachments", ("Neu.txt", b"Neue Anlage", "text/plain"))])
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["version"] == document["version"] + 1
    assert [item["filename"] for item in updated["attachments"]] == ["Neu.txt"]
    assert not Path(old_path).exists()
    assert auth_client.get(f"/contracts/{document['id']}/download").content == b"Hauptvertrag"
    assert len(list(Path("uploads").glob("*"))) == 2


def test_failed_edit_preserves_existing_files_and_removes_new_uploads(auth_client, session):
    document = create_document(auth_client)
    original_paths = set(Path("uploads").glob("*"))
    response = auth_client.put(f"/contracts/{document['id']}", data={
        "version": document["version"], "tags": "unknown-tag-not-allowed",
        "removed_attachment_ids": [document["attachments"][0]["id"]],
    }, files=[
        ("file", ("replacement.txt", b"Replacement", "text/plain")),
        ("attachments", ("new.txt", b"New", "text/plain")),
    ])
    assert response.status_code == 403, response.text
    assert set(Path("uploads").glob("*")) == original_paths
    assert auth_client.get(f"/contracts/{document['id']}").json() == document
    assert len(session.exec(select(ContractAttachment)).all()) == 1


def test_attachment_cannot_be_accessed_through_another_document(auth_client):
    first = create_document(auth_client)
    second = create_document(auth_client)
    attachment_id = second["attachments"][0]["id"]
    assert auth_client.get(f"/contracts/{first['id']}/attachments/{attachment_id}/download").status_code == 404
    response = auth_client.put(f"/contracts/{first['id']}", data={
        "version": first["version"], "removed_attachment_ids": [attachment_id],
    })
    assert response.status_code == 404
    assert auth_client.get(f"/contracts/{second['id']}/attachments/{attachment_id}/download").status_code == 200


def test_attachment_permissions_follow_document(auth_client, session, test_user):
    Path("uploads").mkdir(exist_ok=True)
    Path("uploads/private.txt").write_text("private")
    document = Contract(title="Private", file_path="uploads/private.txt")
    document.attachments.append(ContractAttachment(
        filename="private.txt", file_path="uploads/private.txt", size=7,
    ))
    session.add(document)
    session.commit()
    session.refresh(document)
    attachment_id = document.attachments[0].id
    endpoint = f"/contracts/{document.id}/attachments/{attachment_id}/download"
    assert auth_client.get(endpoint).status_code == 404
    session.add(ContractPermission(user_id=test_user.id, contract_id=document.id, permission_level="read"))
    session.commit()
    assert auth_client.get(endpoint).content == b"private"
    assert auth_client.put(f"/contracts/{document.id}", data={
        "version": document.version, "removed_attachment_ids": [attachment_id],
    }).status_code == 404


def test_stale_version_does_not_add_or_remove_files(auth_client):
    document = create_document(auth_client)
    paths = set(Path("uploads").glob("*"))
    response = auth_client.put(f"/contracts/{document['id']}", data={
        "version": document["version"] + 1,
        "removed_attachment_ids": [document["attachments"][0]["id"]],
    }, files=[("attachments", ("new.txt", b"new", "text/plain"))])
    assert response.status_code == 409
    assert set(Path("uploads").glob("*")) == paths


def test_trash_restore_and_permanent_delete_include_attachments(admin_client, session):
    document = create_document(admin_client)
    contract_id = document["id"]
    download_url = f"/contracts/{contract_id}/attachments/{document['attachments'][0]['id']}/download"
    response = admin_client.delete(f"/contracts/{contract_id}", params={"version": document["version"]})
    assert response.status_code in (200, 204), response.text
    assert admin_client.get(download_url).status_code == 404
    assert len(list(Path("uploads").glob("*"))) == 2
    version = session.get(Contract, contract_id).version
    restored = admin_client.put(f"/trash/{contract_id}/restore", params={"version": version})
    assert restored.status_code == 200, restored.text
    assert restored.json()["attachments"] == document["attachments"]
    assert admin_client.get(download_url).status_code == 200
    admin_client.delete(f"/contracts/{contract_id}", params={"version": restored.json()["version"]})
    version = session.get(Contract, contract_id).version
    response = admin_client.delete(f"/trash/{contract_id}/permanent", params={"version": version})
    assert response.status_code == 204, response.text
    assert session.exec(select(ContractAttachment)).all() == []
    assert list(Path("uploads").glob("*")) == []


def test_backup_includes_additional_files(admin_client):
    create_document(admin_client)
    response = admin_client.post("/admin/backup")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        paths = [path for path in archive.namelist() if "/Anhaenge/" in path]
        assert len(paths) == 1
        assert archive.read(paths[0]) == b"%PDF-1.4\nZusatz"
