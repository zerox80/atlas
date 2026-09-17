"""Bounded, page-preserving review extraction using the configured Mistral model."""

import asyncio
import hashlib
import logging
import os
import re
from dataclasses import dataclass

from pydantic import ValidationError

from ai_client import (
    MODEL,
    complete_chat_with_timeout,
    extract_response_text,
    get_client,
    get_reasoning_options,
)
from ai_document_processing import MAX_OCR_CHARACTERS, MAX_PDF_PAGES, use_ocr_mode
from ai_errors import InvalidStructuredAIResponse
from ai_observability import response_finish_reason, review_context
from ai_service import _parse_analysis_response, _processed_document_payload
from review_evidence import verify_extraction
from review_prompts import REVIEW_SYSTEM_PROMPT, extraction_prompt
from review_response import correction_prompt, review_response_format, validation_issues
from review_schema import ReviewExtraction

SECTION_PAGES = max(1, min(10, int(os.getenv("MISTRAL_REVIEW_SECTION_PAGES", "4"))))
SECTION_CHARACTERS = max(4000, min(MAX_OCR_CHARACTERS, 30_000))
logger = logging.getLogger("atlas.review")


class ReviewProcessingError(ValueError):
    """An actionable, local error safe for the UI (never a provider response body)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass
class Section:
    document: int
    name: str
    first_page: int
    last_page: int
    pdf: bytes
    ocr_pages: dict[int, str] | None = None


def split_documents(documents: list[bytes], names: list[str]) -> tuple[list[Section], str]:
    import fitz

    try:
        enabled = use_ocr_mode()
    except ValueError as exc:
        raise ReviewProcessingError("OCR_REQUIRED", str(exc)) from exc
    if not enabled:
        raise ReviewProcessingError("OCR_REQUIRED", "Die semantische Prüfung benötigt MISTRAL_USE_OCR=true für überprüfbare Textbelege.")
    sections = []
    digest = hashlib.sha256()
    for number, (data, name) in enumerate(zip(documents, names, strict=True), 1):
        digest.update(hashlib.sha256(data).digest())
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise ReviewProcessingError("PDF_PASSWORD", f"{name}: Passwortgeschützte PDF kann nicht gelesen werden.")
                if not len(pdf):
                    raise ReviewProcessingError("PDF_EMPTY", f"{name}: Die PDF enthält keine Seiten.")
                if len(pdf) > MAX_PDF_PAGES:
                    raise ReviewProcessingError("PAGE_LIMIT", f"{name}: {len(pdf)} Seiten überschreiten MISTRAL_MAX_PDF_PAGES={MAX_PDF_PAGES}. "
                                               "Limit in der Backend-Umgebung erhöhen und Backend neu erstellen.")
                for start in range(0, len(pdf), SECTION_PAGES):
                    end = min(start + SECTION_PAGES, len(pdf))
                    with fitz.open() as part:
                        part.insert_pdf(pdf, from_page=start, to_page=end - 1)
                        sections.append(Section(number, name, start + 1, end, part.tobytes(no_new_id=True)))
        except ReviewProcessingError:
            raise
        except Exception as exc:
            raise ReviewProcessingError("INVALID_PDF", f"{name}: Die PDF ist beschädigt oder nicht lesbar.") from exc
    return sections, digest.hexdigest()


def section_pages(text: str, section: Section) -> dict[int, str]:
    if "[Dokumenttext wegen Kontextlimit gekürzt]" in text:
        raise ReviewProcessingError("OCR_CONTEXT_LIMIT", "OCR-Text dieses Abschnitts wurde gekürzt. MISTRAL_REVIEW_SECTION_PAGES reduzieren.")
    parts = re.split(r"(?m)^## Seite (\d+)\s*\n", text)
    pages = {int(parts[index]) + section.first_page - 1: parts[index + 1].strip()
             for index in range(1, len(parts), 2)}
    expected = set(range(section.first_page, section.last_page + 1))
    if set(pages) != expected:
        raise ReviewProcessingError("OCR_INCOMPLETE", "OCR lieferte nicht alle angeforderten Seiten. Die Prüfung ist unvollständig.")
    return pages


def text_sections(pages: dict[int, str]):
    """Split dense OCR too; retain source page labels on each fragment."""
    fragments: list[str] = []
    size = 0
    for page, text in pages.items():
        # Overlap retains quotes near a fragment boundary. Empty pages remain present.
        for offset in range(0, max(1, len(text)), SECTION_CHARACTERS - 2500):
            fragment = f"## Seite {page}\n{text[offset:offset + SECTION_CHARACTERS - 100]}"
            if fragments and size + len(fragment) > SECTION_CHARACTERS:
                yield "\n\n".join(fragments)
                fragments, size = [], 0
            fragments.append(fragment)
            size += len(fragment)
    if fragments:
        yield "\n\n".join(fragments)


async def analyze_section(section: Section, owner_id: int, progress) -> list[dict]:
    try:
        reasoning = get_reasoning_options(MODEL)
    except ValueError as exc:
        raise ReviewProcessingError("MODEL_CONFIGURATION", str(exc)) from exc
    if section.ocr_pages is None:
        progress("ocr")
        _, text = await _processed_document_payload(section.pdf, owner_id)
        if not isinstance(text, str):
            raise ReviewProcessingError("OCR_REQUIRED", "OCR-Text fehlt. MISTRAL_USE_OCR=true konfigurieren.")
        section.ocr_pages = section_pages(text, section)
    pages = section.ocr_pages
    results = []
    for fragment_number, fragment in enumerate(text_sections(pages), 1):
        prompt = extraction_prompt(fragment, section.document, section.first_page, section.last_page)
        feedback = ""
        # Each bounded request, including the correction, gets its own deadline.
        for attempt in range(2):
            progress("analysis_retry" if attempt else "analysis")
            response = await complete_chat_with_timeout(
                get_client(), model=MODEL, **reasoning,
                messages=[{"role": "system", "content": REVIEW_SYSTEM_PROMPT + feedback},
                          {"role": "user", "content": prompt}],
                response_format=review_response_format(),
            )
            try:
                if not response.choices or getattr(response.choices[0], "finish_reason", "stop") != "stop":
                    raise InvalidStructuredAIResponse("Incomplete review response")
                content = extract_response_text(response.choices[0].message.content)
                extraction = ReviewExtraction.model_validate(_parse_analysis_response(content))
            except (InvalidStructuredAIResponse, ValidationError) as exc:
                reason = ("schema_validation" if isinstance(exc, ValidationError) else
                          "incomplete_response" if response_finish_reason(response) != "stop" else "invalid_json")
                logger.warning(
                    "Review response rejected %s document=%s pages=%s-%s fragment=%s attempt=%s "
                    "reason=%s finish_reason=%s retry=%s validation_issues=%s",
                    review_context.get(), section.document, section.first_page, section.last_page,
                    fragment_number, attempt + 1, reason, response_finish_reason(response), not bool(attempt),
                    "; ".join(validation_issues(exc)) if isinstance(exc, ValidationError) else "-",
                )
                if attempt:
                    raise
                # Never replay provider text as instructions or expose it in diagnostics.
                feedback = "\n" + correction_prompt(exc)
                continue
            results.append(verify_extraction(extraction, pages, section.document, section.name))
            break
    return results


async def prepare_sections(documents: list[bytes], names: list[str]):
    return await asyncio.to_thread(split_documents, documents, names)
