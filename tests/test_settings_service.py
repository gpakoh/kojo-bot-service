# Tests/test_settings_service.py
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSettingsService:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        pool.fetchval = AsyncMock()
        pool.fetch = AsyncMock()
        pool.execute = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_get_setting_found(self, mock_pool) -> Any:
        mock_pool.fetchval.return_value = "true"
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        result = await service.get_setting("auto_approve")
        assert result == "true"
        mock_pool.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_setting_not_found_uses_default(self, mock_pool) -> Any:
        mock_pool.fetchval.return_value = None
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        result = await service.get_setting("nonexistent", "default_val")
        assert result == "default_val"

    @pytest.mark.asyncio
    async def test_set_setting_inserts(self, mock_pool) -> Any:
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        await service.set_setting("proxy_url", "socks5://127.0.0.1:1080")
        mock_pool.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_settings(self, mock_pool) -> Any:
        row1 = MagicMock()
        row1.__getitem__ = lambda s, k: {"key": "k1", "value": "v1"}.get(k)
        row2 = MagicMock()
        row2.__getitem__ = lambda s, k: {"key": "k2", "value": "v2"}.get(k)
        mock_pool.fetch.return_value = [row1, row2]
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        result = await service.get_all_settings()
        assert result == {"k1": "v1", "k2": "v2"}

    @pytest.mark.asyncio
    async def test_delete_setting(self, mock_pool) -> Any:
        from tg_bot.bot_services.settings_service import SettingsService
        service = SettingsService(mock_pool)
        await service.delete_setting("stale_key")
        mock_pool.execute.assert_awaited_once()
