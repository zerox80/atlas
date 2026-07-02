"""
Mistral AI Service for Contract Analysis and Chat

Uses Mistral Large 3 for:
- PDF contract data extraction (auto-fill)
- Contract chatbot (Q&A)

Supports two modes (configurable via MISTRAL_USE_OCR env var):
- OCR mode (default): Uses Mistral OCR API for unlimited pages
- Image mode: Uses Vision API with max 8 pages
"""

from mistralai import Mistral
from mistralai.models import SDKError
import base64
import json
import os
import re
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any

# Initialize client (lazy - only when API key is available)
_client = None

MODEL = "mistral-large-latest"  # Mistral Large 3
OCR_MODEL = "mistral-ocr-latest"  # Mistral OCR model

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
            if "429" in error_str or "rate" in error_str or "limit" in error_str:
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


async def _process_pdf_with_ocr(pdf_bytes: bytes) -> str:
    """
    Process PDF using Mistral OCR API. Returns extracted text as markdown.
    Supports unlimited pages (no 8 image limit).
    """
    client = get_client()
    
    # Convert PDF to base64 for OCR API
    pdf_base64 = base64.b64encode(pdf_bytes).decode()
    
    # Call OCR API
    ocr_response = await _retry_on_rate_limit(
        client.ocr.process_async,
        model=OCR_MODEL,
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{pdf_base64}"
        }
    )
    
    # Extract text from all pages
    all_text = []
    if hasattr(ocr_response, 'pages') and ocr_response.pages:
        for page in ocr_response.pages:
            if hasattr(page, 'markdown') and page.markdown:
                all_text.append(page.markdown)
    
    return "\n\n---\n\n".join(all_text) if all_text else ""


async def analyze_contract_pdf(pdf_bytes: bytes) -> dict:
    """
    Analyze a PDF contract and extract structured data.
    Uses OCR or image mode based on MISTRAL_USE_OCR env var.
    
    Returns:
        dict with keys: title, description, value, start_date, end_date, notice_period, tags
    """
    client = get_client()
    
    if use_ocr_mode():
        # OCR mode: Extract text first, then analyze
        logger.info("Using OCR mode for contract analysis")
        document_text = await _process_pdf_with_ocr(pdf_bytes)
        
        if not document_text:
            raise ValueError("OCR konnte keinen Text aus dem PDF extrahieren")
        
        content = [{
            "type": "text",
            "text": f"""Hier ist der extrahierte Text eines Vertrags:

{document_text}

Analysiere diesen Vertrag sorgfältig und extrahiere die folgenden Informationen.
Antworte NUR mit einem validen JSON-Objekt, ohne zusätzlichen Text oder Erklärungen.

{{
    "title": "Kurzer, prägnanter Vertragstitel",
    "description": "Kurze Zusammenfassung des Vertrags (max 200 Zeichen)",
    "value": 0.0,
    "annual_value": 0.0,
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "notice_period": 30,
    "tags": ["Kategorie1", "Kategorie2"]
}}

Regeln:
- value: Der GESAMTWERT des Vertrags (falls berechenbar, sonst null). Berechne: (Summe aller monatlichen Kosten inkl. Versicherung/Steuer) * (Laufzeit in Monaten). Falls Laufzeit unbegrenzt/unbekannt: Nimm (Monatliche Kosten * 12).
- annual_value: Der jährliche Preis oder Basiswert (falls anwendbar). Z.B. monatliche Kosten * 12. Falls nicht zutreffend, null.
- start_date/end_date: Vertragslaufzeit im ISO-Format. Wenn kein Datum explizit genannt wird oder es z.B. unbefristet ist, setze das Feld zwingend auf null.
- notice_period: Kündigungsfrist in Tagen. Falls KEINE Frist explizit genannt ist, verwende null.
- tags: 1-3 passende Kategorien (z.B. "Software", "Lizenz", "Miete", "Service")
- WICHTIG: Wenn ein Wert nicht explizit im Text steht, gib null zurück. Erfinde KEINE Daten. Insbesondere bei Kündigungsfristen und Start-/Enddaten: Wenn unklar, nimm null!"""
        }]
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
        
        content.append({
            "type": "text",
            "text": """Analysiere diesen Vertrag sorgfältig und extrahiere die folgenden Informationen.
Antworte NUR mit einem validen JSON-Objekt, ohne zusätzlichen Text oder Erklärungen.

{
    "title": "Kurzer, prägnanter Vertragstitel",
    "description": "Kurze Zusammenfassung des Vertrags (max 200 Zeichen)",
    "value": 0.0,
    "annual_value": 0.0,
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "notice_period": 30,
    "tags": ["Kategorie1", "Kategorie2"]
}

Regeln:
- value: Der GESAMTWERT des Vertrags (falls berechenbar, sonst null). Berechne: (Summe aller monatlichen Kosten inkl. Versicherung/Steuer) * (Laufzeit in Monaten). Falls Laufzeit unbegrenzt/unbekannt: Nimm (Monatliche Kosten * 12).
- annual_value: Der jährliche Preis oder Basiswert (falls anwendbar). Z.B. monatliche Kosten * 12. Falls nicht zutreffend, null.
- start_date/end_date: Vertragslaufzeit im ISO-Format. Wenn kein Datum explizit genannt wird oder es z.B. unbefristet ist, setze das Feld zwingend auf null.
- notice_period: Kündigungsfrist in Tagen. Falls KEINE Frist explizit genannt ist, verwende null.
- tags: 1-3 passende Kategorien (z.B. "Software", "Lizenz", "Miete", "Service")
- WICHTIG: Wenn ein Wert nicht explizit im Text steht, gib null zurück. Erfinde KEINE Daten. Insbesondere bei Kündigungsfristen und Start-/Enddaten: Wenn unklar, nimm null!"""
        })
    
    response = await _retry_on_rate_limit(
        client.chat.complete_async,
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
    client = get_client()
    
    if use_ocr_mode():
        # OCR mode: Extract text first, then chat
        logger.info("Using OCR mode for contract chat")
        document_text = await _process_pdf_with_ocr(pdf_bytes)
        
        if not document_text:
            return "Fehler: OCR konnte keinen Text aus dem PDF extrahieren."
        
        content = [{
            "type": "text",
            "text": f"""Hier ist der extrahierte Text eines Vertrags:

{document_text}

Frage zum Vertrag: {question}"""
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
    
    response = await _retry_on_rate_limit(
        client.chat.complete_async,
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": """Du bist ein hilfreicher Vertragsassistent. 
Beantworte Fragen basierend auf dem bereitgestellten Vertragsdokument.
Sei präzise und verweise auf spezifische Abschnitte wenn möglich.
Wenn du etwas nicht im Dokument findest, sage das ehrlich."""
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
            "text": f"""Hier ist der extrahierte Text eines Vertrags:

{document_text}

Frage zum Vertrag: {question}"""
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
    stream_response = await client.chat.stream_async(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": """Du bist ein hilfreicher Vertragsassistent. 
Beantworte Fragen basierend auf dem bereitgestellten Vertragsdokument.
Sei präzise und verweise auf spezifische Abschnitte wenn möglich.
Wenn du etwas nicht im Dokument findest, sage das ehrlich."""
            },
            {
                "role": "user",
                "content": content
            }
        ]
    )
    
    # Yield each chunk as it arrives
    async for chunk in stream_response:
        if chunk.data.choices and len(chunk.data.choices) > 0:
            delta = chunk.data.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                yield delta.content

