"""
Mistral AI Service for Contract Analysis and Chat

Uses Mistral Large 3 for:
- PDF contract data extraction (auto-fill)
- Contract chatbot (Q&A)

Supports two modes (configurable via MISTRAL_USE_OCR env var):
- OCR mode (default): Uses Mistral OCR API within configured resource limits
- Image mode: Uses Vision API with max 8 pages
"""

import base64
import json
import os
import re
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any

from ai_prompts import (
    CONTRACT_ANALYSIS_PROMPT,
    CONTRACT_ASSISTANT_PROMPT,
    INVOICE_ANALYSIS_PROMPT,
    build_contract_question_prompt,
    build_ocr_analysis_prompt,
)

try:
    from mistralai import Mistral  # type: ignore[attr-defined]
except ImportError:  # mistralai 2.x exposes the client below the generated namespace.
    # Import the concrete module instead of the namespace re-export.  Some
    # 2.x builds expose ``mistralai`` as a namespace package, where
    # ``from mistralai.client import Mistral`` is not guaranteed to resolve.
    from mistralai.client.sdk import Mistral

try:
    from mistralai.models import SDKError
except ImportError:
    from mistralai.client.errors.sdkerror import SDKError

# Initialize client (lazy - only when API key is available)
_client = None

MODEL = os.getenv("MISTRAL_CHAT_MODEL", "mistral-medium-3-5")
OCR_MODEL = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-4-0")
OCR_TABLE_FORMAT = os.getenv("MISTRAL_OCR_TABLE_FORMAT", "markdown").lower()
OCR_CONFIDENCE_GRANULARITY = os.getenv("MISTRAL_OCR_CONFIDENCE_GRANULARITY", "page").lower()
MAX_PDF_PAGES = max(1, int(os.getenv("MISTRAL_MAX_PDF_PAGES", "100")))
MAX_OCR_CHARACTERS = max(1, int(os.getenv("MISTRAL_MAX_OCR_CHARACTERS", "100000")))
AI_REQUEST_TIMEOUT_SECONDS = max(
    10,
    int(os.getenv("MISTRAL_REQUEST_TIMEOUT_SECONDS", "120")),
)

# Retry configuration for rate limits
MAX_RETRIES = 5
BASE_DELAY = 2  # seconds

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Executor for CPU-bound tasks
_executor = ThreadPoolExecutor(max_workers=3)


