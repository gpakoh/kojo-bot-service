"""Integration tests for CacheManager."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.infrastructure.cache import CacheManager


class TestCacheManager:
    @pytest.fixture
    def mock_redis(self) -> Any:
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def cache(self, mock_redis) -> CacheManager:
        return CacheManager(redis=mock_redis, default_ttl=300)

    @pytest.mark.asyncio
    async def test_get_miss_returns_none(self, cache, mock_redis) -> Any:
        result = await cache.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_hit_returns_value(self, cache, mock_redis) -> Any:
        mock_redis.get = AsyncMock(return_value=b'"cached_value"')
        result = await cache.get("existing_key")
        assert result == "cached_value"

    @pytest.mark.asyncio
    async def test_set_saves_value(self, cache, mock_redis) -> Any:
        await cache.set("key", {"data": 123})
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self, cache, mock_redis) -> Any:
        await cache.set("key", "val", ttl=60)
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs.get("ex") == 60

    @pytest.mark.asyncio
    async def test_delete_removes(self, cache, mock_redis) -> Any:
        await cache.delete("key")
        mock_redis.delete.assert_awaited_once_with("key")

    @pytest.mark.asyncio
    async def test_delete_pattern(self, cache, mock_redis) -> Any:
        mock_redis.keys = AsyncMock(return_value=[b"key1", b"key2"])
        mock_redis.delete = AsyncMock(return_value=2)
        result = await cache.delete_pattern("prefix:*")
        assert result == 2

    @pytest.mark.asyncio
    async def test_get_or_set_computes_on_miss(self, cache, mock_redis) -> Any:
        mock_redis.get = AsyncMock(return_value=None)
        factory = AsyncMock(return_value="computed")

        result = await cache.get_or_set("key", factory)
        assert result == "computed"
        factory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_or_set_skips_factory_on_hit(self, cache, mock_redis) -> Any:
        mock_redis.get = AsyncMock(return_value=b'"cached"')
        factory = AsyncMock()

        result = await cache.get_or_set("key", factory)
        assert result == "cached"
        factory.assert_not_called()
