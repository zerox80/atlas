"""Preserve GLM max reasoning when the SDK omits unknown enum values."""

import json
from collections.abc import Generator

import httpx

MAX_REASONING_HEADER = "X-Atlas-Mistral-Reasoning"


class _MistralReasoningAuth(httpx.Auth):
    """Move a per-request SDK override into JSON before HTTP transmission."""

    requires_request_body = True

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        effort = request.headers.pop(MAX_REASONING_HEADER, None)
        if effort is None:
            yield request
            return

        payload = json.loads(request.content)
        if (
            effort != "max"
            or request.method != "POST"
            or request.url.scheme != "https"
            or request.url.host != "api.mistral.ai"
            or request.url.path != "/v1/chat/completions"
            or payload.get("model") != "zai-glm-5-3"
        ):
            raise ValueError("Max-Reasoning ist nur für GLM 5.3 über Mistral erlaubt.")

        # SDK 2.5.2 removes unrecognized reasoning enums during serialization.
        # The internal header carries this request's value across that step;
        # it is removed locally and never transmitted to the server.
        payload["reasoning_effort"] = effort
        headers = request.headers.copy()
        headers.pop("Content-Length", None)
        yield httpx.Request(
            request.method,
            request.url,
            headers=headers,
            json=payload,
            extensions=request.extensions,
        )


def create_mistral_http_client(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create the shared SDK transport, with optional transport injection."""
    return httpx.AsyncClient(auth=_MistralReasoningAuth(), transport=transport)