def use_ocr_mode() -> bool:
    """Check if OCR mode is enabled (default: True)."""
    return os.getenv("MISTRAL_USE_OCR", "true").lower() == "true"


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse feature flags from env vars."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_attr_or_key(value: Any, name: str, default: Any = None) -> Any:
    """Read SDK model attributes and dict values through one small helper."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _build_ocr_options() -> dict[str, Any]:
    """Build Mistral OCR options. OCR 4 enables blocks and confidence scores."""
    options: dict[str, Any] = {
        "model": OCR_MODEL,
        "include_blocks": _env_bool("MISTRAL_OCR_INCLUDE_BLOCKS", True),
    }

    if OCR_TABLE_FORMAT in {"markdown", "html"}:
        options["table_format"] = OCR_TABLE_FORMAT

    if OCR_CONFIDENCE_GRANULARITY in {"page", "word"}:
        options["confidence_scores_granularity"] = OCR_CONFIDENCE_GRANULARITY

    return options


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


def _format_ocr_text(ocr_response: Any) -> str:
    """Convert Mistral OCR pages into stable text for downstream chat prompts."""
    pages = _get_attr_or_key(ocr_response, "pages", []) or []
    formatted_pages = []

    for index, page in enumerate(pages, start=1):
        page_index = _get_attr_or_key(page, "index", index - 1)
        page_number = page_index + 1 if isinstance(page_index, int) else index
        markdown = str(_get_attr_or_key(page, "markdown", "") or "").strip()
        if not markdown:
            continue

        page_parts = [f"## Seite {page_number}", markdown]

        confidence = _format_confidence_scores(_get_attr_or_key(page, "confidence_scores"))
        if confidence:
            page_parts.append(f"OCR-Konfidenz: {confidence}")

        blocks = _format_structural_blocks(_get_attr_or_key(page, "blocks", []) or [])
        if blocks:
            page_parts.append(f"Strukturierte OCR-4-Blöcke:\n{blocks}")

        formatted_pages.append("\n\n".join(page_parts))

    result = "\n\n---\n\n".join(formatted_pages)
    if len(result) > MAX_OCR_CHARACTERS:
        return (
            result[:MAX_OCR_CHARACTERS]
            + "\n\n[Dokumenttext wegen Kontextlimit gekürzt]"
        )
    return result


async def _retry_on_rate_limit(func: Callable, *args, **kwargs) -> Any:
    """
    Wrapper that retries API calls on rate limit (429) errors.
    Uses exponential backoff: 2s, 4s, 8s, 16s, 32s
    """
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            return await func(*args, **kwargs)
        except SDKError as e:
            # Check if it's a rate limit error (429)
            if e.status_code == 429:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(f"Rate limit hit, waiting {delay}s before retry {attempt + 1}/{MAX_RETRIES}")
                await asyncio.sleep(delay)
                last_exception = e
            else:
                # Not a rate limit error, re-raise immediately
                raise
        except Exception as e:
            # Check if error message contains rate limit info
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(f"Rate limit hit, waiting {delay}s before retry {attempt + 1}/{MAX_RETRIES}")
                await asyncio.sleep(delay)
                last_exception = e
            else:
                raise
    
    # All retries exhausted
    logger.error(f"Max retries ({MAX_RETRIES}) exhausted for rate limit")
    raise last_exception or Exception("Max retries exhausted")


def get_client() -> Mistral:
    """Get or create Mistral client."""
    global _client
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable not set")
    if _client is None:
        _client = Mistral(api_key=api_key)
    return _client


def _process_pdf_to_images(pdf_bytes: bytes, max_pages: int = 8) -> list[str]:
    """
    Blocking function to convert PDF bytes to base64 images.
    To be run in a thread pool. Used in image mode.
    """
    import fitz  # PyMuPDF
    
    images_base64 = []
    
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
            for page_num in range(min(max_pages, len(pdf_doc))):
                page = pdf_doc[page_num]
                # Render at 150 DPI for good quality
                pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))
                # Use JPEG to reduce data size
                img_bytes = pix.tobytes("jpeg")
                img_base64 = base64.b64encode(img_bytes).decode()
                images_base64.append(f"data:image/jpeg;base64,{img_base64}")
    except Exception as e:
        logger.error(f"Error processing PDF to images: {e}")
        raise
        
    return images_base64


def _validate_pdf_limits(pdf_bytes: bytes) -> None:
    """Reject malformed, encrypted, or excessive PDFs before an external API call."""
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


async def _validate_pdf_for_ai(pdf_bytes: bytes) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _validate_pdf_limits, pdf_bytes)


async def _process_pdf_with_ocr(pdf_bytes: bytes) -> str:
    """
    Process PDF using Mistral OCR 4. Returns extracted markdown plus OCR metadata.
    """
    client = get_client()
    
    # Convert PDF to base64 for OCR API
    pdf_base64 = base64.b64encode(pdf_bytes).decode()
    
    # Call OCR API
    ocr_options = _build_ocr_options()
    ocr_response = await asyncio.wait_for(
        _retry_on_rate_limit(
            client.ocr.process_async,
            **ocr_options,
            document={
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{pdf_base64}",
            },
        ),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
    )
    
    return _format_ocr_text(ocr_response)


async def _complete_chat_with_timeout(client: Mistral, **kwargs: Any) -> Any:
    """Run a chat completion with one deadline covering retries and the request."""
    return await asyncio.wait_for(
        _retry_on_rate_limit(client.chat.complete_async, **kwargs),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
    )


async def _stream_chunks_with_timeout(stream: Any):
    """Yield a stream while enforcing one total deadline, including idle periods."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + AI_REQUEST_TIMEOUT_SECONDS
    iterator = stream.__aiter__()

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("KI-Stream hat das Zeitlimit überschritten.")
        try:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        yield chunk


async def analyze_contract_pdf(pdf_bytes: bytes, document_type: str = "contract") -> dict:
    """
    Analyze a PDF contract and extract structured data.
    Uses OCR or image mode based on MISTRAL_USE_OCR env var.
    
    Returns:
        dict with keys: title, description, value, start_date, end_date, notice_period, tags
    """
    if document_type not in {"contract", "invoice"}:
        raise ValueError("Ungültiger Dokumenttyp.")

    await _validate_pdf_for_ai(pdf_bytes)
    client = get_client()
    
    if use_ocr_mode():
        # OCR mode: Extract text first, then analyze
        logger.info("Using OCR mode for contract analysis")
        document_text = await _process_pdf_with_ocr(pdf_bytes)
        
        if not document_text:
            raise ValueError("OCR konnte keinen Text aus dem PDF extrahieren")
        
        content = [{"type": "text", "text": build_ocr_analysis_prompt(document_text)}]
    else:
        # Image mode: Convert to images (max 8 pages)
        logger.info("Using image mode for contract analysis")
        loop = asyncio.get_running_loop()
        images_base64 = await loop.run_in_executor(
            _executor, 
            _process_pdf_to_images, 
            pdf_bytes, 
            8  # max pages (Mistral API limit: max 8 images per request)
        )
        
        content = []
        for img_b64 in images_base64:
            content.append({"type": "image_url", "image_url": img_b64})
        
        content.append({"type": "text", "text": CONTRACT_ANALYSIS_PROMPT})

    if document_type == "invoice":
        content.append({"type": "text", "text": INVOICE_ANALYSIS_PROMPT})

    response = await _complete_chat_with_timeout(
        client,
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": content
            }
        ],
        response_format={"type": "json_object"}
    )
    
    response_content = response.choices[0].message.content
    
    # helper for mypy/safety
    if not isinstance(response_content, str):
        response_content = "" if response_content is None else str(response_content)
    
    # Parse JSON response
    try:
        result = json.loads(response_content)
    except json.JSONDecodeError:
        # Try to extract JSON from response if wrapped in markdown
        json_match = re.search(r'\{[\s\S]*\}', response_content)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError:
                result = {}
        else:
            result = {}
    
    # Ensure all expected keys exist
    defaults: dict = {
        "title": None,
        "description": None,
        "value": None,
        "annual_value": None,
        "start_date": None,
        "end_date": None,
        "notice_period": None,
        "tags": []
    }
    
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
            
    return result


