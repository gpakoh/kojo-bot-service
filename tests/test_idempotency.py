"""Integration tests for IdempotencyStore."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.infrastructure.idempotency import IdempotencyStore


class TestIdempotencyStore:
    @pytest.fixture
    def mock_redis(self) -> Any:
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def store(self, mock_redis) -> IdempotencyStore:
        return IdempotencyStore(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_check_miss_returns_none(self, store, mock_redis) -> Any:
        result = await store.check("order", "key-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_hit_returns_result(self, store, mock_redis) -> Any:
        mock_redis.get = AsyncMock(return_value=b'{"status": "completed", "order_id": 42}')
        result = await store.check("order", "key-123")
        assert result == {"status": "completed", "order_id": 42}

    @pytest.mark.asyncio
    async def test_start_sets_processing(self, store, mock_redis) -> Any:
        await store.start("order", "key-456")
        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "idempotency:order:key-456"
        assert "processing" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_complete_sets_result(self, store, mock_redis) -> Any:
        await store.complete("order", "key-789", {"order_id": 99})
        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert "99" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_key_format(self, store, mock_redis) -> Any:
        await store.start("payment", "pay-001")
        key = mock_redis.setex.call_args[0][0]
        assert key == "idempotency:payment:pay-001"
