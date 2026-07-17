"""Create a complete, human-readable backup of contracts and invoices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence
import zipfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from file_utils import resolve_file_path
from models import Contract


MISSING_VALUE = "Nicht hinterlegt"
_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SAFE_EXTENSION = re.compile(r"^\.[a-z0-9]{1,10}$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class BackupIssue:
    document_type: str
    document_id: int
    title: str
    reason: str


@dataclass(frozen=True)
class DocumentBackupResult:
    path: str
    filename: str
    generated_at: datetime
    contract_count: int
    invoice_count: int
    attachment_count: int
    missing_attachment_count: int


def sanitize_windows_name(value: str | None, max_length: int = 100) -> str:
    """Return a safe Windows folder segment while retaining a readable title."""
    sanitized = _INVALID_WINDOWS_CHARS.sub("_", value or "")
    sanitized = " ".join(sanitized.split()).strip(" .")
    if not sanitized:
        sanitized = "Ohne Titel"

    sanitized = sanitized[:max_length].rstrip(" .") or "Ohne Titel"
    if sanitized.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        sanitized = f"_{sanitized}"
    return sanitized


def cleanup_backup_file(path: str) -> None:
    """Best-effort cleanup used both on failures and after the response finishes."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _document_label(document_type: str) -> str:
    return "Rechnung" if document_type == "invoice" else "Vertrag"


def _document_root(document_type: str) -> str:
    return "Rechnungen" if document_type == "invoice" else "Vertraege"


def _display_text(value: object | None) -> str:
    if value is None:
        return MISSING_VALUE
    text = str(value).strip()
    return text or MISSING_VALUE


def _format_datetime(value: date | datetime | None) -> str:
    if value is None:
        return MISSING_VALUE
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime("%d.%m.%Y %H:%M") + " UTC"
    return value.strftime("%d.%m.%Y")


def _format_money(value: float | None) -> str:
    if value is None:
        return MISSING_VALUE
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{formatted} €"


def _format_names(items: Sequence[object]) -> str:
    names = sorted(
        str(getattr(item, "name", "")).strip()
        for item in items
        if str(getattr(item, "name", "")).strip()
    )
    return ", ".join(names) if names else MISSING_VALUE


def _attachment_extension(file_path: str | None) -> str:
    extension = Path(file_path or "").suffix
    return extension if _SAFE_EXTENSION.fullmatch(extension.lower()) else ".bin"


def _attachment_error_reason(error: Exception) -> str:
    if isinstance(error, PermissionError):
        return "Ungültiger Speicherpfad außerhalb des Upload-Verzeichnisses"
    if isinstance(error, FileNotFoundError):
        return "Datei nicht auf dem Server gefunden"
    return "Datei konnte nicht gelesen werden"


def _info_pdf(document: Contract, file_type: str, file_status: str) -> bytes:
    from io import BytesIO

    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BackupTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=24,
        textColor=colors.HexColor("#172033"),
        alignment=TA_LEFT,
        spaceAfter=7 * mm,
    )
    label_style = ParagraphStyle(
        "BackupLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#5B6475"),
        spaceAfter=1 * mm,
    )
    value_style = ParagraphStyle(
        "BackupValue",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#172033"),
        spaceAfter=3.5 * mm,
        allowWidows=1,
        allowOrphans=1,
    )

    document_id = document.id or 0
    fields = [
        ("Dokumenttyp", _document_label(document.document_type)),
        ("ID", str(document_id)),
        ("Titel", _display_text(document.title)),
        ("Beschreibung", _display_text(document.description)),
        ("Start-/Rechnungsdatum", _format_datetime(document.start_date)),
        ("Enddatum", _format_datetime(document.end_date)),
        ("Wert", _format_money(document.value)),
        ("Jährlicher Wert", _format_money(document.annual_value)),
        (
            "Kündigungsfrist",
            f"{document.notice_period} Tage" if document.notice_period is not None else MISSING_VALUE,
        ),
        ("Tags", _format_names(document.tags)),
        ("Sammlungen", _format_names(document.lists)),
        ("Schutzstatus", "Ja" if document.is_protected else "Nein"),
        ("Version", str(document.version) if document.version is not None else MISSING_VALUE),
        ("Vorgänger-ID", str(document.parent_id) if document.parent_id is not None else MISSING_VALUE),
        ("Erfassungszeitpunkt", _format_datetime(document.uploaded_at)),
        ("Dateityp", file_type),
        ("Dateistatus", file_status),
    ]

    story = [
        Paragraph(
            f"{escape(_document_label(document.document_type))} #{document_id}",
            title_style,
        )
    ]
    for label, value in fields:
        story.append(Paragraph(escape(label), label_style))
        story.append(Paragraph(escape(_display_text(value)).replace("\n", "<br/>"), value_style))
        story.append(Spacer(1, 0.5 * mm))

    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Informationen zu {_document_label(document.document_type)} #{document_id}",
        author="Atlas",
    )
    pdf.build(story)
    return output.getvalue()


