# Tests For Proxy_adapter.py
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.proxy_adapter import ProxyAdapter, RequestMiddleware, get_proxy_adapter, get_request_middleware


class TestProxyAdapter:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        pool.get_all_proxies = MagicMock(return_value=[
            MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
        ])
        pool.failed_proxies = set()
        pool.get_working_proxy = AsyncMock(return_value=MagicMock(url='socks5://proxy1:1080', full_name='Proxy1'))
        return pool

    @pytest.mark.asyncio
    async def test_async_set_proxy_sets_current(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            proxy = await adapter.async_set_proxy()
            assert proxy is not None
            assert adapter.current_proxy == proxy
            assert proxy.url == 'socks5://proxy1:1080'

    @pytest.mark.asyncio
    async def test_no_environ_mutation(self, mock_pool) -> Any:
        """os.environ should not be mutated after async_set_proxy."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            with patch.dict(os.environ, {"EXISTING_VAR": "value"}, clear=False):
                adapter = ProxyAdapter(bot_id="test_bot")
                await adapter.async_set_proxy()
                assert "HTTPS_PROXY" not in os.environ
                assert "HTTP_PROXY" not in os.environ
                assert "ALL_PROXY" not in os.environ

    @pytest.mark.asyncio
    async def test_async_set_proxy_clears_on_failure(self, mock_pool) -> Any:
        mock_pool.get_working_proxy = AsyncMock(return_value=None)
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock()
            proxy = await adapter.async_set_proxy()
            assert proxy is None
            assert adapter.current_proxy is None

    def test_get_proxy_for_httpx_returns_proxy_object(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            result = adapter.get_proxy_for_httpx()
            assert result is not None
            assert result.url == 'socks5://proxy1:1080'

    def test_get_proxy_for_httpx_returns_none_when_no_proxy(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = None
            result = adapter.get_proxy_for_httpx()
            assert result is None

    @pytest.mark.asyncio
    async def test_mark_success_resets_retries(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter._retries = 2
            adapter.current_proxy = MagicMock()
            mock_pool.mark_success = AsyncMock()
            await adapter.mark_success()
            assert adapter._retries == 0
            mock_pool.mark_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_failure_switches_proxy(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            adapter._retries = 0
            mock_pool.mark_failed = AsyncMock()
            mock_pool.get_next_proxy = AsyncMock(return_value=MagicMock(url='socks5://proxy2:1080', full_name='Proxy2'))
            result = await adapter.handle_failure()
            assert result is True
            assert adapter.current_proxy.url == 'socks5://proxy2:1080'
            assert adapter._retries == 1

    @pytest.mark.asyncio
    async def test_handle_failure_exhausted_retries(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock()
            adapter._retries = 3
            mock_pool.mark_failed = AsyncMock()
            result = await adapter.handle_failure()
            assert result is False

    def test_get_proxy_adapter_same_instance(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter1 = get_proxy_adapter("test_bot")
            adapter2 = get_proxy_adapter("test_bot")
            assert adapter1 is adapter2

    def test_get_proxy_adapter_different_bots(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter1 = get_proxy_adapter("bot1")
            adapter2 = get_proxy_adapter("bot2")
            assert adapter1 is not adapter2

    def test_get_status(self, mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(full_name='Test Proxy')
            status = adapter.get_status()
            assert status['bot_id'] == 'test_bot'
            assert status['current_proxy'] == 'Test Proxy'


class TestRequestMiddleware:
    @pytest.fixture
    def mw_mock_pool(self) -> Any:
        pool = MagicMock()
        pool.get_all_proxies = MagicMock(return_value=[
            MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
        ])
        pool.failed_proxies = set()
        pool.get_working_proxy = AsyncMock(return_value=MagicMock(url='socks5://proxy1:1080', full_name='Proxy1'))
        return pool

    @pytest.fixture
    def mw_mock_adapter(self, mw_mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mw_mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            return adapter

    @pytest.mark.asyncio
    async def test_middleware_client_injects_proxy(self, mw_mock_adapter) -> Any:
        mw_mock_adapter.get_proxy_for_httpx = MagicMock(return_value=MagicMock(url='socks5://proxy1:1080'))
        middleware = RequestMiddleware(mw_mock_adapter)
        with patch('httpx.AsyncClient') as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = instance
            MockClient.return_value.__aexit__.return_value = AsyncMock()
            async with middleware.client() as client:
                assert client is not None

    @pytest.mark.asyncio
    async def test_middleware_post_success(self, mw_mock_adapter) -> Any:
        mw_mock_adapter.async_set_proxy = AsyncMock(return_value=mw_mock_adapter.current_proxy)
        mw_mock_adapter.get_proxy_for_httpx = MagicMock(return_value=MagicMock(url='socks5://proxy1:1080'))
        mw_mock_adapter.mark_success = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        middleware = RequestMiddleware(mw_mock_adapter)
        with patch('httpx.AsyncClient') as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = instance

            response = await middleware.post("http://test/api", {"key": "value"})

            assert response.status_code == 200
            mw_mock_adapter.mark_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_middleware_post_retries_on_5xx(self, mw_mock_adapter) -> Any:
        mw_mock_adapter.async_set_proxy = AsyncMock(return_value=mw_mock_adapter.current_proxy)
        mw_mock_adapter.get_proxy_for_httpx = MagicMock(return_value=MagicMock(url='socks5://proxy1:1080'))
        mw_mock_adapter.handle_failure = AsyncMock(return_value=True)
        mw_mock_adapter.mark_success = AsyncMock()

        error_response = MagicMock()
        error_response.status_code = 503
        error_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 503"))

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status = MagicMock()

        middleware = RequestMiddleware(mw_mock_adapter)
        with patch('httpx.AsyncClient') as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(side_effect=[error_response, success_response])
            MockClient.return_value.__aenter__.return_value = instance

            response = await middleware.post("http://test/api", {"key": "value"})

            assert response.status_code == 200
            mw_mock_adapter.handle_failure.assert_called_once()
            mw_mock_adapter.mark_success.assert_called_once()

    def test_get_request_middleware_singleton(self, mw_mock_pool) -> Any:
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mw_mock_pool):
            m1 = get_request_middleware("bot1", timeout=20.0)
            m2 = get_request_middleware("bot1", timeout=20.0)
            assert m1 is m2

            m3 = get_request_middleware("bot1", timeout=30.0)
            assert m3 is not m1


class TestProxyNetworkFailures:
    """Tests simulating real network failures."""

    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        pool.get_all_proxies = MagicMock(return_value=[
            MagicMock(url='socks5://proxy1:1080', full_name='Proxy1'),
            MagicMock(url='socks5://proxy2:1080', full_name='Proxy2'),
        ])
        pool.failed_proxies = set()
        pool.get_working_proxy = AsyncMock(return_value=MagicMock(url='socks5://proxy1:1080', full_name='Proxy1'))
        pool.mark_success = AsyncMock()
        pool.mark_failed = AsyncMock()
        pool.get_next_proxy = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_proxy_connection_error_triggers_retry(self, mock_pool) -> Any:
        """Simulate connection error to proxy - should trigger failure handling."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            adapter._retries = 0

            mock_pool.get_next_proxy = AsyncMock(return_value=MagicMock(url='socks5://proxy2:1080', full_name='Proxy2'))

            result = await adapter.handle_failure()

            assert result is True
            assert adapter.current_proxy.url == 'socks5://proxy2:1080'
            mock_pool.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_proxies_fail_returns_false(self, mock_pool) -> Any:
        """When all proxies fail, should return False."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            adapter._retries = 0

            mock_pool.get_next_proxy = AsyncMock(return_value=None)

            result = await adapter.handle_failure()

            assert result is False
            mock_pool.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, mock_pool) -> Any:
        """Should stop retrying after max_retries."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock()
            adapter._retries = 3
            adapter._max_retries = 3

            result = await adapter.handle_failure()

            assert result is False

    @pytest.mark.asyncio
    async def test_timeout_error_handled(self, mock_pool) -> Any:
        """Simulate timeout during request - should mark failure."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            adapter._retries = 0

            await adapter.mark_failure()

            mock_pool.mark_failed.assert_called_once()
            assert adapter._retries == 0

    @pytest.mark.asyncio
    async def test_recovery_after_switch(self, mock_pool) -> Any:
        """After switching proxy, successful request should reset retries."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            adapter._retries = 1

            await adapter.mark_success()

            assert adapter._retries == 0
            mock_pool.mark_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_proxy_uses_direct_connection(self, mock_pool) -> Any:
        """When no proxy available, should work without proxy."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = None

            proxy = adapter.get_proxy_for_httpx()
            assert proxy is None

    @pytest.mark.asyncio
    async def test_successful_request_after_failures(self, mock_pool) -> Any:
        """Multiple failures then success should work."""
        with patch('services.proxy_adapter.get_proxy_pool', return_value=mock_pool):
            adapter = ProxyAdapter(bot_id="test_bot")
            adapter.current_proxy = MagicMock(url='socks5://proxy1:1080', full_name='Proxy1')
            adapter._retries = 0

            mock_pool.get_next_proxy = AsyncMock(return_value=MagicMock(url='socks5://proxy2:1080', full_name='Proxy2'))

            await adapter.handle_failure()
            assert adapter.current_proxy.url == 'socks5://proxy2:1080'

            await adapter.mark_success()
            assert adapter._retries == 0
