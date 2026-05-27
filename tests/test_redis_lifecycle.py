from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_redis_set_and_get() -> None:
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=b'"cached_value"')

    await mock_redis.set("key", "value")
    result = await mock_redis.get("key")

    assert result == b'"cached_value"'
    mock_redis.set.assert_awaited_once_with("key", "value")

@pytest.mark.asyncio
async def test_redis_connection_error_raises() -> None:
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

    with pytest.raises(ConnectionError):
        await mock_redis.get("key")
