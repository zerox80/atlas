"""PDF validation, rasterization, and OCR text preparation for AI requests."""

import asyncio
import base64
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ai_client import (
    AI_REQUEST_TIMEOUT_SECONDS,
    OCR_MODEL,
    get_client,
    retry_on_rate_limit,
)


OCR_TABLE_FORMAT = os.getenv("MISTRAL_OCR_TABLE_FORMAT", "markdown").lower()
OCR_CONFIDENCE_GRANULARITY = os.getenv(
    "MISTRAL_OCR_CONFIDENCE_GRANULARITY", "page"
).lower()
MAX_PDF_PAGES = max(1, int(os.getenv("MISTRAL_MAX_PDF_PAGES", "100")))
MAX_OCR_CHARACTERS = max(
    1, int(os.getenv("MISTRAL_MAX_OCR_CHARACTERS", "100000"))
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=3)


def use_ocr_mode() -> bool:
    """Check whether OCR mode is enabled."""
    return os.getenv("MISTRAL_USE_OCR", "true").lower() == "true"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_ocr_options() -> dict[str, Any]:
    """Build Mistral OCR options, including OCR 4 metadata features."""
    options: dict[str, Any] = {
        "model": OCR_MODEL,
        "include_blocks": _env_bool("MISTRAL_OCR_INCLUDE_BLOCKS", True),
    }
    if OCR_TABLE_FORMAT in {"markdown", "html"}:
        options["table_format"] = OCR_TABLE_FORMAT
    if OCR_CONFIDENCE_GRANULARITY in {"page", "word"}:
        options["confidence_scores_granularity"] = OCR_CONFIDENCE_GRANULARITY
    return options


def _get_attr_or_key(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _format_confidence_scores(confidence_scores: Any) -> str:
    if not confidence_scores:
        return ""
    average = _get_attr_or_key(confidence_scores, "average_page_confidence_score")
    minimum = _get_attr_or_key(confidence_scores, "minimum_page_confidence_score")
    parts = []
    if average is not None:
        parts.append(f"average={average}")
    if minimum is not None:
        parts.append(f"minimum={minimum}")
    return ", ".join(parts)


def _format_structural_blocks(blocks: list[Any]) -> str:
    if not blocks:
        return ""
    formatted_blocks = []
    for block in blocks:
        block_type = _get_attr_or_key(block, "type", "unknown")
        content = str(_get_attr_or_key(block, "content", "") or "").strip()
        if not content and block_type not in {"signature", "table", "image"}:
            continue
        content = re.sub(r"\s+", " ", content)
        if len(content) > 500:
            content = f"{content[:500]}..."
        formatted_blocks.append(f"- {block_type}: {content}")
    return "\n".join(formatted_blocks)


def format_ocr_text(ocr_response: Any) -> str:
    """Convert Mistral OCR pages into stable text for downstream prompts."""
    pages = _get_attr_or_key(ocr_response, "pages", []) or []
    formatted_pages = []
    for index, page in enumerate(pages, start=1):
        page_index = _get_attr_or_key(page, "index", index - 1)
        page_number = page_index + 1 if isinstance(page_index, int) else index
        markdown = str(_get_attr_or_key(page, "markdown", "") or "").strip()
        if not markdown:
            continue
        page_parts = [f"## Seite {page_number}", markdown]
        confidence = _format_confidence_scores(
            _get_attr_or_key(page, "confidence_scores")
        )
        if confidence:
            page_parts.append(f"OCR-Konfidenz: {confidence}")
        blocks = _format_structural_blocks(_get_attr_or_key(page, "blocks", []) or [])
        if blocks:
            page_parts.append(f"Strukturierte OCR-4-Blöcke:\n{blocks}")
        formatted_pages.append("\n\n".join(page_parts))

    result = "\n\n---\n\n".join(formatted_pages)
    if len(result) > MAX_OCR_CHARACTERS:
        return result[:MAX_OCR_CHARACTERS] + (
            "\n\n[Dokumenttext wegen Kontextlimit gekürzt]"
        )
    return result


def _process_pdf_to_images(pdf_bytes: bytes, max_pages: int) -> list[str]:
    import fitz

    images_base64 = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
            for page_num in range(min(max_pages, len(pdf_doc))):
                page = pdf_doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
                image_bytes = pix.tobytes("jpeg")
                encoded = base64.b64encode(image_bytes).decode()
                images_base64.append(f"data:image/jpeg;base64,{encoded}")
    except Exception as error:
        logger.error("Error processing PDF to images: %s", error)
        raise
    return images_base64


def _validate_pdf_limits(pdf_bytes: bytes) -> None:
    import fitz

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
            if pdf_doc.needs_pass:
                raise ValueError("Passwortgeschützte PDFs werden nicht unterstützt.")
            if len(pdf_doc) == 0:
                raise ValueError("Das PDF enthält keine Seiten.")
            if len(pdf_doc) > MAX_PDF_PAGES:
                raise ValueError(
                    f"Das PDF überschreitet das Limit von {MAX_PDF_PAGES} Seiten."
                )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Das PDF ist beschädigt oder ungültig.") from error


async def validate_pdf_for_ai(pdf_bytes: bytes) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _validate_pdf_limits, pdf_bytes)


async def process_pdf_to_images(
    pdf_bytes: bytes, max_pages: int = 8
) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, _process_pdf_to_images, pdf_bytes, max_pages
    )


async def process_pdf_with_ocr(pdf_bytes: bytes) -> str:
    """Process a PDF with Mistral OCR and return normalized page text."""
    client = get_client()
    pdf_base64 = base64.b64encode(pdf_bytes).decode()
    ocr_response = await asyncio.wait_for(
        retry_on_rate_limit(
            client.ocr.process_async,
            **build_ocr_options(),
            document={
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{pdf_base64}",
            },
        ),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
    )
    return format_ocr_text(ocr_response)
