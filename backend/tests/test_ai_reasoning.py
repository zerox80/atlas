"""Exercise reasoning requests and responses through the real Mistral SDK."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest

import ai_client
import ai_document_processing
from ai_client import extract_response_text, get_reasoning_effort
from ai_errors import InvalidStructuredAIResponse
from ai_mistral_transport import MAX_REASONING_HEADER, create_mistral_http_client

THINKING = {
    "type": "thinking",
    "thinking": [{"type": "text", "text": '{"title": "Nur ein Entwurf"}'}],
}


@pytest.fixture(
    params=[
        ("mistral-medium-3-5", None, "high"),
        ("mistral-medium-3-5", "auto", "high"),
        ("mistral-medium-3-5", "high", "high"),
        ("mistral-medium-3-5", "none", "none"),
        ("zai-glm-5-3", None, "max"),
        ("zai-glm-5-3", "auto", "max"),
        ("zai-glm-5-3", "max", "max"),
        ("zai-glm-5-3", "high", "high"),
        ("zai-glm-5-3", "none", "none"),
        ("zai-glm-latest", "auto", "max"),
        ("zai-glm-latest", "max", "max"),
    ]
)
def reasoning_config(request):
    return request.param


@pytest.fixture
def service(monkeypatch, reasoning_config):
    import ai_service

    model, configured_effort, _ = reasoning_config
    if configured_effort is None:
        monkeypatch.delenv("MISTRAL_REASONING_EFFORT", raising=False)
    else:
        monkeypatch.setenv("MISTRAL_REASONING_EFFORT", configured_effort)
    monkeypatch.setenv("MISTRAL_USE_OCR", "true")
    monkeypatch.setattr(ai_service, "MODEL", model)
    monkeypatch.setattr(ai_document_processing, "MODEL", model)
    monkeypatch.setattr(ai_service, "validate_pdf_for_ai", AsyncMock())
    monkeypatch.setattr(
        ai_service,
        "_processed_document_payload",
        AsyncMock(return_value=("ocr", "Vertrag mit drei Monaten Kündigungsfrist")),
    )
    return ai_service


@pytest.fixture
def mistral_reply(monkeypatch, service):
    @asynccontextmanager
    async def reply(response):
        requests = []

        def handle(request):
            assert request.url.scheme == "https"
            assert request.url.host == "api.mistral.ai"
            assert request.url.path == "/v1/chat/completions"
            assert MAX_REASONING_HEADER not in request.headers
            assert request.headers["Authorization"] == "Bearer test-key"
            assert int(request.headers["Content-Length"]) == len(request.content)
            requests.append(json.loads(request.content))
            return response

        async with create_mistral_http_client(
            transport=httpx.MockTransport(handle)
        ) as http:
            monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
            monkeypatch.setattr(ai_client, "_client", None)
            monkeypatch.setattr(ai_client, "create_mistral_http_client", lambda: http)
            yield requests

    return reply


def completion_response(content, model):
    return httpx.Response(
        200,
        json={
            "id": "reasoning-test",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        },
    )


@pytest.mark.parametrize("operation", ["contract", "invoice", "chat"])
async def test_completions_request_reasoning_and_extract_only_the_answer(
    service, mistral_reply, reasoning_config, operation
):
    effort = reasoning_config[2]
    answer = (
        "Die Kündigungsfrist beträgt drei Monate."
        if operation == "chat"
        else '{"title": "Rahmenvertrag", "value": 1200}'
    )
    content = (
        answer
        if effort == "none"
        else [
            THINKING,
            {"type": "text", "text": answer[:12]},
            {"type": "text", "text": answer[12:]},
        ]
    )

    async with mistral_reply(completion_response(content, service.MODEL)) as requests:
        if operation == "chat":
            result = await service.chat_about_contract(b"pdf", "Kündigungsfrist?")
            assert result == answer
        else:
            result = await service.analyze_contract_pdf(b"pdf", operation)
            assert result["title"] == "Rahmenvertrag"
            assert result["value"] == 1200
            assert result["tags"] == []
            assert requests[0]["response_format"] == {"type": "json_object"}

    assert len(requests) == 1
    assert requests[0]["reasoning_effort"] == effort
    assert requests[0]["model"] == service.MODEL
    user_content = requests[0]["messages"][-1]["content"]
    assert user_content
    assert all(chunk["type"] == "text" for chunk in user_content)


@pytest.mark.parametrize("content", [None, [THINKING]])
async def test_analysis_rejects_missing_answer_even_with_json_in_thinking(
    service, mistral_reply, content
):
    async with mistral_reply(completion_response(content, service.MODEL)):
        with pytest.raises(InvalidStructuredAIResponse):
            await service.analyze_contract_pdf(b"pdf")


async def test_stream_preserves_answer_across_thinking_transition(
    service, mistral_reply, reasoning_config
):
    from ai_routes import _stream_chat_response

    effort = reasoning_config[2]
    deltas = [None, "Die Kündigungsfrist ", "beträgt drei Monate."]
    if effort != "none":
        deltas = [
            None,
            [THINKING],
            [
                {"type": "thinking", "thinking": [], "closed": True},
                {"type": "text", "text": "Die Kündigungsfrist "},
            ],
            "beträgt ",
            [{"type": "text", "text": "drei Monate."}],
        ]
    events = [
        {
            "id": "stream-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": service.MODEL,
            "choices": [
                {"index": 0, "delta": {"content": content}, "finish_reason": None}
            ],
        }
        for content in deltas
    ]
    events.append({**events[0], "choices": []})
    sse = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    response = httpx.Response(
        200,
        headers={"Content-Type": "text/event-stream"},
        text=sse + "data: [DONE]\n\n",
    )

    async with mistral_reply(response) as requests:
        output = [
            json.loads(event.removeprefix("data: "))
            async for event in _stream_chat_response(b"pdf", "Kündigungsfrist?", 1)
        ]

    assert output[-1] == "[DONE]"
    assert all(isinstance(part, str) and part for part in output)
    assert "".join(output[:-1]) == "Die Kündigungsfrist beträgt drei Monate."
    assert len(requests) == 1
    assert requests[0]["reasoning_effort"] == effort
    assert requests[0]["model"] == service.MODEL
    user_content = requests[0]["messages"][-1]["content"]
    assert user_content
    assert all(chunk["type"] == "text" for chunk in user_content)
    assert requests[0]["stream"] is True


def test_dict_chunks_only_include_top_level_answer_text():
    assert (
        extract_response_text(
            [
                THINKING,
                {"type": "text", "text": "Antwort"},
                {"type": "text", "text": None},
                {"type": "unknown", "text": "Kein Antworttext"},
            ]
        )
        == "Antwort"
    )


@pytest.mark.parametrize("effort", ["medium", "xhigh", ""])
@pytest.mark.parametrize("model", ["mistral-medium-3-5", "zai-glm-5-3"])
def test_unsupported_reasoning_effort_is_rejected(monkeypatch, effort, model):
    monkeypatch.setenv("MISTRAL_REASONING_EFFORT", effort)

    with pytest.raises(ValueError, match="MISTRAL_REASONING_EFFORT"):
        get_reasoning_effort(model)


def test_medium_rejects_glm_max_effort(monkeypatch):
    monkeypatch.setenv("MISTRAL_REASONING_EFFORT", "max")

    with pytest.raises(ValueError, match="mistral-medium-3-5"):
        get_reasoning_effort("mistral-medium-3-5")
