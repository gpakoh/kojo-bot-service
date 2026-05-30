"""Tests for CommunicationService — tenant-scoped connections."""
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.communication_service import CommunicationService
from tg_bot.tenant.config import set_current_tenant


THREAD_ROW = {
    "id": 1,
    "order_id": 100,
    "is_read": False,
    "is_important": False,
    "last_message_at": datetime(2024, 1, 1, 12, 0, 0),
}


class TestCommunicationServiceTenantAware:
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
        conn.fetchrow = AsyncMock(return_value=dict(THREAD_ROW))

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
        service = CommunicationService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            result = await service.get_thread_by_order_id(order_id=100)
        finally:
            set_current_tenant(None)

        assert result is not None
        assert result.order_id == 100
        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=dict(THREAD_ROW))

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = CommunicationService(pool, db_manager=DummyDbManager())
        result = await service.get_thread_by_order_id(order_id=100)
        assert result is not None
        assert result.order_id == 100

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=dict(THREAD_ROW))

        service = CommunicationService(pool)
        result = await service.get_thread_by_order_id(order_id=100)
        assert result is not None
        assert result.order_id == 100

    @pytest.mark.asyncio
    async def test_does_not_fallback_when_tenant_connection_fails(self) -> Any:
        conn = AsyncMock()
        pool = MagicMock()
        pool.acquire = MagicMock()

        class FailingDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise RuntimeError("tenant db connection failed")
                yield  # pragma: no cover

        service = CommunicationService(pool, db_manager=FailingDbManager())

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        with pytest.raises(RuntimeError, match="tenant db connection failed"):
            await service.get_thread_by_order_id(order_id=100)
        set_current_tenant(None)

        pool.acquire.assert_not_called()
