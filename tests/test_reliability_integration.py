"""Tests for Phase 3.1 Part 1/2: Federation HMAC + Alerting + Circuit Breaker."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gateway.client import GatewayClient
from tg_bot.bot_services.ai_communication_service import AICommunicationService
from tg_bot.infrastructure.hmac_signing import sign_payload, verify_signature
from tg_bot.llm_client import LLMStructuredClient


class _AsyncCtxManager:
    """Helper to make a value work as async context manager."""
    def __init__(self, value: Any) -> None:
        self.value = value
    async def __aenter__(self) -> Any:
        return self.value
    async def __aexit__(self, *args: Any) -> Any:
        pass


class TestHMACIntegration:
    """Federation HMAC header in GatewayClient._get_headers."""

    def test_federation_secret_in_init(self) -> None:
        """federation_secret param sets self.federation_secret."""
        client = GatewayClient("http://test.local", federation_secret="test-secret")
        assert client.federation_secret == "test-secret"

    def test_hmac_header_present_with_payload(self) -> None:
        """_get_headers includes X-Federation-Signature when payload is given."""
        client = GatewayClient("http://test.local", federation_secret="test-secret")
        headers = client._get_headers(payload=b'{"key":"value"}')
        assert "X-Federation-Signature" in headers
        assert len(headers["X-Federation-Signature"]) == 64  # SHA-256 hex digest

    def test_hmac_header_absent_without_secret(self) -> None:
        """_get_headers omits X-Federation-Signature when federation_secret is None."""
        client = GatewayClient("http://test.local", federation_secret=None)
        headers = client._get_headers(payload=b'{}')
        assert "X-Federation-Signature" not in headers

    def test_hmac_header_absent_without_payload(self) -> None:
        """_get_headers omits X-Federation-Signature when payload is None."""
        client = GatewayClient("http://test.local", federation_secret="test-secret")
        headers = client._get_headers(payload=None)
        assert "X-Federation-Signature" not in headers

    def test_hmac_signature_verification(self) -> None:
        """sign_payload creates a valid verify_signature."""
        secret = "my-federation-secret"
        payload = b'{"bot_id": "test", "user_id": "123"}'
        sig = sign_payload(secret, payload)
        assert verify_signature(secret, payload, sig) is True
        assert verify_signature(secret, b'tampered', sig) is False
        assert verify_signature("wrong-secret", payload, sig) is False


class TestGatewayClientCB:
    """GatewayClient circuit breaker integration in _request."""

    @patch("services.gateway.client.GatewayClient._get_client")
    def test_request_passes_hmac_on_post(self, mock_get_client: Any) -> None:
        """_request includes HMAC header on POST with json body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        client = GatewayClient("http://test.local", federation_secret="test-secret")

        async def run() -> Any:
            return await client._request("POST", "/test", json={"hello": "world"})

        asyncio.run(run())

        call_kwargs = mock_client.request.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "X-Federation-Signature" in headers
        assert "X-Request-ID" in headers


