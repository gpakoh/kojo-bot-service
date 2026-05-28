# Tests/test_rate_limit_middleware.py
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ApplicationHandlerStop

from tg_bot.rate_limit_middleware import (
    BucketConfig,
    RateLimitMiddleware,
    throttle_ai,
    throttle_callback,
    throttle_message,
    throttle_navigation,
    throttle_order,
    throttle_payment,
    throttle_search,
)


class TestRateLimitMiddleware:
    @pytest.fixture
    def mw(self) -> Any:
        return RateLimitMiddleware()

    @pytest.fixture
    def mock_update(self) -> Any:
        u = MagicMock()
        u.callback_query.from_user.id = 12345
        u.callback_query.answer = MagicMock()
        return u

    def test_first_call_not_limited(self, mw, mock_update) -> Any:
        limited, msg = mw.check(mock_update, "callback")
        assert limited is False
        assert msg is None

    def test_sixth_call_within_ttl_is_limited(self, mw, mock_update) -> Any:
        # First 5 Calls Should Succeed
        for _ in range(5):
            limited, msg = mw.check(mock_update, "callback")
            assert limited is False

        # 6th Call Should Be Blocked
        limited, msg = mw.check(mock_update, "callback")
        assert limited is True
        assert msg == "⏳ Не спешите..."

    def test_different_users_not_limited(self) -> Any:
        mw = RateLimitMiddleware()
        u1 = MagicMock()
        u1.callback_query.from_user.id = 100
        u2 = MagicMock()
        u2.callback_query.from_user.id = 200

        # Exhaust U1's Callback Bucket (5 Calls)
        for _ in range(5):
            mw.check(u1, "callback")
        # 6th Call Blocked For U1
        limited, _ = mw.check(u1, "callback")
        assert limited is True

        # U2 Should Still Work
        limited, _ = mw.check(u2, "callback")
        assert limited is False

    def test_navigation_bucket_allows_5_calls(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 333

        for i in range(5):
            limited, _ = mw.check(u, "navigation")
            assert limited is False, f"Call {i+1} should pass"

        limited, _ = mw.check(u, "navigation")
        assert limited is True

    def test_payment_bucket_allows_2_calls(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 90002

        assert mw.consume(u, "payment") is True
        assert mw.consume(u, "payment") is True
        assert mw.consume(u, "payment") is False

    def test_clear_user_resets_all_buckets(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 555

        mw.check(u, "callback")
        mw.check(u, "ai")
        mw.check(u, "search")

        mw.clear_user(555)

        stats = mw.stats(555)
        assert all(s["hits"] == 0 for s in stats.values())

    def test_stats_shows_remaining(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 666

        now = time.monotonic()
        ts = mw._timestamps["navigation"]
        ts[666] = [now - 0.1, now - 0.1]

        stats = mw.stats(666)
        assert stats["navigation"]["hits"] == 2
        assert stats["navigation"]["remaining"] == 3
        assert stats["navigation"]["limited"] is False
        assert stats["callback"]["hits"] == 0

    def test_unknown_bucket_not_limited(self, mw, mock_update) -> Any:
        limited, msg = mw.check(mock_update, "nonexistent_bucket")
        assert limited is False

    def test_multiple_buckets_independent(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 777

        # Exhaust Callback Bucket (5 Calls)
        for _ in range(5):
            mw.check(u, "callback")
        limited, _ = mw.check(u, "callback")
        assert limited is True  # Now blocked

        # Search Bucket Should Still Work
        limited, _ = mw.check(u, "search")
        assert limited is False

    def test_consume_respects_max_calls(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 90000

        assert mw.consume(u, "order") is True
        assert mw.consume(u, "order") is False

    def test_user_without_id_not_blocked(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query = None
        u.message = None
        u.effective_user = None

        limited, msg = mw.check(u, "callback")
        assert limited is False

    def test_custom_bucket_config(self) -> Any:
        custom = RateLimitMiddleware(buckets={
            "ultra_strict": BucketConfig(ttl=10.0, max_calls=1, message="Ultra slow!"),
            "lenient": BucketConfig(ttl=60.0, max_calls=10, message="OK"),
        })
        assert custom.buckets["ultra_strict"].ttl == 10.0
        assert custom.buckets["ultra_strict"].max_calls == 1
        assert custom.buckets["lenient"].ttl == 60.0
        assert custom.buckets["lenient"].max_calls == 10


class TestResolveBucket:
    def test_ai_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "ai_ask_question"
        update.message = None

        assert mw._resolve_bucket(update) == "ai"

    def test_search_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "search_coffee"
        update.message = None

        assert mw._resolve_bucket(update) == "search"

    def test_find_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "find_product"
        update.message = None

        assert mw._resolve_bucket(update) == "search"

    def test_cart_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "cart_add_item"
        update.message = None

        assert mw._resolve_bucket(update) == "order"

    def test_order_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "order_checkout"
        update.message = None

        assert mw._resolve_bucket(update) == "order"

    def test_payment_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "pay_now"
        update.message = None

        assert mw._resolve_bucket(update) == "payment"

    def test_default_callback_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "some_other_action"
        update.message = None

        assert mw._resolve_bucket(update) == "callback"

    def test_message_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = MagicMock()

        assert mw._resolve_bucket(update) == "message"

    def test_empty_callback_data(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = ""
        update.message = None

        assert mw._resolve_bucket(update) == "callback"


class TestUserKey:
    def test_callback_query_user(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.from_user.id = 42
        update.message = None
        update.effective_user = None

        assert mw._user_key(update) == 42

    def test_message_user(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message.from_user.id = 99
        update.effective_user = None

        assert mw._user_key(update) == 99

    def test_effective_user(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = None
        update.effective_user.id = 77

        assert mw._user_key(update) == 77

    def test_none_when_no_user(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = None
        update.effective_user = None

        assert mw._user_key(update) is None

    def test_exception_returns_none(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = None

        class BrokenUser:
            @property
            def id(self):
                raise Exception("broken")

        update.effective_user = BrokenUser()

        assert mw._user_key(update) is None


class TestMiddlewareCall:
    @pytest.mark.asyncio
    async def test_passes_through_when_not_limited(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "some_action"
        update.callback_query.from_user.id = 111
        context = MagicMock()
        next_handler = AsyncMock(return_value="ok")

        result = await mw(update, context, next_handler)

        assert result == "ok"
        next_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_application_handler_stop_when_limited(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "callback"
        update.callback_query.from_user.id = 222
        context = MagicMock()

        # Exhaust Callback Bucket (5 Calls)
        for _ in range(5):
            mw.check(update, "callback")

        next_handler = AsyncMock()

        with pytest.raises(ApplicationHandlerStop):
            await mw(update, context, next_handler)

        update.callback_query.answer.assert_called_once()
        next_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_through_when_user_id_is_none(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = None
        update.effective_user = None
        context = MagicMock()
        next_handler = AsyncMock(return_value="ok")

        result = await mw(update, context, next_handler)

        assert result == "ok"
        next_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_through_for_unknown_bucket(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "unknown_token"
        update.callback_query.from_user.id = 333
        mw.buckets = {}
        context = MagicMock()
        next_handler = AsyncMock(return_value="ok")

        result = await mw(update, context, next_handler)

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_callback_query_answer_failure_does_not_crash(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.data = "callback"
        update.callback_query.from_user.id = 444
        update.callback_query.answer = AsyncMock(side_effect=Exception("answer failed"))
        context = MagicMock()

        # Exhaust Callback Bucket (5 Calls)
        for _ in range(5):
            mw.check(update, "callback")
        next_handler = AsyncMock()

        with pytest.raises(ApplicationHandlerStop):
            await mw(update, context, next_handler)


class TestPostprocess:
    @pytest.mark.asyncio
    async def test_postprocess_is_noop(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock()
        context = MagicMock()

        result = await mw.postprocess(update, "some_result", context)

        assert result is None


class TestConsumeEdgeCases:
    def test_consume_with_unknown_bucket_returns_true(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.from_user.id = 555

        result = mw.consume(update, "nonexistent_bucket")

        assert result is True

    def test_consume_user_id_none_returns_true(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = None
        update.effective_user = None

        result = mw.consume(update, "callback")

        assert result is True

    def test_check_with_none_user_id_explicit(self) -> Any:
        mw = RateLimitMiddleware()
        limited, msg = mw.check(None, "callback")
        assert limited is False
        assert msg is None

    def test_resolve_bucket_both_none_returns_callback(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.message = None

        assert mw._resolve_bucket(update) == "callback"


class TestStatsAccuracy:
    def test_stats_shows_remaining_and_limited(self) -> Any:
        mw = RateLimitMiddleware()
        update = MagicMock(spec=Update)
        update.callback_query.from_user.id = 888

        # Use 5 Calls To Exhaust The Callback Bucket
        now = time.monotonic()
        mw._timestamps["callback"][888] = [now - 0.01] * 5

        stats = mw.stats(888)
        cb = stats["callback"]
        assert cb["hits"] == 5
        assert cb["limit"] == 5
        assert cb["remaining"] == 0
        assert cb["limited"] is True
        assert cb["ttl"] == 1.0

    def test_stats_navigation_remaining(self) -> Any:
        mw = RateLimitMiddleware()
        u = MagicMock()
        u.callback_query.from_user.id = 999

        # 2 Navigation Calls
        now = time.monotonic()
        mw._timestamps["navigation"][999] = [now - 0.01, now - 0.02]

        stats = mw.stats(999)
        nav = stats["navigation"]
        assert nav["hits"] == 2
        assert nav["limit"] == 5
        assert nav["remaining"] == 3
        assert nav["limited"] is False

    def test_stats_no_hits(self) -> Any:
        mw = RateLimitMiddleware()
        stats = mw.stats(999)
        assert stats["callback"]["hits"] == 0
        assert stats["callback"]["remaining"] == 5
        assert stats["callback"]["limited"] is False


class FakeUpdateCallback:
    """Helper that acts like an update with callback_query for throttled decorators."""

    def __init__(self, user_id: int = 111):
        self.callback_query = MagicMock()
        self.callback_query.from_user.id = user_id
        self.callback_query.answer = AsyncMock()
        self.message = None
        self.effective_user = MagicMock()
        self.effective_user.id = user_id


class FakeUpdateMessage:
    """Helper that acts like an update with message for throttle_message."""

    def __init__(self, user_id: int = 222):
        self.callback_query = None
        self.message = MagicMock()
        self.message.from_user.id = user_id
        self.effective_user = MagicMock()
        self.effective_user.id = user_id


@pytest.mark.asyncio
class TestThrottleDecorators:
    async def test_throttle_callback_passes_through(self) -> Any:
        @throttle_callback
        async def handler(update, context):
            return "called"

        result = await handler(FakeUpdateCallback(1), MagicMock())
        assert result == "called"

    async def test_throttle_callback_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateCallback(2)
        # Exhaust Callback Bucket (5 Calls)
        for _ in range(5):
            _middleware.check(update, "callback")

        @throttle_callback
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None
        update.callback_query.answer.assert_awaited_once()

    async def test_throttle_message_passes_through(self) -> Any:
        @throttle_message
        async def handler(update, context):
            return "msg_ok"

        result = await handler(FakeUpdateMessage(3), MagicMock())
        assert result == "msg_ok"

    async def test_throttle_message_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateMessage(4)
        # Exhaust Message Bucket (3 Calls)
        for _ in range(3):
            _middleware.check(update, "message")

        @throttle_message
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None

    async def test_throttle_ai_passes_through(self) -> Any:
        @throttle_ai
        async def handler(update, context):
            return "ai_ok"

        result = await handler(FakeUpdateCallback(5), MagicMock())
        assert result == "ai_ok"

    async def test_throttle_ai_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateCallback(6)
        _middleware.check(update, "ai")

        @throttle_ai
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None

    async def test_throttle_search_passes_through(self) -> Any:
        @throttle_search
        async def handler(update, context):
            return "search_ok"

        result = await handler(FakeUpdateCallback(7), MagicMock())
        assert result == "search_ok"

    async def test_throttle_search_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateCallback(8)
        _middleware.check(update, "search")

        @throttle_search
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None

    async def test_throttle_payment_passes_through(self) -> Any:
        @throttle_payment
        async def handler(update, context):
            return "pay_ok"

        result = await handler(FakeUpdateCallback(9), MagicMock())
        assert result == "pay_ok"

    async def test_throttle_payment_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateCallback(10)
        _middleware.check(update, "payment")
        _middleware.check(update, "payment")

        @throttle_payment
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None

    async def test_throttle_order_passes_through(self) -> Any:
        @throttle_order
        async def handler(update, context):
            return "order_ok"

        result = await handler(FakeUpdateCallback(11), MagicMock())
        assert result == "order_ok"

    async def test_throttle_order_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateCallback(12)
        _middleware.check(update, "order")

        @throttle_order
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None

    async def test_throttle_navigation_passes_through(self) -> Any:
        @throttle_navigation
        async def handler(update, context):
            return "nav_ok"

        result = await handler(FakeUpdateCallback(13), MagicMock())
        assert result == "nav_ok"

    async def test_throttle_navigation_blocks_when_limited(self) -> Any:
        from tg_bot.rate_limit_middleware import _middleware

        update = FakeUpdateCallback(14)
        # Exhaust Navigation Bucket (5 Calls)
        for _ in range(5):
            _middleware.check(update, "navigation")

        @throttle_navigation
        async def handler(update, context):
            return "called"

        result = await handler(update, MagicMock())
        assert result is None
