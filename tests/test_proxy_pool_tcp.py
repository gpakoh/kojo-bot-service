"""Tests for ProxyPool TCP connectivity checks."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.proxy_pool import ProxyPool, ProxyServer


@pytest.mark.asyncio
async def test_check_proxy_success() -> None:
    """Proxy that accepts TCP should return True."""
    pool = ProxyPool(bot_id="test")
    proxy = ProxyServer(host="127.0.0.1", port=12345)

    # Mock Successful Connection
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    with patch('asyncio.open_connection', return_value=(mock_reader, mock_writer)):
        result = await pool._check_proxy(proxy, timeout=1.0)
        assert result is True


@pytest.mark.asyncio
async def test_check_proxy_refused() -> None:
    """Proxy that refuses connection should return False."""
    pool = ProxyPool(bot_id="test")
    proxy = ProxyServer(host="127.0.0.1", port=12345)

    # Mock Connection Refused
    with patch('asyncio.open_connection', side_effect=ConnectionRefusedError("Connection refused")):
        result = await pool._check_proxy(proxy, timeout=1.0)
        assert result is False


@pytest.mark.asyncio
async def test_get_working_proxy_returns_first_available() -> None:
    """Should return first working proxy."""
    pool = ProxyPool(bot_id="test")

    proxy1 = ProxyServer(host="proxy1.test", port=8080)
    proxy2 = ProxyServer(host="proxy2.test", port=8080)
    pool.proxies = [proxy1, proxy2]

    # Mock _check_proxy To Return True For Proxy1, False For Proxy2
    async def mock_check(proxy, timeout=3.0):
        return proxy is proxy1  # Only proxy1 works

    # Patch At Class Level To Affect All Calls
    original = ProxyPool._check_proxy
    ProxyPool._check_proxy = staticmethod(mock_check)

    try:
        # Disable Health Check By Setting Last Check To Now
        pool._last_health_check = datetime.now(timezone.utc)

        # Manually Add Proxy2 To Failed_proxies To Simulate It Being Down
        # And Ensure Proxy1 Is NOT In Failed_proxies
        pool.failed_proxies = {proxy2.url: datetime.now(timezone.utc)}

        result = await pool.get_working_proxy()
        assert result is proxy1
    finally:
        ProxyPool._check_proxy = original


class TestProxyPoolStateCoverage:
    """Close gaps in proxy_pool.py (44% → target 80%+)."""

    @pytest.fixture
    def pool(self) -> "ProxyPool":
        return ProxyPool(bot_id="cov_test")

    def test_get_all_proxies_returns_copy(self, pool) -> None:
        pool.proxies = [ProxyServer(host="h1", port=80), ProxyServer(host="h2", port=81)]
        result = pool.get_all_proxies()
        assert len(result) == 2
        result.pop()
        assert len(pool.proxies) == 2  # original unchanged

    def test_get_failed_count(self, pool) -> None:
        pool.failed_proxies = {"http://a:80": datetime.now(timezone.utc)}
        assert pool.get_failed_count() == 1

    def test_get_metrics_structure(self, pool) -> None:
        pool.proxies = [ProxyServer(host="h", port=80)]
        pool._total_failovers = 5
        pool._total_requests = 10
        m = pool.get_metrics()
        assert m["total_proxies"] == 1
        assert m["failed_proxies"] == 0
        assert m["total_failovers"] == 5
        assert m["total_requests"] == 10
        assert "proxies" in m

    def test_record_request_increments(self, pool) -> None:
        pool.record_request()
        pool.record_request()
        assert pool._total_requests == 2

    @pytest.mark.asyncio
    async def test_mark_failed_adds_to_failed(self, pool) -> None:
        p = ProxyServer(host="h", port=80)
        await pool.mark_failed(p)
        assert p.url in pool.failed_proxies
        assert p.failure_count == 1

    @pytest.mark.asyncio
    async def test_mark_success_removes_from_failed(self, pool) -> None:
        p = ProxyServer(host="h", port=80)
        pool.failed_proxies[p.url] = datetime.now(timezone.utc)
        await pool.mark_success(p)
        assert p.url not in pool.failed_proxies
        assert p.success_count == 1

    @pytest.mark.asyncio
    async def test_record_response_time_ema(self, pool) -> None:
        p = ProxyServer(host="h", port=80)
        await pool.record_response_time(p, 1.0)
        assert p.avg_response_time == 1.0
        await pool.record_response_time(p, 2.0)
        # EMA: 0.7*1.0 + 0.3*2.0 = 1.3
        assert pytest.approx(p.avg_response_time, 0.01) == 1.3

    @pytest.mark.asyncio
    async def test_get_next_proxy_exhausted_returns_none(self, pool) -> None:
        pool.proxies = [ProxyServer(host="h", port=80)]
        # URL Is A Property, Can't Assign - Add To Failed_proxies Directly
        pool.failed_proxies["http://h:80"] = datetime.now(timezone.utc)
        result = await pool.get_next_proxy(pool.proxies[0])
        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_proxy_skips_current(self, pool) -> None:
        p1 = ProxyServer(host="h1", port=80)
        p2 = ProxyServer(host="h2", port=81)
        pool.proxies = [p1, p2]
        # Mock _check_proxy To Always Return True For This Test
        original = ProxyPool._check_proxy
        # _check_proxy Is An Async Method: (self, P, Timeout=3.0)
        # Replace With An Async Mock
        async def mock_check(self, p, timeout=3.0):
            return True
        ProxyPool._check_proxy = mock_check
        try:
            result = await pool.get_next_proxy(p1)
            assert result == p2
        finally:
            ProxyPool._check_proxy = original