class TestLLMClientGatewayPath:
    """LLMStructuredClient uses GatewayClient as primary path."""

    def test_gateway_path_on_success(self) -> None:
        """GatewayClient path returns before middleware fallback."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}]
        }

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        client = LLMStructuredClient(
            base_url="http://test.local",
            gateway_client=mock_gateway,
        )

        async def run() -> Any:
            return await client.chat(
                system_prompt="Be helpful",
                user_input="Hi",
            )

        result = asyncio.run(run())
        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        mock_gateway._request.assert_awaited_once()

    def test_fallback_on_circuit_open(self) -> None:
        """CircuitOpenError triggers fallback to middleware."""
        from services.gateway.circuit_breaker import CircuitOpenError

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(side_effect=CircuitOpenError("test"))

        mock_middleware_response = MagicMock()
        mock_middleware_response.json.return_value = {
            "choices": [{"message": {"content": "Fallback response"}, "finish_reason": "stop"}]
        }
        mock_middleware_client = MagicMock()
        mock_middleware_client.post = AsyncMock(return_value=mock_middleware_response)
        mock_middleware = MagicMock()
        mock_middleware.client.return_value = _AsyncCtxManager(mock_middleware_client)

        client = LLMStructuredClient(
            base_url="http://test.local",
            gateway_client=mock_gateway,
            http_middleware=mock_middleware,
        )

        async def run() -> Any:
            return await client.chat(
                system_prompt="Be helpful",
                user_input="Hi",
            )

        result = asyncio.run(run())
        assert result.content == "Fallback response"
        mock_middleware_client.post.assert_awaited_once()

    def test_fallback_on_generic_error(self) -> None:
        """Generic GatewayClient error triggers fallback to middleware."""
        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(side_effect=ConnectionError("connection lost"))

        mock_middleware_response = MagicMock()
        mock_middleware_response.json.return_value = {
            "choices": [{"message": {"content": "Fallback after error"}, "finish_reason": "stop"}]
        }
        mock_middleware_client = MagicMock()
        mock_middleware_client.post = AsyncMock(return_value=mock_middleware_response)
        mock_middleware = MagicMock()
        mock_middleware.client.return_value = _AsyncCtxManager(mock_middleware_client)

        client = LLMStructuredClient(
            base_url="http://test.local",
            gateway_client=mock_gateway,
            http_middleware=mock_middleware,
        )

        async def run() -> Any:
            return await client.chat(
                system_prompt="Be helpful",
                user_input="Hi",
            )

        result = asyncio.run(run())
        assert result.content == "Fallback after error"

    def test_no_gateway_uses_middleware(self) -> None:
        """Without gateway_client, falls through to middleware."""
        mock_middleware_response = MagicMock()
        mock_middleware_response.json.return_value = {
            "choices": [{"message": {"content": "Direct middleware"}, "finish_reason": "stop"}]
        }
        mock_middleware_client = MagicMock()
        mock_middleware_client.post = AsyncMock(return_value=mock_middleware_response)
        mock_middleware = MagicMock()
        mock_middleware.client.return_value = _AsyncCtxManager(mock_middleware_client)

        client = LLMStructuredClient(
            base_url="http://test.local",
            gateway_client=None,
            http_middleware=mock_middleware,
        )

        async def run() -> Any:
            return await client.chat(
                system_prompt="Be helpful",
                user_input="Hi",
            )

        result = asyncio.run(run())
        assert result.content == "Direct middleware"

    def test_no_gateway_no_middleware_raises(self) -> None:
        """Without both gateway_client and middleware, raises RuntimeError."""
        client = LLMStructuredClient(
            base_url="http://test.local",
            gateway_client=None,
            http_middleware=None,
        )

        async def run() -> Any:
            return await client.chat(
                system_prompt="Be helpful",
                user_input="Hi",
            )

        with pytest.raises(RuntimeError, match="HTTP middleware is required"):
            asyncio.run(run())


class TestAICommunicationServiceGatewayPath:
    """AICommunicationService uses GatewayClient in all 5 methods."""

    def test_fallback_to_quart_gateway_path(self) -> None:
        """_fallback_to_quart uses GatewayClient as primary path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"answer": "Quart answer", "status": "ok"}

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )

        async def run() -> Any:
            return await service._fallback_to_quart(
                user_id=123, topic="Hello", nickname="User"
            )

        result = asyncio.run(run())
        assert result["answer"] == "Quart answer"
        mock_gateway._request.assert_awaited_once_with(
            "POST", "", json={
                "bot_id": "test_bot",
                "user_id": "123",
                "topic": "Hello",
                "user_nickname": "User",
            }
        )

    def test_fallback_to_quart_indexing_status(self) -> None:
        """202 status is returned early as indexing status."""
        mock_response = MagicMock()
        mock_response.status_code = 202

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )

        async def run() -> Any:
            return await service._fallback_to_quart(
                user_id=123, topic="data", nickname="User"
            )

        result = asyncio.run(run())
        assert result["status"] == "indexing"

    def test_fallback_to_quart_circuit_open_fallback(self) -> None:
        """CircuitOpenError falls back to http_middleware."""
        from services.gateway.circuit_breaker import CircuitOpenError

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(side_effect=CircuitOpenError("test"))

        mock_middleware_response = MagicMock()
        mock_middleware_response.status_code = 200
        mock_middleware_response.json.return_value = {"answer": "Middleware answer"}
        mock_middleware = MagicMock()
        mock_middleware.post = AsyncMock(return_value=mock_middleware_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )
        service._http_middleware = mock_middleware

        async def run() -> Any:
            return await service._fallback_to_quart(
                user_id=123, topic="Hello", nickname="User"
            )

        result = asyncio.run(run())
        assert result["answer"] == "Middleware answer"
        mock_middleware.post.assert_awaited_once()

    def test_semantic_retrieval_gateway_path(self) -> None:
        """get_semantic_retrieval uses GatewayClient as primary path."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "context": ["### Товар: Эспрессо ###", "### Товар: Латте ###"]
        }

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )

        async def run() -> Any:
            return await service.get_semantic_retrieval(query="coffee")

        result = asyncio.run(run())
        assert "Эспрессо" in result
        assert "Латте" in result
        mock_gateway._request.assert_awaited_once_with(
            "POST", "/semantic", json={"query": "coffee"}
        )

    def test_chat_history_paged_gateway_path(self) -> None:
        """get_chat_history_paged remote path uses GatewayClient."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messages": [
                {"role": "human", "content": "Hi", "created_at": "2024-01-01T12:00:00Z"}
            ]
        }

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )

        with patch("tg_bot.infrastructure.secrets_loader.SecretsLoader.get_required") as mock_get:
            mock_get.return_value = "shared-secret"
            async def run() -> Any:
                return await service.get_chat_history_paged(user_id=123, nickname="User")

            result = asyncio.run(run())
        assert result["status"] == "success"
        mock_gateway._request.assert_awaited_once()

    def test_brewing_request_gateway_path(self) -> None:
        """_execute_brewing_request uses GatewayClient as primary path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"answer": "Brewing guide"}

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )

        async def run() -> Any:
            return await service._execute_brewing_request(
                prompt="How to brew?", log_label="coffee"
            )

        result = asyncio.run(run())
        assert "Brewing guide" in result
        mock_gateway._request.assert_awaited_once()

    def test_gift_greetings_gateway_path(self) -> None:
        """get_ai_gift_greetings uses GatewayClient as primary path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "<v1>Option 1</v1><v2>Option 2</v2><v3>Option 3</v3>"
        }

        mock_gateway = MagicMock()
        mock_gateway._request = AsyncMock(return_value=mock_response)

        service = AICommunicationService(
            quart_url="http://quart:5000",
            bot_id="test_bot",
            gateway=mock_gateway,
        )

        async def run() -> Any:
            return await service.get_ai_gift_greetings(prompt_data="birthday")

        result = asyncio.run(run())
        assert len(result) == 3
        mock_gateway._request.assert_awaited_once()


