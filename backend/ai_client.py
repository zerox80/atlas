"""Mistral client lifecycle, retry policy, and request deadlines."""

import asyncio
import logging
import os
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from ai_mistral_transport import MAX_REASONING_HEADER, create_mistral_http_client
from ai_models import is_glm_model
from ai_observability import observed_request

try:
    from mistralai import Mistral  # type: ignore[attr-defined]
except ImportError:
    from mistralai.client.sdk import Mistral

try:
    from mistralai.models import SDKError
except ImportError:
    from mistralai.client.errors.sdkerror import SDKError


MODEL = os.getenv("MISTRAL_CHAT_MODEL", "mistral-medium-3-5")
OCR_MODEL = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-4-0")
AI_REQUEST_TIMEOUT_SECONDS = max(
    10,
    int(os.getenv("MISTRAL_REQUEST_TIMEOUT_SECONDS", "900")),
)
MAX_RETRIES = 5
BASE_DELAY = 5
rate_limit_observer: ContextVar[Callable[[int, float], None] | None] = ContextVar("rate_limit_observer", default=None)

logger = logging.getLogger("atlas.ai")
_client = None


def get_reasoning_effort(
    model: str = MODEL, *, configured: str | None = None,
) -> Literal["none", "high", "max"]:
    """Resolve model-specific effort without downgrading GLM's max to high."""
    effort = (configured if configured is not None else os.getenv("MISTRAL_REASONING_EFFORT", "auto")).strip().lower()
    if effort == "auto":
        effort = "max" if is_glm_model(model) else "high"
    if effort == "high":
        return "high"
    if effort == "none":
        return "none"
    if effort == "max" and is_glm_model(model):
        return "max"
    allowed = "auto, none, high, max" if is_glm_model(model) else "auto, none, high"
    raise ValueError(
        f"MISTRAL_REASONING_EFFORT für {model} muss einer dieser Werte sein: {allowed}."
    )


def get_reasoning_options(model: str = MODEL, *, effort: str | None = None) -> dict[str, Any]:
    """Use SDK-native options or the transport override for GLM max."""
    effort = get_reasoning_effort(model, configured=effort)
    if effort == "max":
        return {"http_headers": {MAX_REASONING_HEADER: "max"}}
    return {"reasoning_effort": effort}


def extract_response_text(content: Any) -> str:
    """Extract answer text from Mistral content, excluding thinking chunks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts = []
    for chunk in content:
        if isinstance(chunk, dict):
            chunk_type, text = chunk.get("type"), chunk.get("text")
        else:
            chunk_type = getattr(chunk, "type", None)
            text = getattr(chunk, "text", None)
        if chunk_type == "text" and isinstance(text, str):
            parts.append(text)
    return "".join(parts)


async def retry_on_rate_limit(func: Callable, *args, **kwargs) -> Any:
    """Retry rate-limited SDK calls with exponential backoff."""
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            return await func(*args, **kwargs)
        except SDKError as error:
            if error.status_code != 429:
                raise
            last_exception = error
        if attempt == MAX_RETRIES - 1:
            break
        delay = max(BASE_DELAY * (2**attempt), _retry_after(last_exception))
        logger.warning(
            "Rate limit hit, waiting %ss before retry %s/%s",
            delay,
            attempt + 1,
            MAX_RETRIES,
        )
        observer = rate_limit_observer.get()
        if observer:
            observer(attempt + 2, delay)
        await asyncio.sleep(delay)
        if observer:
            observer(attempt + 2, 0)

    logger.error("Max retries (%s) exhausted for rate limit", MAX_RETRIES)
    raise last_exception or RuntimeError("Max retries exhausted")


def _retry_after(error: Exception | None) -> float:
    response = getattr(error, "raw_response", None)
    value = response.headers.get("retry-after") if response is not None else None
    if not value:
        return 0
    try:
        delay = float(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            delay = (parsed.replace(tzinfo=parsed.tzinfo or UTC) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0
    # The enclosing request deadline bounds even a very large Retry-After value.
    return max(0, delay) if delay < float("inf") else 0


def get_client() -> Mistral:
    """Get or lazily create the shared Mistral client."""
    global _client
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable not set")
    if _client is None:
        _client = Mistral(
            api_key=api_key,
            server_url="https://api.mistral.ai",
            async_client=create_mistral_http_client(),
            timeout_ms=AI_REQUEST_TIMEOUT_SECONDS * 1000,
        )
    return _client


async def complete_chat_with_timeout(client: Mistral, **kwargs: Any) -> Any:
    """Run a chat completion with one deadline covering retries and the request."""
    return await observed_request(
        retry_on_rate_limit(client.chat.complete_async, **kwargs),
        operation="chat", model=kwargs.get("model", MODEL),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
    )


async def stream_chunks_with_timeout(stream: Any):
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
