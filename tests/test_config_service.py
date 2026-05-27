# Tests/test_config_service.py
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.config_service import (
    CachedConfig,
    ConfigSource,
    DatabaseConfig,
    EnvironmentConfig,
    create_hierarchical_config,
)


class TestCachedConfig:
    @pytest.fixture
    def cache(self) -> Any:
        return CachedConfig(ttl=2.0, maxsize=10)

    def test_cache_miss_returns_none(self, cache) -> Any:
        assert cache.get("key") is None

    def test_cache_hit_returns_values(self, cache) -> Any:
        cache.set("key", ConfigSource(value="val1", source="env"))
        assert cache.get("key").value == "val1"

    def test_cache_invalidation(self, cache) -> Any:
        cache.set("key", ConfigSource(value="val1", source="env"))
        cache.invalidate("key")
        assert cache.get("key") is None

    def test_cache_prefix_invalidation(self, cache) -> Any:
        cache.set("proxy_url", ConfigSource(value="p1", source="db"))
        cache.set("proxy_enabled", ConfigSource(value="true", source="db"))
        cache.set("product_hash", ConfigSource(value="abc", source="env"))
        cache.invalidate_prefix("proxy_")
        assert cache.get("proxy_url") is None
        assert cache.get("proxy_enabled") is None
        assert cache.get("product_hash") is not None


class TestEnvironmentConfig:
    def test_get_from_environ(self) -> Any:
        with patch.dict("os.environ", {"TEST_VAR": "test_val"}):
            env = EnvironmentConfig()
            assert env.get("TEST_VAR") == "test_val"

    def test_get_none_for_missing(self) -> Any:
        env = EnvironmentConfig()
        assert env.get("NONEXISTENT_VAR") is None


class TestDatabaseConfig:
    @pytest.fixture
    def mock_settings(self) -> Any:
        svc = MagicMock()
        svc.get_setting = AsyncMock(return_value="db_value")
        svc.set_setting = AsyncMock()
        svc.delete_setting = AsyncMock()
        svc.get_all_settings = AsyncMock(return_value={"a": "1", "b": "2"})
        return svc

    @pytest.mark.asyncio
    async def test_db_get(self, mock_settings) -> Any:
        db = DatabaseConfig(mock_settings)
        result = await db.get("key")
        assert result == "db_value"

    @pytest.mark.asyncio
    async def test_db_set(self, mock_settings) -> Any:
        db = DatabaseConfig(mock_settings)
        await db.set("key", "value")
        mock_settings.set_setting.assert_awaited_once_with("key", "value")

    @pytest.mark.asyncio
    async def test_db_delete(self, mock_settings) -> Any:
        db = DatabaseConfig(mock_settings)
        await db.delete("key")
        mock_settings.delete_setting.assert_awaited_once_with("key")

    @pytest.mark.asyncio
    async def test_db_load_all(self, mock_settings) -> Any:
        db = DatabaseConfig(mock_settings)
        result = await db.load_all()
        assert result == {"a": "1", "b": "2"}


class TestHierarchicalConfig:
    @pytest.mark.asyncio
    async def test_get_priority_cache_first(self) -> Any:
        mock_svc = MagicMock()
        mock_svc.get_setting = AsyncMock(return_value="db_val")
        mock_svc.get_all_settings = AsyncMock(return_value={})

        config = await create_hierarchical_config(settings_service=mock_svc)
        config._cache.set("key", ConfigSource(value="db_val", source="db"))
        result = await config.get("key")
        assert result == "db_val"

    @pytest.mark.asyncio
    async def test_get_priority_env_fallback(self) -> Any:
        mock_svc = MagicMock()
        mock_svc.get_setting = AsyncMock(return_value=None)
        mock_svc.get_all_settings = AsyncMock(return_value={})

        config = await create_hierarchical_config(settings_service=mock_svc)
        config._env.get = MagicMock(return_value="env_val")
        result = await config.get("unknown_key")
        assert result == "env_val"

    @pytest.mark.asyncio
    async def test_get_default_fallback(self) -> Any:
        mock_svc = MagicMock()
        mock_svc.get_setting = AsyncMock(return_value=None)
        mock_svc.get_all_settings = AsyncMock(return_value={})

        config = await create_hierarchical_config(settings_service=mock_svc)
        result = await config.get("missing_key", "default")
        assert result == "default"

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self) -> Any:
        mock_svc = MagicMock()
        mock_svc.get_setting = AsyncMock(return_value=None)
        mock_svc.get_all_settings = AsyncMock(return_value={})

        config = await create_hierarchical_config(settings_service=mock_svc)
        config._cache.set("key", ConfigSource(value="val", source="db"))
        config.invalidate("key")
        assert config._cache.get("key") is None

    @pytest.mark.asyncio
    async def test_warm_cache(self) -> Any:
        mock_svc = MagicMock()
        mock_svc.get_setting = AsyncMock(return_value=None)
        mock_svc.get_all_settings = AsyncMock(return_value={"k1": "v1", "k2": "v2"})

        config = await create_hierarchical_config(settings_service=mock_svc)
        assert config._cache_warm is True
        assert config._cache.get("k1").value == "v1"
        assert config._cache.get("k2").value == "v2"

    @pytest.mark.asyncio
    async def test_stats(self) -> Any:
        mock_svc = MagicMock()
        mock_svc.get_setting = AsyncMock(return_value=None)
        mock_svc.get_all_settings = AsyncMock(return_value={})

        config = await create_hierarchical_config(settings_service=mock_svc)
        stats = config.stats()
        assert "size" in stats
        assert "warmed" in stats
