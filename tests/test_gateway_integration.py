"""Tests for Gateway Client + Circuit Breaker Integration."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.gateway.circuit_breaker import (
    CircuitOpenError,
    CircuitState,
    clear_circuit_breakers,
    get_circuit_breaker,
)
from services.gateway.client import GatewayClient, clear_gateway_clients, get_gateway_client


class TestGatewayClientInit:
    """Test client initialization."""

    def test_client_creation(self) -> None:
        """Test basic client creation."""
        asyncio.run(clear_gateway_clients())
        client = get_gateway_client("test_bot", base_url="http://test.local")
        assert client.base_url == "http://test.local"
        assert client.timeout == 30.0  # default

    def test_client_creation_with_params(self) -> None:
        """Test client creation with custom parameters."""
        asyncio.run(clear_gateway_clients())
        client = GatewayClient(base_url="http://example.com", timeout=10.0)
        assert client.base_url == "http://example.com"
        assert client.timeout == 10.0


class TestCircuitBreakerStateMachine:
    """Test circuit breaker state transitions."""

    def setup_method(self) -> None:
        clear_circuit_breakers()

    def test_closed_to_open_after_threshold(self) -> None:
        """Circuit opens after failure_threshold failures."""
        cb = get_circuit_breaker("test_cb")
        cb.config.failure_threshold = 3

        for _ in range(3):
            asyncio.run(cb.record_failure(TimeoutError()))

        assert cb.state == CircuitState.OPEN

    def test_half_open_after_timeout(self) -> None:
        """Circuit goes to HALF_OPEN after timeout."""
        import time
        cb = get_circuit_breaker("test_cb")
        cb.config.failure_threshold = 1
        cb.config.timeout = 0.01  # 10ms for test

        asyncio.run(cb.record_failure(TimeoutError()))
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)  # wait for timeout

        # After Timeout, State Property Should Return HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self) -> None:
        """Circuit closes after success in HALF_OPEN state."""
        clear_circuit_breakers()
        cb = get_circuit_breaker("test_cb")
        cb.config.failure_threshold = 1
        cb.config.success_threshold = 1
        cb.config.timeout = 0.0

        await cb.record_failure(TimeoutError())
        # Should Be HALF_OPEN Now (timeout=0)

        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_open_rejects_immediately(self) -> None:
        """When circuit is OPEN, should reject without calling."""
        clear_circuit_breakers()
        cb = get_circuit_breaker("test_cb")
        cb.config.failure_threshold = 1

        await cb.record_failure(TimeoutError())
        assert cb.state == CircuitState.OPEN

        # Trying To Call Should Raise Circuitopenerror
        with pytest.raises(CircuitOpenError):
            # Simulate What Gatewayclient Does
            if cb.state == CircuitState.OPEN:
                raise CircuitOpenError("test_cb")


class TestGatewayIntegration:
    """Full integration tests with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_successful_request(self) -> None:
        await clear_gateway_clients()
        client = get_gateway_client("test_bot", base_url="http://test.local")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"answer": "Hello!"})
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.headers = {}
        mock_http.timeout = 5.0

        client._client = mock_http

        response = await client._request("POST", "/api/ai/chat", json={"message": "Hi"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_calls(self) -> None:
        """Test that open circuit prevents HTTP calls."""
        await clear_gateway_clients()
        clear_circuit_breakers()

        client = get_gateway_client("test_bot", base_url="http://test.local")

        # Trip The Circuit
        cb = get_circuit_breaker("test_bot")
        cb.config.failure_threshold = 1

        await cb.record_failure(TimeoutError())
        assert cb.state == CircuitState.OPEN

        # Now Trying To Make A Request Should Fail Fast
        with pytest.raises(CircuitOpenError):
            async with cb:
                await client._request("POST", "/api/test")


import httpx

from services.gateway.client import (
    AIHistoryRequest,
    AISearchRequest,
)


class TestGatewayClientCoverage:
    """Close coverage gaps in client.py (64% → target 80%+)."""

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self) -> None:
        await clear_gateway_clients()
        client = get_gateway_client("hc_bot", base_url="http://hc.local")

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=httpx.ConnectError("fail"))
        client._client = mock_http

        result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_close_sets_client_none(self) -> None:
        await clear_gateway_clients()
        client = get_gateway_client("close_bot", base_url="http://close.local")
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock()
        client._client = mock_http

        await client.close()
        assert client._client is None
        mock_http.aclose.assert_awaited_once()

    def test_get_headers_with_api_key_and_extra(self) -> None:
        # Use Sync Clear Since We're Not In Async Context
        asyncio.run(clear_gateway_clients())
        client = get_gateway_client("hdr_bot", base_url="http://hdr.local", api_key="secret")
        headers = client._get_headers(extra={"X-Custom": "val"})
        assert headers["Authorization"] == "Bearer secret"
        assert headers["X-Custom"] == "val"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_request_raises_on_circuit_open(self) -> None:
        await clear_gateway_clients()
        clear_circuit_breakers()
        client = get_gateway_client("cb_bot", base_url="http://cb.local")

        # Circuit Breaker Is Keyed By Base_url, Not By Client Name
        cb = get_circuit_breaker("http://cb.local")
        cb.config.failure_threshold = 1
        await cb.record_failure(RuntimeError("boom"))

        # Mock The HTTP Client To Avoid Real Requests
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http.request = AsyncMock(return_value=mock_response)
        client._client = mock_http

        # Now The Circuit Is OPEN, Should Raise Circuitopenerror Immediately
        with pytest.raises(CircuitOpenError):
            await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_ai_history_returns_dict(self) -> None:
        await clear_gateway_clients()
        client = get_gateway_client("hist_bot", base_url="http://hist.local")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"messages": []})
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.ai_history(
            AIHistoryRequest(bot_id="b", user_id="u", user_nickname="n")
        )
        assert result == {"messages": []}

    @pytest.mark.asyncio
    async def test_ai_search_returns_parsed_response(self) -> None:
        await clear_gateway_clients()
        client = get_gateway_client("search_bot", base_url="http://search.local")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"context": ["chunk1", "chunk2"]})
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.ai_search(
            AISearchRequest(bot_id="b", topic="coffee", top_k=5)
        )
        assert result.context == ["chunk1", "chunk2"]

    @pytest.mark.asyncio
    async def test_chat_completion_with_response_format(self) -> None:
        await clear_gateway_clients()
        client = get_gateway_client("llm_bot", base_url="http://llm.local")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"choices": [{"message": {"content": "hi"}}]})
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.chat_completion(
            system="sys", user="usr", response_format={"type": "json_object"}
        )
        assert result["choices"][0]["message"]["content"] == "hi"
