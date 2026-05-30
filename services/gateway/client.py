# Services/gateway/client.py
"""
Gateway Client for External Service Integration.

Provides typed interface to external APIs (Quart, LLM, etc.)
with circuit breaker, retry logic, and structured logging.
"""
import asyncio
import json as stdjson
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from services.gateway.circuit_breaker import (
    CircuitOpenError,
    get_circuit_breaker,
)
from services.gateway.retry_policy import RetryConfig, RetryPolicy
from tg_bot.infrastructure.correlation import get_correlation_id
from tg_bot.infrastructure.hmac_signing import HMACNonceManager, sign_payload
from tg_bot.infrastructure.metrics import kojo_llm_latency_seconds, observe_latency

logger = logging.getLogger(__name__)


@dataclass
class AIChatRequest:
    """Request to AI chat service."""
    bot_id: str
    user_id: str
    topic: str
    user_nickname: str
    is_direct: bool = False


@dataclass
class AIChatResponse:
    """Response from AI chat service."""
    answer: str
    status: Optional[str] = None


@dataclass
class AIHistoryRequest:
    """Request to AI history service."""
    bot_id: str
    user_id: str
    user_nickname: str


@dataclass
class AISearchRequest:
    """Request to AI semantic search."""
    bot_id: str
    topic: str
    top_k: int = 10


@dataclass
class AISearchResponse:
    """Response from AI semantic search."""
    context: list[str]


class GatewayClient:
    """
    Typed client for external API calls.

    Features:
    - Circuit breaker per service
    - Retry with exponential backoff
    - Structured request/response logging
    - Timeout handling
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        api_key: Optional[str] = None,
        federation_secret: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.api_key = api_key
        self.federation_secret = federation_secret

        if self.federation_secret is None:
            from tg_bot.infrastructure.secrets_loader import get_secret
            self.federation_secret = get_secret("FEDERATION_SECRET")

        # Create Circuit Breaker For This Service
        self._circuit = get_circuit_breaker(self.base_url)

        # Retry Config
        self._retry_policy = RetryPolicy(RetryConfig(
            max_attempts=3,
            base_delay=1.0,
        ))

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(
        self,
        extra: Optional[dict[str, str]] = None,
        payload: Optional[bytes] = None,
    ) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": get_correlation_id(),
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.federation_secret and payload:
            headers["X-Federation-Signature"] = sign_payload(self.federation_secret, payload)
            headers["X-Federation-Timestamp"] = str(HMACNonceManager.generate_timestamp())
            headers["X-Federation-Nonce"] = HMACNonceManager.generate_nonce()
        if extra:
            headers.update(extra)
        return headers

    @observe_latency(kojo_llm_latency_seconds)
    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, object]] = None,
        params: Optional[dict[str, str]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Make HTTP request with circuit breaker and retry."""
        url = f"{self.base_url}{path}"
        cid = get_correlation_id()
        logger.debug("Gateway request: %s %s (correlation_id=%s)", method, url, cid)

        # Pre-serialize JSON For HMAC Signing
        content: Optional[bytes] = None
        if json is not None:
            content = stdjson.dumps(json, separators=(",", ":")).encode("utf-8")

        async def do_request() -> httpx.Response:
            client = await self._get_client()
            return await client.request(
                method=method,
                url=url,
                content=content,
                params=params,
                headers=self._get_headers(headers, content),
            )

        # Try With Circuit Breaker And Retry
        try:
            async with self._circuit:
                response = await self._retry_policy.execute(do_request)
                response.raise_for_status()
                logger.debug(
                    "Gateway response: %s %s (status=%s, correlation_id=%s)",
                    method, url, response.status_code, cid,
                )
                return response
        except CircuitOpenError:
            logger.warning("Circuit open for %s, correlation_id=%s", url, cid)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error %s for %s (correlation_id=%s)", e.response.status_code, url, cid)
            raise
        except httpx.RequestError as e:
            logger.error("Request error for %s: %s (correlation_id=%s)", url, e, cid)
            raise

        # This Should Never Be Reached, But Mypy Requires A Return
        raise RuntimeError("Unreachable code reached in _request")

    # === AI Service Methods ===

    async def chat_completion(
        self,
        system: str,
        user: str,
        response_format: Optional[dict[str, object]] = None,
    ) -> dict[str, object]:
        """
        Send chat completion request to LLM service.

        OpenAPI spec would define:
        POST /llm/chat
        """
        from typing import cast

        payload: dict[str, object] = {"system": system, "user": user}
        if response_format:
            payload["response_format"] = response_format

        response = await self._request("POST", "/llm/chat", json=payload)
        return cast(dict[str, object], response.json())

    async def ai_chat(self, request: AIChatRequest) -> AIChatResponse:
        """
        Send message to AI chat endpoint.

        OpenAPI spec would define:
        POST /api/ai/chat
        """
        from typing import cast

        response = await self._request(
            "POST",
            "/api/ai/chat",
            json={
                "bot_id": request.bot_id,
                "user_id": request.user_id,
                "topic": request.topic,
                "user_nickname": request.user_nickname,
                "is_direct": request.is_direct,
            }
        )
        data = cast(dict[str, object], response.json())
        return AIChatResponse(
            answer=cast(str, data.get("answer", "")),
            status=cast(Optional[str], data.get("status")),
        )

    async def ai_history(self, request: AIHistoryRequest) -> dict[str, object]:
        """
        Get AI chat history.

        OpenAPI spec would define:
        POST /api/ai/history
        """
        from typing import cast

        response = await self._request(
            "POST",
            "/api/ai/history",
            json={
                "bot_id": request.bot_id,
                "user_id": request.user_id,
                "user_nickname": request.user_nickname,
            }
        )
        return cast(dict[str, object], response.json())

    async def ai_search(self, request: AISearchRequest) -> AISearchResponse:
        """
        Semantic search via AI service.

        OpenAPI spec would define:
        POST /api/ai/search
        """
        from typing import cast

        response = await self._request(
            "POST",
            "/api/ai/search",
            json={
                "bot_id": request.bot_id,
                "topic": request.topic,
                "top_k": request.top_k,
            }
        )
        data = cast(dict[str, object], response.json())
        return AISearchResponse(context=cast(list[str], data.get("context", [])))

    async def health_check(self) -> bool:
        """Check if the gateway service is healthy."""
        try:
            response = await self._request("GET", "/health")
            return response.status_code == 200
        except (RuntimeError, ConnectionError, TimeoutError, OSError, httpx.RequestError):
            return False


