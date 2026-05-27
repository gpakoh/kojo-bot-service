from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from tg_bot.infrastructure.health_server import create_health_app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    app = create_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18081)
    await site.start()

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18081/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"

    await runner.cleanup()


@pytest.mark.asyncio
async def test_ready_returns_200_when_db_ok() -> None:
    app = create_health_app()

    class MockConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def fetchval(self, query):
            return 1

    class MockPool:
        def acquire(self):
            return MockConn()

        async def close(self):
            pass

    app["db_pool"] = MockPool()
    app["redis"] = AsyncMock(ping=AsyncMock(return_value=True))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18082)
    await site.start()

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18082/ready") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ready"
            assert data["checks"]["db"] is True

    await runner.cleanup()


@pytest.mark.asyncio
async def test_ready_returns_503_when_db_down() -> None:
    app = create_health_app()

    # Mock DB Pool That Fails
    mock_pool = MagicMock()
    mock_pool.acquire.side_effect = RuntimeError("DB connection refused")
    app["db_pool"] = mock_pool

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18083)
    await site.start()

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18083/ready") as resp:
            assert resp.status == 503
            data = await resp.json()
            assert data["status"] == "not_ready"
            assert data["checks"]["db"] is False

    await runner.cleanup()


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_format() -> None:
    from tg_bot.infrastructure.health_server import create_health_app
    app = create_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18084)
    await site.start()

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18084/metrics") as resp:
            assert resp.status == 200
            text = await resp.text()
            assert "# HELP" in text

    await runner.cleanup()
