"""Synthetic review replies; no provider calls or stored document access."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError
from test_ai_reasoning import completion_response
from test_review_semantics import observation

import ai_client
import review_analysis
from ai_errors import InvalidStructuredAIResponse
from ai_mistral_transport import MAX_REASONING_HEADER, create_mistral_http_client
from review_analysis import Section, analyze_section
from review_errors import error_details
from review_response import correction_prompt
from review_schema import ReviewExtraction

SOURCE = "Gesamt netto: 120,00 EUR"
SECTION = Section(1, "synthetic.pdf", 5, 5, b"synthetic")


def valid_reply():
    fact = observation("invoice_total_net", 120, SOURCE, currency="EUR")
    fact["evidence"]["page"] = 5
    return {"document_type": "invoice", "observations": [fact], "components": [], "warnings": []}


def invalid_reply():
    # Reproduce all five validation errors reported by the user.
    reply = valid_reply()
    del reply["observations"][0]["evidence"]
    del reply["observations"][0]["entity"]
    reply["observations"].append("UNTRUSTED_PROVIDER_TEXT")
    del reply["components"]
    del reply["warnings"]
    return reply


def response(payload, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason, message=SimpleNamespace(
            content=payload if isinstance(payload, str) else json.dumps(payload),
        ),
    )])


@pytest.fixture
def ocr(monkeypatch):
    payload = AsyncMock(return_value=("ocr", "## Seite 1\n" + SOURCE))
    monkeypatch.setattr(review_analysis, "_processed_document_payload", payload)
    monkeypatch.setattr(review_analysis, "get_client", lambda: object())
    monkeypatch.setenv("MISTRAL_REASONING_EFFORT", "auto")
    return payload


async def test_reported_missing_fields_are_corrected_once_with_original_source(monkeypatch, ocr):
    complete = AsyncMock(side_effect=[response(invalid_reply()), response(valid_reply())])
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    stages = []
    result = await analyze_section(SECTION, 1, stages.append)
    assert stages == ["ocr", "analysis", "analysis_retry"]
    assert ocr.await_count == 1 and complete.await_count == 2
    fact = result[0]["observations"][0]
    assert fact["value"] == 120 and fact["evidence_verified"]
    assert fact["evidence"]["page"] == 5 and fact["entity"] == "document"
    first, second = [call.kwargs for call in complete.call_args_list]
    assert first["response_format"]["type"] == "json_schema"
    assert second["response_format"] == first["response_format"]
    assert second["messages"][1] == first["messages"][1]
    feedback = second["messages"][0]["content"]
    for issue in ("observations.0.evidence: missing", "observations.0.entity: missing",
                  "observations.1: model_type", "components: missing", "warnings: missing"):
        assert issue in feedback
    assert "UNTRUSTED_PROVIDER_TEXT" not in str(second)


async def test_repeated_invalid_reply_fails_without_fabricating_defaults(monkeypatch, ocr):
    complete = AsyncMock(return_value=response(invalid_reply()))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(ValidationError) as raised:
        await analyze_section(SECTION, 1, lambda stage: None)
    assert complete.await_count == 2
    diagnostic = error_details(raised.value, "analysis_retry", 300)
    assert diagnostic["code"] == "INVALID_AI_RESPONSE"
    assert len(diagnostic["validation_issues"]) == 5
    assert "UNTRUSTED_PROVIDER_TEXT" not in str(diagnostic)


@pytest.mark.parametrize("bad", [response("not JSON"), response(valid_reply(), "length"), SimpleNamespace(choices=[])])
async def test_incomplete_answers_have_one_correction_attempt(monkeypatch, ocr, bad):
    complete = AsyncMock(return_value=bad)
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(InvalidStructuredAIResponse):
        await analyze_section(SECTION, 1, lambda stage: None)
    assert complete.await_count == 2


@pytest.mark.parametrize("error", [TimeoutError(), httpx.ConnectError("synthetic")])
async def test_transport_failure_does_not_trigger_format_retry(monkeypatch, ocr, error):
    complete = AsyncMock(side_effect=error)
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(type(error)):
        await analyze_section(SECTION, 1, lambda stage: None)
    assert complete.await_count == 1


async def test_corrected_schema_still_requires_verified_source_evidence(monkeypatch, ocr):
    forged = valid_reply()
    forged["observations"][0]["evidence"]["quote"] = "Gesamt netto: 900,00 EUR"
    complete = AsyncMock(side_effect=[response(invalid_reply()), response(forged)])
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    result = await analyze_section(SECTION, 1, lambda stage: None)
    assert not result[0]["observations"][0]["evidence_verified"]
    assert result[0]["observations"][0]["confidence"] <= 0.4


def test_correction_feedback_redacts_unknown_keys_and_values():
    bad = deepcopy(valid_reply())
    bad["PRIVATE_KEY_FROM_PROVIDER"] = "PRIVATE_VALUE_FROM_PROVIDER"
    with pytest.raises(ValidationError) as raised:
        ReviewExtraction.model_validate(bad)
    prompt = correction_prompt(raised.value)
    assert "unbekanntes Feld: extra_forbidden" in prompt
    assert "PRIVATE" not in prompt


@pytest.mark.parametrize(("model", "effort"), [("zai-glm-5-3", "max"), ("mistral-medium-3-5", "high")])
async def test_real_sdk_transmits_schema_and_preserves_reasoning(monkeypatch, ocr, model, effort):
    requests = []

    def handle(request):
        assert request.url == "https://api.mistral.ai/v1/chat/completions"
        assert MAX_REASONING_HEADER not in request.headers
        requests.append(json.loads(request.content))
        return completion_response(json.dumps(valid_reply()), model)

    async with create_mistral_http_client(transport=httpx.MockTransport(handle)) as http:
        client = ai_client.Mistral(api_key="test-key", server_url="https://api.mistral.ai", async_client=http)
        monkeypatch.setattr(review_analysis, "get_client", lambda: client)
        monkeypatch.setattr(review_analysis, "MODEL", model)
        result = await analyze_section(SECTION, 1, lambda stage: None)
    assert len(requests) == 1 and result[0]["observations"][0]["evidence_verified"]
    payload = requests[0]
    assert payload["model"] == model and payload["reasoning_effort"] == effort
    fmt = payload["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert "schema_definition" not in fmt["json_schema"]
    for node in [schema, *schema["$defs"].values()]:
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node["properties"])
    assert {"evidence", "entity"} <= set(schema["$defs"]["Observation"]["required"])
