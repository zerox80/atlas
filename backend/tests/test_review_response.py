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
from ai_observability import review_context
from ai_errors import InvalidStructuredAIResponse
from ai_mistral_transport import MAX_REASONING_HEADER, create_mistral_http_client
from review_analysis import Section, analyze_bundle
from review_errors import error_details
from review_response import validation_issues
from review_schema import ReviewExtraction

SOURCE = "Gesamt netto: 120,00 EUR"
SECTION = Section(1, "synthetic.pdf", 5, 5, b"synthetic")


def valid_reply():
    fact = observation("invoice_total_net", 120, SOURCE, currency="EUR")
    fact["evidence"]["page"] = 5
    return {"document_type": "invoice", "observations": [fact], "warnings": []}


def invalid_reply():
    # Reproduce all five validation errors reported by the user.
    reply = valid_reply()
    del reply["observations"][0]["evidence"]
    del reply["observations"][0]["entity"]
    reply["observations"].append("UNTRUSTED_PROVIDER_TEXT")
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


async def test_one_combined_response_is_verified_without_rescanning(monkeypatch, ocr):
    complete = AsyncMock(return_value=response(valid_reply()))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    stages = []
    result = await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], stages.append)
    assert stages == ["analysis"]
    ocr.assert_not_awaited()
    complete.assert_awaited_once()
    assert result[0]["observations"][0]["evidence_verified"]
    assert complete.call_args.kwargs["response_format"]["type"] == "json_schema"


async def test_repeated_invalid_reply_fails_without_fabricating_defaults(monkeypatch, ocr):
    complete = AsyncMock(return_value=response(invalid_reply()))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(ValidationError) as raised:
        await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
    assert complete.await_count == 1
    diagnostic = error_details(raised.value, "analysis_retry", 300)
    assert diagnostic["code"] == "INVALID_AI_RESPONSE"
    assert len(diagnostic["validation_issues"]) == 4
    assert "UNTRUSTED_PROVIDER_TEXT" not in str(diagnostic)


@pytest.mark.parametrize("bad", [response("not JSON"), response(valid_reply(), "length"), SimpleNamespace(choices=[])])
async def test_incomplete_answers_do_not_trigger_another_analysis(monkeypatch, ocr, bad):
    complete = AsyncMock(return_value=bad)
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(InvalidStructuredAIResponse):
        await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
    assert complete.await_count == 1


@pytest.mark.parametrize("error", [TimeoutError(), httpx.ConnectError("synthetic")])
async def test_transport_failure_does_not_trigger_format_retry(monkeypatch, ocr, error):
    complete = AsyncMock(side_effect=error)
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(type(error)):
        await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
    assert complete.await_count == 1


@pytest.mark.parametrize("bad, reason, issue", [
    (response(invalid_reply()), "schema_validation", "observations.0.entity: missing"),
    (response("PRIVATE_INVALID_JSON"), "invalid_json", "validation_issues=-"),
    (response("PRIVATE_TRUNCATED", "length"), "incomplete_response", "finish_reason=length"),
    (SimpleNamespace(choices=[]), "incomplete_response", "finish_reason=missing_choice"),
])
async def test_rejection_logs_explain_failure_without_response_text(monkeypatch, ocr, caplog, bad, reason, issue):
    complete = AsyncMock(return_value=bad)
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    token = review_context.set("run=synthetic item=151")
    try:
        with pytest.raises((ValidationError, InvalidStructuredAIResponse)):
            await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
    finally:
        review_context.reset(token)
    messages = [record.message for record in caplog.records if "Review response rejected" in record.message]
    assert len(messages) == 1
    assert "retry=False" in messages[0]
    for message in messages:
        assert "run=synthetic item=151" in message
        assert f"reason={reason}" in message and issue in message
        assert "PRIVATE" not in message and "UNTRUSTED" not in message


async def test_corrected_schema_still_requires_verified_source_evidence(monkeypatch, ocr):
    forged = valid_reply()
    forged["observations"][0]["evidence"]["quote"] = "Gesamt netto: 900,00 EUR"
    complete = AsyncMock(return_value=response(forged))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    result = await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
    assert not result[0]["observations"][0]["evidence_verified"]
    assert result[0]["observations"][0]["confidence"] <= 0.4


def test_correction_feedback_redacts_unknown_keys_and_values():
    bad = deepcopy(valid_reply())
    bad["PRIVATE_KEY_FROM_PROVIDER"] = "PRIVATE_VALUE_FROM_PROVIDER"
    with pytest.raises(ValidationError) as raised:
        ReviewExtraction.model_validate(bad)
    prompt = "; ".join(validation_issues(raised.value))
    assert "unbekanntes Feld: extra_forbidden" in prompt
    assert "PRIVATE" not in prompt


@pytest.mark.parametrize(("model", "effort"), [("zai-glm-5-3", "max"), ("mistral-medium-3-5", "high")])
async def test_real_sdk_transmits_schema_and_preserves_reasoning(monkeypatch, ocr, model, effort):
    monkeypatch.setattr(review_analysis, "REVIEW_REASONING_EFFORT", effort)
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
        result = await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
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


async def test_default_review_uses_high_even_when_general_chat_uses_max(monkeypatch, ocr):
    monkeypatch.setenv("MISTRAL_REASONING_EFFORT", "max")
    monkeypatch.setattr(review_analysis, "MODEL", "zai-glm-5-3")
    monkeypatch.setattr(review_analysis, "REVIEW_REASONING_EFFORT", "high")
    complete = AsyncMock(return_value=response(valid_reply()))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    await analyze_bundle([Section(1, "synthetic.pdf", 5, 5, b"pdf", {5: SOURCE})], lambda stage: None)
    assert complete.call_args.kwargs["reasoning_effort"] == "high"


async def test_full_bundle_preserves_attachment_provenance(monkeypatch, ocr):
    reply = valid_reply()
    reply["observations"][0]["evidence"].update(document=2, page=1)
    complete = AsyncMock(return_value=response(reply))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    sections = [Section(1, "main.pdf", 1, 1, b"pdf", {1: "Upgrade plus Maintenance"}),
                Section(2, "bill.pdf", 1, 1, b"pdf", {1: SOURCE})]
    result = await analyze_bundle(sections, lambda stage: None)
    fact = result[1]["observations"][0]
    assert fact["evidence_verified"] and fact["document_name"] == "bill.pdf"
    prompt = complete.call_args.kwargs["messages"][1]["content"]
    assert "Upgrade plus Maintenance" in prompt and SOURCE in prompt
    complete.assert_awaited_once()


async def test_over_limit_text_fails_without_truncation_or_paid_analysis(monkeypatch, ocr):
    monkeypatch.setattr(review_analysis, "REVIEW_MAX_CHARACTERS", 20)
    complete = AsyncMock()
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    with pytest.raises(review_analysis.ReviewProcessingError, match="vollständige Text"):
        await analyze_bundle([Section(1, "big.pdf", 1, 1, b"pdf", {1: "x" * 30})], lambda stage: None)
    complete.assert_not_awaited()
