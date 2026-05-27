# Tests/test_rate_limit.py
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

logger = logging.getLogger(__name__)

import pytest

from tg_bot.rate_limit_middleware import (
    RateLimitMiddleware,
    throttle_ai,
    throttle_callback,
    throttle_search,
)

_middleware = RateLimitMiddleware()


def _get_user_id(update) -> Any:
    """Extract user_id from update."""
    try:
        if update.callback_query:
            return update.callback_query.from_user.id
        if update.message:
            return update.message.from_user.id
        if update.effective_user:
            return update.effective_user.id
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"[databases/kojo/tests/test_rate_limit.py] Connection error: {e}")
    return None


@pytest.mark.asyncio
async def test_throttle_callback_blocks_after_five_calls() -> Any:
    """Callback should be blocked after 5 rapid calls."""
    _middleware._timestamps["callback"].clear()

    @throttle_callback
    async def handler(update, context) -> Any:
        return "ok"

    mock_update = MagicMock()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.from_user.id = 999
    mock_update.callback_query.answer = AsyncMock()

    # First 5 Calls Should Succeed
    for i in range(5):
        result = await handler(mock_update, None)
        assert result == "ok", f"Call {i+1} should succeed"

    # 6th Call Should Be Blocked
    result6 = await handler(mock_update, None)
    assert result6 is None


@pytest.mark.asyncio
async def test_throttle_callback_different_users_not_blocked() -> Any:
    """Different users should not block each other."""
    _middleware._timestamps["callback"].clear()

    @throttle_callback
    async def handler(update, context) -> Any:
        return "ok"

    user1 = MagicMock()
    user1.callback_query.from_user.id = 101
    user1.callback_query.answer = AsyncMock()

    user2 = MagicMock()
    user2.callback_query.from_user.id = 102
    user2.callback_query.answer = AsyncMock()

    result1 = await handler(user1, None)
    assert result1 == "ok"

    result2 = await handler(user2, None)
    assert result2 == "ok"


@pytest.mark.asyncio
async def test_throttle_ai_blocks_rapid_calls() -> Any:
    """AI calls should be blocked within TTL window."""
    _middleware._timestamps["ai"].clear()

    @throttle_ai
    async def handler(update, context) -> Any:
        return "response"

    mock_update = MagicMock()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.from_user.id = 888
    mock_update.callback_query.answer = AsyncMock()
    mock_update.message = None

    result = await handler(mock_update, None)
    assert result == "response"

    result2 = await handler(mock_update, None)
    assert result2 is None


@pytest.mark.asyncio
async def test_throttle_ai_message_blocks() -> Any:
    """Message-type updates should be blocked."""
    _middleware._timestamps["ai"].clear()

    @throttle_ai
    async def handler(update, context) -> Any:
        return "response"

    mock_update = MagicMock()
    mock_update.message = MagicMock()
    mock_update.message.from_user.id = 777
    mock_update.message.reply_text = AsyncMock()
    mock_update.callback_query = None

    result = await handler(mock_update, None)
    assert result == "response"

    result2 = await handler(mock_update, None)
    assert result2 is None


@pytest.mark.asyncio
async def test_throttle_search_blocks_rapid_search() -> Any:
    """Search should be blocked within TTL."""
    _middleware._timestamps["search"].clear()

    @throttle_search
    async def handler(update, context) -> Any:
        return "results"

    mock_update = MagicMock()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.from_user.id = 555
    mock_update.callback_query.answer = AsyncMock()

    result = await handler(mock_update, None)
    assert result == "results"

    result2 = await handler(mock_update, None)
    assert result2 is None


@pytest.mark.asyncio
async def test_get_user_id_from_callback() -> Any:
    """Extract user_id from callback query."""
    mock_update = MagicMock()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.from_user.id = 12345

    user_id = _get_user_id(mock_update)
    assert user_id == 12345


@pytest.mark.asyncio
async def test_get_user_id_from_message() -> Any:
    """Extract user_id from message."""
    mock_update = MagicMock()
    mock_update.message = MagicMock()
    mock_update.message.from_user.id = 67890
    mock_update.callback_query = None

    user_id = _get_user_id(mock_update)
    assert user_id == 67890


@pytest.mark.asyncio
async def test_get_user_id_returns_none_for_invalid() -> Any:
    """Returns None for None updates."""
    mock_update = MagicMock()
    mock_update.callback_query = None
    mock_update.message = None
    mock_update.effective_user = None

    user_id = _get_user_id(mock_update)
    assert user_id is None