class TestAlertingIntegration:
    """Alerting setup attaches Telegram handler to root logger."""

    def test_setup_alerting_adds_handler(self) -> None:
        """setup_alerting adds TelegramAlertHandler to root logger."""
        import logging

        from tg_bot.infrastructure.alerting import setup_alerting

        root = logging.getLogger()
        original_handlers = list(root.handlers)

        app = MagicMock()
        app.bot_data = {}

        with patch("tg_bot.infrastructure.secrets_loader.get_secret") as mock_get:
            mock_get.side_effect = lambda key, default=None: {
                "BOT_TOKEN": "test-token",
                "ADMIN_CHAT_ID": "-1001234567890",
            }.get(key, default)
            setup_alerting(app)

        new_handlers = root.handlers
        added = [h for h in new_handlers if h not in original_handlers]
        assert len(added) >= 1

        handler = added[0]
        from tg_bot.infrastructure.alerting import TelegramAlertHandler
        assert isinstance(handler, TelegramAlertHandler)
        assert handler.level == logging.ERROR

        # Cleanup
        for h in added:
            root.removeHandler(h)

    def test_alert_handler_format(self) -> None:
        """TelegramAlertHandler formats record as HTML message."""
        import logging

        from tg_bot.infrastructure.alerting import TelegramAlertHandler

        handler = TelegramAlertHandler("token", "-100chat")
        record = logging.LogRecord(
            name="test.module",
            level=logging.ERROR,
            pathname="/test.py",
            lineno=42,
            msg="Something went wrong",
            args=(),
            exc_info=None,
        )
        msg = handler._format_alert(record)
        assert "⚠️" in msg  # ERROR level uses ⚠️
        assert "ERROR" in msg
        assert "test.module" in msg
        assert "Something went wrong" in msg
        assert "Module: test:42" in msg


