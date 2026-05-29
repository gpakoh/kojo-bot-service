"""Tests for InfoService tenant-aware connections."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.info_service import InfoService
from tg_bot.tenant.config import set_current_tenant


class TestInfoService:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        return pool, conn

    @pytest.mark.asyncio
    async def test_uses_tenant_connection_when_tenant_is_set(self) -> Any:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"id": 1, "title": "Test"})

        pool = MagicMock()
        pool.acquire = MagicMock()

        class DummyDbManager:
            def __init__(self) -> None:
                self.called = False
                self.seen_tenant_id = None

            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                self.called = True
                self.seen_tenant_id = tenant_id
                yield conn

        db_manager = DummyDbManager()
        service = InfoService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            result = await service.get_page(page_id=1)
        finally:
            set_current_tenant(None)

        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        assert result == {"id": 1, "title": "Test"}
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={"id": 1, "title": "Test"})

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = InfoService(pool, db_manager=DummyDbManager())
        result = await service.get_page(page_id=1)
        assert result == {"id": 1, "title": "Test"}
        conn.fetchrow.assert_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={"id": 1, "title": "Test"})

        service = InfoService(pool)
        result = await service.get_page(page_id=1)
        assert result == {"id": 1, "title": "Test"}
        conn.fetchrow.assert_awaited()
