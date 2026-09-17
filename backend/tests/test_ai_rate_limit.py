"""Exercise bounded retries through the real SDK with synthetic HTTP responses."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from test_ai_reasoning import completion_response

import ai_client
from ai_mistral_transport import create_mistral_http_client


async def test_sdk_429_retries_after_provider_delay_and_reports_wait(monkeypatch):
    requests, waits = [], []
    sleep = AsyncMock()
    monkeypatch.setattr(ai_client.asyncio, "sleep", sleep)

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "12"}, json={"message": "limited"})
        return completion_response("done", "zai-glm-5-3")

    token = ai_client.rate_limit_observer.set(lambda attempt, delay: waits.append((attempt, delay)))
    try:
        async with create_mistral_http_client(transport=httpx.MockTransport(handle)) as http:
            client = ai_client.Mistral(api_key="synthetic", async_client=http)
            result = await ai_client.retry_on_rate_limit(
                client.chat.complete_async, model="zai-glm-5-3", messages=[{"role": "user", "content": "test"}],
            )
    finally:
        ai_client.rate_limit_observer.reset(token)
    assert len(requests) == 2 and result.choices[0].message.content == "done"
    sleep.assert_awaited_once_with(12)
    assert waits == [(2, 12), (2, 0)]


async def test_rate_limit_is_bounded_and_uses_exponential_backoff(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(ai_client.asyncio, "sleep", sleep)
    error = ai_client.SDKError("limited", httpx.Response(429))
    request = AsyncMock(side_effect=error)
    with pytest.raises(ai_client.SDKError):
        await ai_client.retry_on_rate_limit(request)
    assert request.await_count == 5
    assert [call.args[0] for call in sleep.await_args_list] == [5, 10, 20, 40]


@pytest.mark.parametrize("status", [400, 401, 404, 500, 504])
async def test_non_rate_limit_failure_does_not_trigger_another_analysis(status):
    request = AsyncMock(side_effect=ai_client.SDKError("failure", httpx.Response(status)))
    with pytest.raises(ai_client.SDKError):
        await ai_client.retry_on_rate_limit(request)
    request.assert_awaited_once()


async def test_request_deadline_includes_rate_limit_wait():
    request = AsyncMock(side_effect=ai_client.SDKError("limited", httpx.Response(429, headers={"Retry-After": "900"})))
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(ai_client.retry_on_rate_limit(request), timeout=0.01)
    request.assert_awaited_once()


def test_retry_after_http_date_is_respected():
    date = format_datetime(datetime.now(UTC) + timedelta(seconds=60))
    error = ai_client.SDKError("limited", httpx.Response(429, headers={"Retry-After": date}))
    assert 58 <= ai_client._retry_after(error) <= 60
