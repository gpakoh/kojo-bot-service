"""Tests for RateLimitMiddleware as PTB middleware."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ApplicationHandlerStop

from tg_bot.rate_limit_middleware import RateLimitMiddleware, app_middleware


class TestRateLimitMiddleware:
    @pytest.fixture
    def mw(self) -> RateLimitMiddleware:
        return RateLimitMiddleware()

    @pytest.fixture
    def mock_update(self) -> MagicMock:
        u = MagicMock(spec=Update)
        u.callback_query = AsyncMock()
        u.callback_query.from_user.id = 12345
        u.callback_query.data = "menu_main"
        u.message = None
        return u

    def test_middleware_allows_first_call(self, mw: RateLimitMiddleware, mock_update: MagicMock) -> None:
        next_handler = AsyncMock(return_value="ok")
        result = mw(mock_update, MagicMock(), next_handler)
        import asyncio
        result = asyncio.run(result)
        assert result == "ok"
        next_handler.assert_awaited_once()

    def test_middleware_blocks_after_five_calls(self, mw: RateLimitMiddleware, mock_update: MagicMock) -> None:
        next_handler = AsyncMock(return_value="ok")
        import asyncio

        # First 5 Calls Should Succeed
        for _ in range(5):
            coro = mw(mock_update, MagicMock(), next_handler)
            asyncio.run(coro)

        # 6th Call — Should Raise Applicationhandlerstop
        with pytest.raises(ApplicationHandlerStop):
            coro6 = mw(mock_update, MagicMock(), next_handler)
            asyncio.run(coro6)

    def test_resolve_bucket_callback(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = MagicMock()
        u.callback_query.data = "menu_main"
        u.message = None
        assert mw._resolve_bucket(u) == "callback"

    def test_resolve_bucket_ai(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = MagicMock()
        u.callback_query.data = "ai_chat_start"
        u.message = None
        assert mw._resolve_bucket(u) == "ai"

    def test_resolve_bucket_order(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = MagicMock()
        u.callback_query.data = "order_123"
        u.message = None
        assert mw._resolve_bucket(u) == "order"

    def test_resolve_bucket_payment(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = MagicMock()
        u.callback_query.data = "pay_confirm"
        u.message = None
        assert mw._resolve_bucket(u) == "payment"

    def test_resolve_bucket_message(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = None
        u.message = MagicMock()
        assert mw._resolve_bucket(u) == "message"

    def test_singleton_is_rate_limit_middleware(self) -> None:
        assert isinstance(app_middleware, RateLimitMiddleware)

    def test_check_returns_false_on_first_call(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = MagicMock()
        u.callback_query.from_user.id = 999
        u.callback_query.data = "test"
        u.message = None
        is_limited, msg = mw.check(u, "callback")
        assert is_limited is False
        assert msg is None

    def test_consume_returns_true(self, mw: RateLimitMiddleware) -> None:
        u = MagicMock(spec=Update)
        u.callback_query = MagicMock()
        u.callback_query.from_user.id = 888
        u.callback_query.data = "test"
        u.message = None
        assert mw.consume(u, "callback") is True

    def test_stats_empty(self, mw: RateLimitMiddleware) -> None:
        stats = mw.stats(99999)
        assert "callback" in stats
        assert stats["callback"]["limited"] is False