def _report_text(
    generated_at: datetime,
    contract_count: int,
    invoice_count: int,
    attachment_count: int,
    issues: Sequence[BackupIssue],
) -> bytes:
    lines = [
        "Atlas Dokument-Datensicherung",
        "==============================",
        "",
        f"Erstellt am: {generated_at.strftime('%d.%m.%Y %H:%M:%S')} UTC",
        f"Verträge: {contract_count}",
        f"Rechnungen: {invoice_count}",
        f"Exportierte Dateien: {attachment_count}",
        f"Fehlende oder ungültige Dateien: {len(issues)}",
        "",
    ]

    if issues:
        lines.append("Probleme bei Anhängen")
        lines.append("----------------------")
        for issue in issues:
            lines.append(
                f"- {issue.document_type} #{issue.document_id} - "
                f"{issue.title}: {issue.reason}"
            )
    else:
        lines.append("Alle hinterlegten Dateien wurden erfolgreich übernommen.")

    lines.extend(
        [
            "",
            "Hinweis: Dieses Archiv enthält vertrauliche Daten und ist nicht passwortgeschützt.",
        ]
    )
    # UTF-8 with BOM remains readable in older Windows Notepad versions.
    return ("\r\n".join(lines) + "\r\n").encode("utf-8-sig")


def create_document_backup(
    documents: Sequence[Contract],
    generated_at: datetime | None = None,
) -> DocumentBackupResult:
    """Write a ZIP backup to a temporary file and return its metadata."""
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    filename = f"atlas-datensicherung-{generated_at.strftime('%Y-%m-%d_%H-%M-%SZ')}.zip"
    file_descriptor, temporary_path = tempfile.mkstemp(prefix="atlas-backup-", suffix=".zip")
    os.close(file_descriptor)

    contract_count = sum(document.document_type == "contract" for document in documents)
    invoice_count = sum(document.document_type == "invoice" for document in documents)
    attachment_count = 0
    issues: list[BackupIssue] = []

    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            archive.writestr("Vertraege/", b"")
            archive.writestr("Rechnungen/", b"")

            for document in documents:
                document_id = document.id or 0
                document_label = _document_label(document.document_type)
                root = _document_root(document.document_type)
                folder = f"{document_id:06d} - {sanitize_windows_name(document.title)}"
                archive.writestr(f"{root}/{folder}/", b"")

                extension = _attachment_extension(document.file_path)
                file_type = extension if extension != ".bin" else MISSING_VALUE
                file_status = "Enthalten"
                try:
                    resolved_path = resolve_file_path(document.file_path)
                    archive.write(
                        resolved_path,
                        arcname=f"{root}/{folder}/Dokument{extension}",
                    )
                    attachment_count += 1
                except (FileNotFoundError, PermissionError, OSError) as error:
                    reason = _attachment_error_reason(error)
                    file_status = f"Nicht enthalten - {reason}"
                    issues.append(
                        BackupIssue(
                            document_type=document_label,
                            document_id=document_id,
                            title=_display_text(document.title),
                            reason=reason,
                        )
                    )

                archive.writestr(
                    f"{root}/{folder}/Informationen.pdf",
                    _info_pdf(document, file_type=file_type, file_status=file_status),
                )

            archive.writestr(
                "Sicherungsbericht.txt",
                _report_text(
                    generated_at=generated_at,
                    contract_count=contract_count,
                    invoice_count=invoice_count,
                    attachment_count=attachment_count,
                    issues=issues,
                ),
            )
    except Exception:
        cleanup_backup_file(temporary_path)
        raise

    return DocumentBackupResult(
        path=temporary_path,
        filename=filename,
        generated_at=generated_at,
        contract_count=contract_count,
        invoice_count=invoice_count,
        attachment_count=attachment_count,
        missing_attachment_count=len(issues),
    )
