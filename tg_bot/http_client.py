# Tg_bot/http_client.py
# Unified HTTP Client — Single Entry Point For All Outgoing HTTP Requests
# Uses Requestmiddleware For Proxy Management, Retry, And Logging

import logging
from typing import Any, Optional

import httpx

from services.proxy_adapter import ProxyAdapter, RequestMiddleware, get_proxy_adapter

logger = logging.getLogger(__name__)

# Global Singleton (initialized In Main.py)
_http_client: Optional[RequestMiddleware] = None


def init_http_client(adapter: ProxyAdapter, timeout: float = 20.0) -> RequestMiddleware:
    """Initialize global HTTP client in main.py."""
    global _http_client
    _http_client = RequestMiddleware(adapter, timeout)
    logger.info("HTTP Client Initialized With Requestmiddleware")
    return _http_client


def get_http_client() -> RequestMiddleware:
    """Get initialized HTTP client or create default."""
    global _http_client
    if _http_client is None:
        adapter = get_proxy_adapter("default")
        _http_client = RequestMiddleware(adapter)
    return _http_client


async def http_get(url: str, **kwargs: Any) -> httpx.Response:
    """Convenience GET method."""
    client = get_http_client()
    return await client.get(url, **kwargs)


async def http_post(url: str, **kwargs: Any) -> httpx.Response:
    """Convenience POST method."""
    client = get_http_client()
    return await client.post(url, {}, **kwargs)


# Re-export Requestmiddleware For Type Hints
__all__ = [
    'init_http_client',
    'get_http_client',
    'http_get',
    'http_post',
    'RequestMiddleware',
]
