"""Tests for UserAddressService tenant-aware connections."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.user_address_service import UserAddressService
from tg_bot.tenant.config import set_current_tenant


class TestUserAddressService:
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
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchval.return_value = 42

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
        service = UserAddressService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            result = await service.add_address(
                user_id=1, provider="cdek", point_id="p1",
                address_text="ул. Ленина, 1",
            )
        finally:
            set_current_tenant(None)

        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        assert result == 42
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchval.return_value = 5

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = UserAddressService(pool, db_manager=DummyDbManager())
        result = await service.add_address(
            user_id=1, provider="cdek", point_id="p1",
            address_text="ул. Ленина, 1",
        )
        assert result == 5
        conn.fetchval.assert_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchval.return_value = 5

        service = UserAddressService(pool)
        result = await service.add_address(
            user_id=1, provider="cdek", point_id="p1",
            address_text="ул. Ленина, 1",
        )
        assert result == 5
        conn.fetchval.assert_awaited()