# Global Client Registry With TTL
_clients: dict[str, GatewayClient] = {}
_client_timestamps: dict[str, datetime] = {}
_CLIENT_TTL_SECONDS = 3600  # 1 hour


def _cleanup_stale_clients() -> None:
    """Remove clients not accessed for >1 hour."""
    now = datetime.now(timezone.utc)
    stale = [
        name for name, ts in _client_timestamps.items()
        if (now - ts).total_seconds() > _CLIENT_TTL_SECONDS
    ]
    for name in stale:
        client = _clients.pop(name, None)
        _client_timestamps.pop(name, None)
        if client:
            # Fire-and-forget Close Is Acceptable For Cleanup
            asyncio.create_task(client.close())
        logger.info(f"🧹 [GatewayClient] Cleaned up stale client: {name}")


def get_gateway_client(
    name: str = "default",
    base_url: Optional[str] = None,
    timeout: float = 30.0,
    api_key: Optional[str] = None,
    federation_secret: Optional[str] = None,
) -> GatewayClient:
    """
    Get or create a gateway client.
    Usage:
        client = get_gateway_client("quart", base_url="http://localhost:5000")
        response = await client.ai_chat(request)
    """
    _cleanup_stale_clients()

    if name not in _clients:
        from tg_bot.infrastructure.secrets_loader import get_secret
        url = base_url or get_secret(f"{name.upper()}_SERVER_URL", "")
        if not url:
            raise ValueError(f"No URL provided for gateway client: {name}")

        key = api_key or get_secret(f"{name.upper()}_API_KEY")

        _clients[name] = GatewayClient(
            base_url=url,
            timeout=timeout,
            api_key=key,
            federation_secret=federation_secret,
        )

    _client_timestamps[name] = datetime.now(timezone.utc)
    return _clients[name]


async def clear_gateway_clients() -> None:
    """Clear all gateway clients (for testing)."""
    tasks = [client.close() for client in _clients.values()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _clients.clear()


__all__ = [
    'GatewayClient',
    'get_gateway_client',
    'AIChatRequest',
    'AIChatResponse',
    'AIHistoryRequest',
    'AISearchRequest',
    'AISearchResponse',
    'clear_gateway_clients',
]
