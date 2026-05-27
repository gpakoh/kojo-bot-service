"""
HTTP Health & Metrics Server for the bot.
Runs alongside the Telegram bot (polling or webhook) in the same event loop.
"""
import logging
from typing import Any

from aiohttp import web
from prometheus_client import generate_latest

from tg_bot.infrastructure.metrics import REGISTRY

logger = logging.getLogger(__name__)


async def health_handler(request: web.Request) -> web.Response:
    """Liveness probe — process is alive."""
    return web.json_response({"status": "ok", "service": "kojo-bot"})


async def ready_handler(request: web.Request) -> web.Response:
    """Readiness probe — dependencies are reachable."""
    checks: dict[str, bool] = {}

    # Check DB
    pool = request.app.get("db_pool")
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["db"] = True
        except (RuntimeError, ConnectionError, TimeoutError, OSError):
            checks["db"] = False
    else:
        checks["db"] = False

    # Check Redis (if Configured)
    redis = request.app.get("redis")
    if redis:
        try:
            await redis.ping()
            checks["redis"] = True
        except (redis.ConnectionError, redis.TimeoutError, OSError):
            checks["redis"] = False
    else:
        checks["redis"] = False  # optional, not required for ready

    # Redis Is Optional — Only DB Is Required For Ready Status
    all_ok = checks.get("db", False)
    status = 200 if all_ok else 503

    return web.json_response(
        {"status": "ready" if all_ok else "not_ready", "checks": checks},
        status=status,
    )


async def metrics_handler(request: web.Request) -> web.Response:
    """Prometheus metrics endpoint."""
    return web.Response(
        body=generate_latest(REGISTRY),
        content_type="text/plain; version=0.0.4",
    )


def create_health_app(db_pool: Any = None, redis: Any = None) -> web.Application:
    app = web.Application()
    app["db_pool"] = db_pool
    app["redis"] = redis
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", ready_handler)
    app.router.add_get("/metrics", metrics_handler)
    return app


async def start_health_server(
    db_pool: Any = None,
    redis: Any = None,
    port: int = 8080,
) -> Any:
    """Start health server as background asyncio task."""
    app = create_health_app(db_pool, redis)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🩺 Health server started on 0.0.0.0:{port} (/health, /ready, /metrics)")

    # Return Cleanup Task
    async def cleanup() -> None:
        await runner.cleanup()
        logger.info("🩺 Health Server Stopped.")

    return cleanup
