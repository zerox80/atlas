import json

import httpx
import pytest
from pydantic import ValidationError

import notice_research as research
from api_core import limiter


@pytest.fixture(autouse=True)
def config(monkeypatch):
    limiter.reset()
    monkeypatch.setenv("NOTICE_RESEARCH_PROVIDER", "disabled")
    monkeypatch.delenv("NOTICE_RESEARCH_MODEL", raising=False)
    monkeypatch.delenv("NOTICE_RESEARCH_API_KEY", raising=False)


@pytest.mark.parametrize("query", [
    "Tarif für kunde@example.com", "Kündigungsfrist Kundennummer 12", "Tarif +49 170 12345678",
    "Kündigungsfrist IBAN DE89 3704 0044 0532 0130 00", "Vertrag für Herrn Mustermann",
])
def test_private_identifiers_are_rejected(query):
    with pytest.raises(ValidationError):
        research.ResearchRequest(query=query, confirmed_public=True)


def test_confirmation_and_allowlisted_request_fields_are_required():
    for data in [
        {"query": "Magenta L", "confirmed_public": False},
        {"query": "Magenta L", "confirmed_public": True, "ocr_text": "Private signature"},
        {"query": "Magenta L", "confirmed_public": True, "contract_id": 1},
    ]:
        with pytest.raises(ValidationError):
            research.ResearchRequest(**data)


@pytest.mark.parametrize("provider", ["mistral", "openai"])
async def test_wire_payload_contains_only_public_query_and_independent_config(monkeypatch, provider):
    monkeypatch.setenv("NOTICE_RESEARCH_PROVIDER", provider)
    monkeypatch.setenv("NOTICE_RESEARCH_API_KEY", "search-only-key")
    monkeypatch.setenv("MISTRAL_CHAT_MODEL", "zai-glm-latest")
    monkeypatch.setenv("MISTRAL_REASONING_EFFORT", "max")
    query = "Kündigungsfrist Magenta L Deutschland 2024"
    source = {"title": "AGB", "url": "https://example.com/agb"}
    requests = []

    def handle(request):
        requests.append(request)
        if provider == "mistral":
            data = {"outputs": [
                {"type": "tool.execution", "name": "web_search"},
                {"type": "message.output", "content": [
                    {"type": "text", "text": "Öffentliche Bedingungen."},
                    {"type": "tool_reference", "tool": "web_search", **source},
                ]},
            ]}
        else:
            data = {"output": [
                {"type": "web_search_call", "status": "completed"},
                {"type": "message", "content": [{"type": "output_text", "text": "Öffentliche Bedingungen.",
                    "annotations": [{"type": "url_citation", **source}]}]},
            ]}
        return httpx.Response(200, json=data)

    original = httpx.AsyncClient
    monkeypatch.setattr(research.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    result = await research.research_public_query(query)
    payload = json.loads(requests[0].content)
    assert requests[0].headers["Authorization"] == "Bearer search-only-key"
    assert requests[0].url.host == ("api.mistral.ai" if provider == "mistral" else "api.openai.com")
    assert payload["store"] is False
    assert payload.get("inputs", payload.get("input")) == query
    assert payload["model"] != "zai-glm-latest"
    if provider == "mistral":
        assert payload["model"] == "mistral-medium-latest"
        assert payload["completion_args"].get("tool_choice", "auto") == "auto"
    assert not set(payload) & {"messages", "conversation", "previous_response_id", "metadata", "document", "reasoning_effort", "agent_id"}
    assert result["sources"] == [source]


def test_search_is_independent_and_disabled_by_default(auth_client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "document-key")
    assert auth_client.get("/ai/notice-research").json()["available"] is False
    assert auth_client.post("/ai/notice-research", json={"query": "Magenta L", "confirmed_public": True}).status_code == 503
    monkeypatch.setenv("NOTICE_RESEARCH_PROVIDER", "mistral")
    monkeypatch.setenv("NOTICE_RESEARCH_MODEL", "zai-glm-latest")
    assert auth_client.get("/ai/notice-research").json()["available"] is False


def test_answer_without_actual_search_or_citations_is_rejected():
    with pytest.raises(ValueError):
        research.parse_research_response({"outputs": [{"type": "message.output", "content": "30 Tage"}]}, "mistral")
    assert research._source({"url": "javascript:alert(1)"}) is None


def test_unauthenticated_search_is_not_allowed(client):
    assert client.post("/ai/notice-research", json={"query": "Magenta L", "confirmed_public": True}).status_code == 401


@pytest.mark.parametrize(("upstream_status", "expected_detail"), [
    (400, "Suchmodell und Websuche-Konfiguration"),
    (401, "API-Schlüssel abgelehnt"),
    (402, "Guthaben"),
    (403, "Berechtigungen"),
    (404, "Suchmodell oder den Recherche-Endpunkt"),
    (422, "Suchmodell und Websuche-Konfiguration"),
    (429, "Anfrage- oder Kontingentlimit"),
    (503, "Später erneut versuchen"),
])
def test_provider_errors_explain_failure_without_exposing_payload(auth_client, monkeypatch, upstream_status, expected_detail):
    monkeypatch.setenv("NOTICE_RESEARCH_PROVIDER", "mistral")
    monkeypatch.setenv("NOTICE_RESEARCH_API_KEY", "search-only-key")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(upstream_status, json={"message": "private-upstream-detail search-only-key"})

    original = httpx.AsyncClient
    monkeypatch.setattr(research.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    response = auth_client.post("/ai/notice-research", json={"query": "Magenta L", "confirmed_public": True})
    assert response.status_code == 502
    assert len(requests) == 1  # No automatic retries with additional API costs.
    detail = response.json()["detail"]
    assert "Mistral" in detail
    assert expected_detail in detail
    assert f"HTTP {upstream_status}" in detail
    assert "Die Kündigungsfrist bleibt unverändert" in detail
    assert not any(value in detail for value in ("private-upstream-detail", "search-only-key", "Magenta L"))


@pytest.mark.parametrize(("failure", "expected_status", "expected_detail"), [
    ("timeout", 504, "120 Sekunden"),
    ("connection", 502, "nicht erreicht"),
    ("no_sources", 502, "keine durch Websuche belegte Antwort"),
    ("invalid_json", 502, "Antwortformat war ungültig"),
    ("invalid_shape", 502, "Antwortformat war ungültig"),
])
def test_research_failures_have_distinct_messages(auth_client, monkeypatch, failure, expected_status, expected_detail):
    monkeypatch.setenv("NOTICE_RESEARCH_PROVIDER", "mistral")
    monkeypatch.setenv("NOTICE_RESEARCH_API_KEY", "search-only-key")

    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private-upstream-detail", request=request)
        if failure == "connection":
            raise httpx.ConnectError("private-upstream-detail", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="private-upstream-detail")
        if failure == "invalid_shape":
            return httpx.Response(200, json={"outputs": [None]})
        return httpx.Response(200, json={"outputs": [{"type": "message.output", "content": "30 Tage"}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(research.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    response = auth_client.post("/ai/notice-research", json={"query": "Magenta L", "confirmed_public": True})
    assert response.status_code == expected_status
    assert expected_detail in response.json()["detail"]
    assert "private-upstream-detail" not in response.text
