"""Mistral client lifecycle, retry policy, and request deadlines."""

import asyncio
import logging
import os
from typing import Any, Callable

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
    int(os.getenv("MISTRAL_REQUEST_TIMEOUT_SECONDS", "120")),
)
MAX_RETRIES = 5
BASE_DELAY = 2

logger = logging.getLogger(__name__)
_client = None


async def retry_on_rate_limit(func: Callable, *args, **kwargs) -> Any:
    """Retry rate-limited SDK calls with exponential backoff."""
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            return await func(*args, **kwargs)
        except SDKError as error:
            if error.status_code != 429:
                raise
            delay = BASE_DELAY * (2**attempt)
            logger.warning(
                "Rate limit hit, waiting %ss before retry %s/%s",
                delay,
                attempt + 1,
                MAX_RETRIES,
            )
            await asyncio.sleep(delay)
            last_exception = error
        except Exception as error:
            error_text = str(error).lower()
            if "429" not in error_text and "rate limit" not in error_text:
                raise
            delay = BASE_DELAY * (2**attempt)
            logger.warning(
                "Rate limit hit, waiting %ss before retry %s/%s",
                delay,
                attempt + 1,
                MAX_RETRIES,
            )
            await asyncio.sleep(delay)
            last_exception = error

    logger.error("Max retries (%s) exhausted for rate limit", MAX_RETRIES)
    raise last_exception or RuntimeError("Max retries exhausted")


def get_client() -> Mistral:
    """Get or lazily create the shared Mistral client."""
    global _client
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable not set")
    if _client is None:
        _client = Mistral(api_key=api_key)
    return _client


async def complete_chat_with_timeout(client: Mistral, **kwargs: Any) -> Any:
    """Run a chat completion with one deadline covering retries and the request."""
    return await asyncio.wait_for(
        retry_on_rate_limit(client.chat.complete_async, **kwargs),
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
