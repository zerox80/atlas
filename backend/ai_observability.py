"""Request lifecycle logs without prompts, credentials, or provider response bodies."""

import asyncio
import logging
import re
from collections.abc import Awaitable
from contextvars import ContextVar
from typing import TypeVar
from uuid import uuid4

T = TypeVar("T")
WAIT_LOG_INTERVAL = 30.0
review_context: ContextVar[str] = ContextVar("review_context", default="review=-")
logger = logging.getLogger("atlas.ai")


def response_finish_reason(response) -> str:
    """Log only known completion statuses, never arbitrary provider strings."""
    choices = getattr(response, "choices", None)
    if not choices:
        return "missing_choice"
    reason = getattr(choices[0], "finish_reason", None)
    return reason if reason in {"stop", "length", "model_length", "tool_calls", "error", "content_filter"} else "unknown"


def response_usage(response) -> str:
    usage = getattr(response, "usage", None)
    fields = []
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, name, None)
        fields.append(f"{name}={value if type(value) is int and value >= 0 else '-'}")
    return " ".join(fields)


def configure_ai_logging() -> None:
    """Emit application INFO logs to Docker stderr without enabling SDK debug logs."""
    application = logging.getLogger("atlas")
    application.setLevel(logging.INFO)
    if not application.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        application.addHandler(handler)


async def observed_request(
    request: Awaitable[T], *, operation: str, model: str, timeout: float,
) -> T:
    """Keep the original total deadline, reporting pending calls every 30 seconds."""
    started = asyncio.get_running_loop().time()
    # Model names are configuration, but still constrain them to a single log field.
    model_label = re.sub(r"[^a-zA-Z0-9_.:/-]", "_", model)[:100]
    label = f"request={uuid4().hex[:12]} operation={operation} model={model_label} {review_context.get()}"
    logger.info("Mistral request started %s timeout_seconds=%s", label, timeout)

    def elapsed() -> float:
        return asyncio.get_running_loop().time() - started

    async def report_wait() -> None:
        while True:
            await asyncio.sleep(WAIT_LOG_INTERVAL)
            logger.info("Mistral waiting for response %s elapsed_seconds=%.1f", label, elapsed())

    monitor = asyncio.create_task(report_wait())
    try:
        response = await asyncio.wait_for(request, timeout=timeout)
        logger.info("Mistral response received %s elapsed_seconds=%.1f%s", label, elapsed(),
                    f" finish_reason={response_finish_reason(response)} {response_usage(response)}" if operation == "chat" else "")
        return response
    except asyncio.CancelledError:
        logger.warning("Mistral request cancelled %s elapsed_seconds=%.1f", label, elapsed())
        raise
    except Exception as error:
        # SDK exception messages may contain the entire request/response. Log metadata only.
        status = getattr(error, "status_code", None)
        logger.warning(
            "Mistral request failed %s elapsed_seconds=%.1f error_type=%s http_status=%s",
            label, elapsed(), type(error).__name__, status if isinstance(status, int) else "-",
        )
        raise
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
