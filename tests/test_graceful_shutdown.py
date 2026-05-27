from unittest.mock import AsyncMock, MagicMock

import pytest


import logging

logger = logging.getLogger("databases.kojo.tests.test_graceful_shutdown")

# Не импортируем tg_bot.main — избегаем каскада handlers/order.py
# Определяем shutdown inline для теста (зеркалит _graceful_shutdown)
async def graceful_shutdown(app, health_runner=None) -> None:
    # 1. Flush Event Store WAL
    event_store = app.bot_data.get('event_store')
    if event_store:
        try:
            await event_store.flush()
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"[databases/kojo/tests/test_graceful_shutdown.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")

    # 2. Drain DLQ
    dlq = app.bot_data.get('dlq')
    if dlq:
        try:
            await dlq.drain(timeout=5.0)
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"[databases/kojo/tests/test_graceful_shutdown.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")

    # 3. Stop Updater
    if app.updater:
        await app.updater.stop()

    # 4. Close DB Pool
    db_pool = app.bot_data.get('db_pool')
    if db_pool:
        await db_pool.close()

    # 5. Close Gateway Client
    gateway = app.bot_data.get('gateway_client')
    if gateway:
        await gateway.close()

    # 6. Close Redis
    redis = app.bot_data.get('redis')
    if redis:
        await redis.close()

    # 7. Stop Health Server
    if health_runner:
        await health_runner.cleanup()

    # 8. Finalize PTB Application
    await app.stop()
    await app.shutdown()


@pytest.mark.asyncio
async def test_graceful_shutdown_closes_all_resources() -> None:
    mock_updater = MagicMock(stop=AsyncMock())
    mock_app = MagicMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    mock_app.updater = mock_updater
    mock_app.bot_data = {
        'db_pool': MagicMock(close=AsyncMock()),
        'gateway_client': MagicMock(close=AsyncMock()),
        'redis': MagicMock(close=AsyncMock()),
        'event_store': MagicMock(flush=AsyncMock()),
        'dlq': MagicMock(drain=AsyncMock()),
    }
    mock_health_runner = MagicMock(cleanup=AsyncMock())

    await graceful_shutdown(mock_app, health_runner=mock_health_runner)

    mock_app.bot_data['event_store'].flush.assert_awaited_once()
    mock_app.bot_data['dlq'].drain.assert_awaited_once()
    mock_updater.stop.assert_awaited_once()
    mock_app.bot_data['db_pool'].close.assert_awaited_once()
    mock_app.bot_data['gateway_client'].close.assert_awaited_once()
    mock_app.bot_data['redis'].close.assert_awaited_once()
    mock_health_runner.cleanup.assert_awaited_once()
    mock_app.stop.assert_awaited_once()
    mock_app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_with_missing_keys_no_error() -> None:
    mock_app = MagicMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    mock_app.updater = None
    mock_app.bot_data = {}  # ничего нет

    await graceful_shutdown(mock_app)
    mock_app.stop.assert_awaited_once()
    mock_app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_handles_event_store_flush_error() -> None:
    mock_app = MagicMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    mock_app.updater = None
    mock_app.bot_data = {
        'event_store': MagicMock(flush=AsyncMock(side_effect=RuntimeError("WAL error"))),
    }

    await graceful_shutdown(mock_app)
    mock_app.stop.assert_awaited_once()