async def chat_about_contract(pdf_bytes: bytes, question: str) -> str:
    """
    Chat with AI about a specific contract.
    Uses OCR or image mode based on MISTRAL_USE_OCR env var.
    
    Args:
        pdf_bytes: The PDF file content
        question: User's question about the contract
        
    Returns:
        AI-generated answer
    """
    await _validate_pdf_for_ai(pdf_bytes)
    client = get_client()
    
    if use_ocr_mode():
        # OCR mode: Extract text first, then chat
        logger.info("Using OCR mode for contract chat")
        document_text = await _process_pdf_with_ocr(pdf_bytes)
        
        if not document_text:
            return "Fehler: OCR konnte keinen Text aus dem PDF extrahieren."
        
        content = [{
            "type": "text",
            "text": build_contract_question_prompt(document_text, question),
        }]
    else:
        # Image mode: Convert to images (max 8 pages)
        logger.info("Using image mode for contract chat")
        loop = asyncio.get_running_loop()
        images_base64 = await loop.run_in_executor(
            _executor, 
            _process_pdf_to_images, 
            pdf_bytes, 
            8  # max pages (Mistral API limit: max 8 images per request)
        )
        
        content = []
        for img_b64 in images_base64:
            content.append({"type": "image_url", "image_url": img_b64})
        
        content.append({
            "type": "text",
            "text": f"Frage zum Vertrag: {question}"
        })
    
    response = await _complete_chat_with_timeout(
        client,
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": CONTRACT_ASSISTANT_PROMPT,
            },
            {
                "role": "user",
                "content": content
            }
        ]
    )
    
    response_content = response.choices[0].message.content
    # Safety check for mypy - content can be str | None | list
    if not isinstance(response_content, str):
        response_content = "" if response_content is None else str(response_content)
    return response_content


async def chat_about_contract_stream(pdf_bytes: bytes, question: str):
    """
    Stream chat responses about a contract, token by token.
    Uses OCR or image mode based on MISTRAL_USE_OCR env var.
    
    Args:
        pdf_bytes: The PDF file content
        question: User's question about the contract
        
    Yields:
        str: Each token/chunk of the response as it arrives
    """
    await _validate_pdf_for_ai(pdf_bytes)
    client = get_client()
    
    if use_ocr_mode():
        # OCR mode: Extract text first, then chat
        logger.info("Using OCR mode for contract chat (streaming)")
        document_text = await _process_pdf_with_ocr(pdf_bytes)
        
        if not document_text:
            yield "Fehler: OCR konnte keinen Text aus dem PDF extrahieren."
            return
        
        content = [{
            "type": "text",
            "text": build_contract_question_prompt(document_text, question),
        }]
    else:
        # Image mode: Convert to images (max 8 pages)
        logger.info("Using image mode for contract chat (streaming)")
        loop = asyncio.get_running_loop()
        images_base64 = await loop.run_in_executor(
            _executor, 
            _process_pdf_to_images, 
            pdf_bytes, 
            8  # max pages (Mistral API limit: max 8 images per request)
        )
        
        content = []
        for img_b64 in images_base64:
            content.append({"type": "image_url", "image_url": img_b64})
        
        content.append({
            "type": "text",
            "text": f"Frage zum Vertrag: {question}"
        })
    
    # Use streaming API
    stream_response = await asyncio.wait_for(
        client.chat.stream_async(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": CONTRACT_ASSISTANT_PROMPT,
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
        ),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
    )
    
    # Yield each chunk as it arrives
    async for chunk in _stream_chunks_with_timeout(stream_response):
        if chunk.data.choices and len(chunk.data.choices) > 0:
            delta = chunk.data.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                yield delta.content
