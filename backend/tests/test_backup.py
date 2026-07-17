import io
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import zipfile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlmodel import select

import backup_export
import file_utils
import main
from backup_export import create_document_backup, sanitize_windows_name
from models import AuditLog, Contract, ContractList, Tag


def _zip(response) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(response.content))


def _pdf_text(archive: zipfile.ZipFile, path: str) -> str:
    reader = PdfReader(io.BytesIO(archive.read(path)))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _document_folder(archive: zipfile.ZipFile, root: str) -> str:
    folders = [
        name
        for name in archive.namelist()
        if name.startswith(f"{root}/") and name.count("/") == 2 and name.endswith("/")
    ]
    assert len(folders) == 1
    return folders[0]


class TestAdminDocumentBackupAccess:
    def test_requires_authentication(self, client: TestClient):
        response = client.post("/admin/backup")

        assert response.status_code == 401

    def test_rejects_regular_users(self, auth_client: TestClient):
        response = auth_client.post("/admin/backup")

        assert response.status_code == 403


class TestAdminDocumentBackupContent:
    def test_exports_documents_metadata_audit_and_cleans_temporary_file(
        self,
        admin_client: TestClient,
        admin_user,
        session,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        monkeypatch.setattr(file_utils, "UPLOAD_DIR", str(upload_dir))

        contract_bytes = b"%PDF-1.4\nunchanged-contract-attachment\n%%EOF"
        invoice_bytes = b"\x89PNG\r\n\x1a\nunchanged-invoice-attachment"
        contract_path = upload_dir / "contract.pdf"
        invoice_path = upload_dir / "invoice.png"
        contract_path.write_bytes(contract_bytes)
        invoice_path.write_bytes(invoice_bytes)

        tag = Tag(name="Prüfung & Wichtig", color="#123456")
        collection = ContractList(name="Einkauf Süd", description="Relevante Verträge")
        session.add(tag)
        session.add(collection)
        session.commit()

        long_description = "Über die jährliche Leistung für München. " * 220
        contract = Contract(
            title='Müller: Rahmen/Vertrag?*',
            description=long_description,
            start_date=datetime(2026, 1, 2, 8, 30, tzinfo=timezone.utc),
            end_date=datetime(2027, 1, 2, 8, 30, tzinfo=timezone.utc),
            file_path=str(contract_path),
            document_type="contract",
            uploaded_at=datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc),
            notice_period=90,
            value=1234.5,
            annual_value=600.25,
            is_protected=False,
            version=2,
            parent_id=77,
        )
        contract.tags.append(tag)
        contract.lists.append(collection)
        invoice = Contract(
            title="Jahresrechnung Köln",
            description=None,
            start_date=datetime(2026, 2, 3, 9, 45, tzinfo=timezone.utc),
            end_date=None,
            file_path=str(invoice_path),
            document_type="invoice",
            uploaded_at=datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
            notice_period=None,
            value=99.9,
            annual_value=None,
            is_protected=True,
            version=1,
            parent_id=None,
        )
        session.add(contract)
        session.add(invoice)
        session.commit()
        session.refresh(contract)
        session.refresh(invoice)

        generated_paths: list[str] = []
        original_create_backup = main.create_document_backup

        def capture_generated_path(documents):
            result = original_create_backup(documents)
            generated_paths.append(result.path)
            return result

        monkeypatch.setattr(main, "create_document_backup", capture_generated_path)

        response = admin_client.post("/admin/backup")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert re.search(
            r'filename="?atlas-datensicherung-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}Z\.zip"?',
            response.headers["content-disposition"],
        )
        assert generated_paths
        assert not os.path.exists(generated_paths[0])

        with _zip(response) as archive:
            names = archive.namelist()
            assert "Sicherungsbericht.txt" in names
            assert "Vertraege/" in names
            assert "Rechnungen/" in names

            contract_folder = _document_folder(archive, "Vertraege")
            invoice_folder = _document_folder(archive, "Rechnungen")
            contract_segment = contract_folder.split("/")[1]
            invoice_segment = invoice_folder.split("/")[1]
            assert contract_segment.startswith(f"{contract.id:06d} - ")
            assert invoice_segment.startswith(f"{invoice.id:06d} - ")
            assert not set('<>:"\\|?*').intersection(contract_segment)

            assert archive.read(f"{contract_folder}Dokument.pdf") == contract_bytes
            assert archive.read(f"{invoice_folder}Dokument.png") == invoice_bytes

            contract_pdf = _pdf_text(archive, f"{contract_folder}Informationen.pdf")
            invoice_pdf = _pdf_text(archive, f"{invoice_folder}Informationen.pdf")
            for label in (
                "Dokumenttyp",
                "ID",
                "Titel",
                "Beschreibung",
                "Start-/Rechnungsdatum",
                "Enddatum",
                "Wert",
                "Jährlicher Wert",
                "Kündigungsfrist",
                "Tags",
                "Sammlungen",
                "Schutzstatus",
                "Version",
                "Vorgänger-ID",
                "Erfassungszeitpunkt",
                "Dateityp",
                "Dateistatus",
            ):
                assert label in contract_pdf
            assert "Müller: Rahmen/Vertrag?*" in contract_pdf
            assert "Über die jährliche Leistung für München." in contract_pdf
            assert "Prüfung & Wichtig" in contract_pdf
            assert "Einkauf Süd" in contract_pdf
            assert "1.234,50 €" in contract_pdf
            assert "600,25 €" in contract_pdf
            assert "77" in contract_pdf
            assert "Enthalten" in contract_pdf

            assert "Rechnung" in invoice_pdf
            assert "Jahresrechnung Köln" in invoice_pdf
            assert "Ja" in invoice_pdf
            assert "Nicht hinterlegt" in invoice_pdf

            report = archive.read("Sicherungsbericht.txt").decode("utf-8-sig")
            assert "Verträge: 1" in report
            assert "Rechnungen: 1" in report
            assert "Exportierte Dateien: 2" in report
            assert "Fehlende oder ungültige Dateien: 0" in report

        audit = session.exec(
            select(AuditLog).where(AuditLog.action == "ADMIN_DOCUMENT_BACKUP")
        ).one()
        assert audit.user_id == admin_user.id
        assert "contracts=1" in audit.details
        assert "invoices=1" in audit.details
        assert "exported_files=2" in audit.details
        assert "missing_files=0" in audit.details

    def test_missing_and_external_files_are_reported_without_leaking_content(
        self,
        admin_client: TestClient,
        session,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        monkeypatch.setattr(file_utils, "UPLOAD_DIR", str(upload_dir))

        outside_file = tmp_path / "outside-secret.txt"
        outside_file.write_bytes(b"TOP-SECRET-OUTSIDE-UPLOADS")
        missing = Contract(
            title="Fehlender Vertrag",
            file_path=str(upload_dir / "missing.pdf"),
            document_type="contract",
        )
        external = Contract(
            title="Externe Rechnung",
            file_path=str(outside_file),
            document_type="invoice",
            is_protected=True,
        )
        session.add(missing)
        session.add(external)
        session.commit()
        session.refresh(missing)
        session.refresh(external)

        response = admin_client.post("/admin/backup")

        assert response.status_code == 200
        with _zip(response) as archive:
            names = archive.namelist()
            assert sum(name.endswith("Informationen.pdf") for name in names) == 2
            assert not any(Path(name).name.startswith("Dokument.") for name in names)
            assert b"TOP-SECRET-OUTSIDE-UPLOADS" not in response.content

            report = archive.read("Sicherungsbericht.txt").decode("utf-8-sig")
            assert f"Vertrag #{missing.id} - Fehlender Vertrag" in report
            assert "Datei nicht auf dem Server gefunden" in report
            assert f"Rechnung #{external.id} - Externe Rechnung" in report
            assert "Ungültiger Speicherpfad außerhalb des Upload-Verzeichnisses" in report
            assert "Fehlende oder ungültige Dateien: 2" in report

        audit = session.exec(
            select(AuditLog).where(AuditLog.action == "ADMIN_DOCUMENT_BACKUP")
        ).one()
        assert "exported_files=0" in audit.details
        assert "missing_files=2" in audit.details

    def test_empty_backup_is_a_valid_archive(self, admin_client: TestClient, session):
        response = admin_client.post("/admin/backup")

        assert response.status_code == 200
        with _zip(response) as archive:
            assert archive.testzip() is None
            assert {"Vertraege/", "Rechnungen/", "Sicherungsbericht.txt"}.issubset(
                archive.namelist()
            )
            report = archive.read("Sicherungsbericht.txt").decode("utf-8-sig")
            assert "Verträge: 0" in report
            assert "Rechnungen: 0" in report
            assert "Exportierte Dateien: 0" in report


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("A:B/C\\D?E*F", "A_B_C_D_E_F"),
        ("CON", "_CON"),
        ("...", "Ohne Titel"),
        (None, "Ohne Titel"),
    ],
)
def test_windows_safe_folder_names(title, expected):
    assert sanitize_windows_name(title) == expected


def test_generator_removes_temporary_file_when_creation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    temporary_path = tmp_path / "failed-backup.zip"

    def fake_mkstemp(**_kwargs):
        descriptor = os.open(temporary_path, os.O_CREAT | os.O_RDWR | os.O_TRUNC)
        return descriptor, str(temporary_path)

    def fail_pdf(*_args, **_kwargs):
        raise RuntimeError("PDF generation failed")

    monkeypatch.setattr(backup_export.tempfile, "mkstemp", fake_mkstemp)
    monkeypatch.setattr(backup_export, "_info_pdf", fail_pdf)
    document = Contract(id=1, title="Test", file_path="", document_type="contract")

    with pytest.raises(RuntimeError, match="PDF generation failed"):
        create_document_backup([document])

    assert not temporary_path.exists()
