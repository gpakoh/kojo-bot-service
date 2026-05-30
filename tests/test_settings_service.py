# Tests/test_settings_service.py
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.tenant.config import set_current_tenant
from tg_bot.bot_services.settings_service import SettingsService


class TestSettingsService:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetchval = AsyncMock()
        conn.fetch = AsyncMock()
        conn.execute = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_get_setting_found(self, mock_pool) -> Any:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = "true"
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        result = await service.get_setting("auto_approve")
        assert result == "true"
        conn.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_setting_not_found_uses_default(self, mock_pool) -> Any:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        result = await service.get_setting("nonexistent", "default_val")
        assert result == "default_val"

    @pytest.mark.asyncio
    async def test_set_setting_inserts(self, mock_pool) -> Any:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        await service.set_setting("proxy_url", "socks5://127.0.0.1:1080")
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_settings(self, mock_pool) -> Any:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        row1 = MagicMock()
        row1.__getitem__ = lambda s, k: {"key": "k1", "value": "v1"}.get(k)
        row2 = MagicMock()
        row2.__getitem__ = lambda s, k: {"key": "k2", "value": "v2"}.get(k)
        conn.fetch.return_value = [row1, row2]
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        result = await service.get_all_settings()
        assert result == {"k1": "v1", "k2": "v2"}

    @pytest.mark.asyncio
    async def test_delete_setting(self, mock_pool) -> Any:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        await service.delete_setting("stale_key")
        conn.execute.assert_awaited_once()


class TestSettingsServiceTenantAware:
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
        conn.fetchval = AsyncMock(return_value="true")

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
        service = SettingsService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            result = await service.get_setting("auto_approve")
        finally:
            set_current_tenant(None)

        assert result == "true"
        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value="true")

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = SettingsService(pool, db_manager=DummyDbManager())
        result = await service.get_setting("auto_approve")
        assert result == "true"

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value="true")

        service = SettingsService(pool)
        result = await service.get_setting("auto_approve")
        assert result == "true"

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

        service = SettingsService(pool, db_manager=FailingDbManager())

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        with pytest.raises(RuntimeError, match="tenant db connection failed"):
            await service.get_setting("auto_approve")
        set_current_tenant(None)

        pool.acquire.assert_not_called()
