# Tg_bot/rate_limit_middleware.py
# Unified Ratelimitmiddleware — Multiple Buckets With Per-action Configuration.
# Integrates As Telegram-ext Application Middleware Via App.add_middleware().
# Also Provides Decorators For Per-handler Rate Limiting.

import logging
import time
from functools import wraps
from typing import Any, Awaitable, Callable, Optional

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

logger = logging.getLogger(__name__)


class BucketConfig:
    """Configuration for a single rate-limit bucket."""
    def __init__(self, ttl: float = 3.0, max_calls: int = 1,
                 message: str = "Слишком быстро! Подождите..."):
        self.ttl = ttl
        self.max_calls = max_calls
        self.message = message


class RateLimitMiddleware:
    """
    Multi-bucket rate limiter as telegram-ext Application middleware.
    Each bucket has its own TTL and call limit.

    Usage in main.py:
        from tg_bot.rate_limit_middleware import app_middleware
        app.add_middleware(app_middleware)

    Per-handler usage:
        @throttle_ai
        async def handle_ai(update, context):
            ...
    """

    def __init__(self, buckets: Optional[dict[str, BucketConfig]] = None) -> None:
        self.buckets = buckets or {
            "callback":    BucketConfig(ttl=1.0,  max_calls=5, message="⏳ Не спешите..."),
            "message":     BucketConfig(ttl=1.0,  max_calls=3, message="Подождите..."),
            "ai":          BucketConfig(ttl=3.0,  max_calls=1, message="🤖 Подождите, формирую ответ..."),
            "search":     BucketConfig(ttl=2.0,  max_calls=1, message="🔍 Подождите..."),
            "payment":    BucketConfig(ttl=10.0, max_calls=2, message="💳 Подождите..."),
            "order":      BucketConfig(ttl=3.0,  max_calls=1, message="📦 Подождите..."),
            "navigation": BucketConfig(ttl=1.0,  max_calls=5, message="⏳ Не спешите..."),
        }
        self._timestamps: dict[str, dict[int, list[float]]] = {
            name: {} for name in self.buckets
        }

    def _user_key(self, update: Update) -> Optional[int]:
        try:
            if update.callback_query:
                return update.callback_query.from_user.id
            if update.message:
                return update.message.from_user.id  # type: ignore[union-attr]
            if update.effective_user:
                return update.effective_user.id
        except Exception as e:
            # Broad by design: middleware boundary — user identity extraction failure must degrade to no rate limiting, not crash
            logger.warning(f"[databases/kojo/tg_bot/rate_limit_middleware.py] (Exception): {e}")
        return None

    def check(self, update_or_user_id: Any, bucket_name: str = "callback") -> tuple[bool, Optional[str]]:
        """Check if user is rate-limited. Accepts Update or user_id."""
        if isinstance(update_or_user_id, Update):
            user_id = self._user_key(update_or_user_id)
        else:
            user_id = update_or_user_id

        if user_id is None:
            return False, None

        cfg = self.buckets.get(bucket_name)
        if cfg is None:
            return False, None

        now = time.monotonic()
        timestamps = self._timestamps[bucket_name].setdefault(user_id, [])

        cutoff = now - cfg.ttl
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= cfg.max_calls:
            logger.debug(f"Rate limit: user={user_id} bucket={bucket_name}")
            return True, cfg.message

        timestamps.append(now)
        return False, None

    def consume(self, update: Update, bucket_name: str = "callback") -> bool:
        """Consume one call slot in the bucket. Returns True if allowed."""
        user_id = self._user_key(update)
        if user_id is None:
            return True

        cfg = self.buckets.get(bucket_name)
        if cfg is None:
            return True

        now = time.monotonic()
        timestamps = self._timestamps[bucket_name].setdefault(user_id, [])
        cutoff = now - cfg.ttl
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= cfg.max_calls:
            return False

        timestamps.append(now)
        return True

    def clear_user(self, user_id: int) -> Any:
        """Clear all rate limits for a user."""
        for ts_dict in self._timestamps.values():
            ts_dict.pop(user_id, None)

    def stats(self, user_id: int) -> dict[str, Any]:
        """Return rate limit status for a user across all buckets."""
        now = time.monotonic()
        result = {}
        for name, cfg in self.buckets.items():
            timestamps = self._timestamps[name].get(user_id, [])
            active = [t for t in timestamps if now - t < cfg.ttl]
            result[name] = {
                "hits": len(active),
                "limit": cfg.max_calls,
                "ttl": cfg.ttl,
                "remaining": max(0, cfg.max_calls - len(active)),
                "limited": len(active) >= cfg.max_calls,
            }
        return result

    def _resolve_bucket(self, update: Update) -> str:
        """Map update to bucket name by tokenized callback data."""
        if update.callback_query:
            data = update.callback_query.data or ""
            tokens = data.lower().split("_")
            if "ai" in tokens:
                return "ai"
            if "search" in tokens or "find" in tokens:
                return "search"
            if "cart" in tokens or "order" in tokens:
                return "order"
            if "pay" in tokens:
                return "payment"
            return "callback"
        elif update.message:
            return "message"
        return "callback"

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        next_handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        """PTB Application middleware entry point."""
        user_id = self._user_key(update)
        if user_id is None:
            return await next_handler()

        # Determine Bucket
        bucket_name = self._resolve_bucket(update)
        cfg = self.buckets.get(bucket_name)
        if cfg is None:
            return await next_handler()

        # Check Rate Limit
        is_limited, msg = self.check(update, bucket_name)
        if is_limited:
            logger.warning(f"Rate limited: user={user_id} bucket={bucket_name}")
            if update.callback_query:
                try:
                    await update.callback_query.answer(msg, show_alert=True)
                except Exception as e:
                    # Broad by design: middleware boundary — callback answer failure must not crash rate limit enforcement
                    logger.warning(f"[databases/kojo/tg_bot/rate_limit_middleware.py] callback_query.answer error: {e}")
            raise ApplicationHandlerStop()

        return await next_handler()

    async def postprocess(self, update: Update, result: Any, context: ContextTypes.DEFAULT_TYPE) -> Any:
        pass


# Singleton Instance — Use This In Main.py
app_middleware = RateLimitMiddleware()

# Global Middleware For Decorators (uses Singleton)
_middleware = app_middleware


def throttle_callback(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit callback buttons."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "callback")
        if is_limited:
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def throttle_message(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit message handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "message")
        if is_limited:
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def throttle_ai(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit AI handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "ai")
        if is_limited:
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def throttle_search(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit search handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "search")
        if is_limited:
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def throttle_payment(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit payment handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "payment")
        if is_limited:
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def throttle_order(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit order handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "order")
        if is_limited:
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def throttle_navigation(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: rate-limit navigation handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        is_limited, msg = _middleware.check(update, "navigation")
        if is_limited:
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper
