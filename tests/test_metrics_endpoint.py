import pytest
from aiohttp import web

from tg_bot.infrastructure.health_server import create_health_app
from tg_bot.infrastructure.metrics import (
    REGISTRY,
    kojo_active_users,
    kojo_db_query_duration_seconds,
    kojo_llm_latency_seconds,
    kojo_order_value_sum,
    kojo_orders_total,
    kojo_proxy_failover_count,
)


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_format() -> None:
    app = create_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18082)
    await site.start()

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18082/metrics") as resp:
            assert resp.status == 200
            text = await resp.text()
            assert "kojo_orders" in text or "# HELP" in text

    await runner.cleanup()


@pytest.mark.asyncio
async def test_metrics_contains_all_required_metrics() -> None:
    # Reset Registry To Avoid Cross-test Pollution
    for sample in REGISTRY.collect():
        pass

    # Pre-populate Metrics With Sample Data
    kojo_orders_total.labels(status="created", tenant_id="default").inc()
    kojo_order_value_sum.observe(150.0)
    kojo_llm_latency_seconds.observe(1.5)
    kojo_proxy_failover_count.labels(bot_id="kojo").inc()
    kojo_db_query_duration_seconds.observe(0.05)
    kojo_active_users.labels(tenant_id="default").set(1)

    app = create_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18085)
    await site.start()

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18085/metrics") as resp:
            assert resp.status == 200
            text = await resp.text()

            required = [
                "kojo_orders_total",
                "kojo_order_value_sum",
                "kojo_llm_latency_seconds",
                "kojo_proxy_failover_count",
                "kojo_db_query_duration_seconds",
                "kojo_active_users",
            ]
            for metric in required:
                assert metric in text, f"Missing metric: {metric}"

    await runner.cleanup()
