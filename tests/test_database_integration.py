"""Integration tests for database infrastructure."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.infrastructure.database import DatabaseManager


class TestDatabaseManager:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value=None)
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool

    @pytest.fixture
    def db(self, mock_pool) -> DatabaseManager:
        return DatabaseManager(pool=mock_pool)

    @pytest.mark.asyncio
    async def test_execute_query(self, db, mock_pool) -> Any:
        await db.execute("SELECT 1")
        mock_pool.acquire.return_value.__aenter__.return_value.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_all(self, db, mock_pool) -> Any:
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        result = await db.fetch_all("SELECT * FROM users")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_transaction_context(self, db, mock_pool) -> Any:
        conn = MagicMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
        conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        async with db.transaction() as tx_conn:
            assert tx_conn is conn

    @pytest.mark.asyncio
    async def test_health_check(self, db, mock_pool) -> Any:
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"health": 1})
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        result = await db.health_check()
        assert result is True
