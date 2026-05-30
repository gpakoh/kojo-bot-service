from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.favorite_service import FavoriteService
from tg_bot.tenant.config import set_current_tenant


class TestFavoriteService:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        return pool, conn

    @pytest.mark.asyncio
    async def test_add_favorite_executes_query(self, mock_pool) -> Any:
        pool, conn = mock_pool
        service = FavoriteService(pool)
        await service.add_favorite(user_id=123, product_id=456)
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_favorite_executes_query(self, mock_pool) -> Any:
        pool, conn = mock_pool
        service = FavoriteService(pool)
        await service.remove_favorite(user_id=123, product_id=456)
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_favorite_returns_true(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=1)
        service = FavoriteService(pool)
        result = await service.is_favorite(user_id=123, product_id=456)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_user_favorites_returns_list(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[{"product_id": 1}, {"product_id": 2}])
        service = FavoriteService(pool)
        result = await service.get_user_favorites(user_id=123)
        assert result == [1, 2]

    @pytest.mark.asyncio
    async def test_get_favorites_count(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=3)
        service = FavoriteService(pool)
        result = await service.get_favorites_count(user_id=123)
        assert result == 3


class TestFavoriteServiceTenantAware:
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
        conn.execute = AsyncMock(return_value="INSERT 0 1")

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
        service = FavoriteService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            await service.add_favorite(user_id=1, product_id=2)
        finally:
            set_current_tenant(None)

        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = FavoriteService(pool, db_manager=DummyDbManager())
        await service.add_favorite(user_id=1, product_id=2)
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")

        service = FavoriteService(pool)
        await service.add_favorite(user_id=1, product_id=2)
        conn.execute.assert_awaited_once()

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

        service = FavoriteService(pool, db_manager=FailingDbManager())

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        with pytest.raises(RuntimeError, match="tenant db connection failed"):
            await service.add_favorite(user_id=1, product_id=2)
        set_current_tenant(None)

        pool.acquire.assert_not_called()
