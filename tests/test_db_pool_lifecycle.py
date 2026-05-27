from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_pool_acquire_release_cycle() -> None:
    mock_conn = MagicMock()
    mock_conn.close = AsyncMock()

    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    async with mock_pool.acquire() as conn:
        assert conn is mock_conn

    mock_pool.acquire.return_value.__aexit__.assert_awaited_once()

@pytest.mark.asyncio
async def test_pool_close_gracefully() -> None:
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()

    await mock_pool.close()
    mock_pool.close.assert_awaited_once()
