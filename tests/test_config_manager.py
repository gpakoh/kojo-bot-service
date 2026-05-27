from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.utils.redis_config_manager import RedisConfigManager


class TestRedisConfigManager:
    @pytest.fixture
    def manager(self) -> Any:
        return RedisConfigManager(redis_url="redis://localhost:6379/1", ttl=60)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self, manager) -> Any:
        manager._cache_set("test_key", {"value": "cached"})
        result = await manager.read_config_value("test_key")
        assert result == {"value": "cached"}

    @pytest.mark.asyncio
    async def test_cache_miss_reads_from_redis(self, manager) -> Any:
        import redis.asyncio as redis
        mock_redis = MagicMock(spec=redis.Redis)
        mock_redis.hget = AsyncMock(return_value='"redis_value"')
        manager._redis = mock_redis

        result = await manager.read_config_value("test_key")
        assert result == "redis_value"

    @pytest.mark.asyncio
    async def test_write_config_value_caches_and_publishes(self, manager) -> Any:
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.publish = AsyncMock()
        manager._redis = mock_redis

        result = await manager.write_config_value("test_key", "value123")

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_all_config_returns_all_keys(self, manager) -> Any:
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={
            "key1": '"val1"',
            "key2": '"val2"',
        })
        manager._redis = mock_redis

        result = await manager.read_all_config()
        assert result["key1"] == "val1"
        assert result["key2"] == "val2"

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_write(self, manager) -> Any:
        manager._cache_set("test_key", "old_value")
        manager._cache_invalidate("test_key")
        assert manager._cache_get("test_key") is None

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, manager) -> Any:
        import time
        manager._cache_set("test_key", "value")
        manager._cache_ttl = 0.001
        time.sleep(0.01)
        assert manager._cache_get("test_key") is None

    @pytest.mark.asyncio
    async def test_default_returned_when_not_found(self, manager) -> Any:
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        manager._redis = mock_redis

        result = await manager.read_config_value("missing_key", "default_val")
        assert result == "default_val"
