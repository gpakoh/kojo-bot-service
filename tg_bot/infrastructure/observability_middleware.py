# Tg_bot/infrastructure/observability_middleware.py
"""
Observability Middleware.

Wraps handler execution with metrics collection and tracing.
"""
import time
import uuid
from typing import Any, Callable, Optional

from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.infrastructure.correlation import get_correlation_id, set_correlation_id
from tg_bot.infrastructure.observability import (
    get_structured_logger,
    record_request,
    record_request_duration,
    traced_async,
)

logger = get_structured_logger(__name__)


class ObservabilityMiddleware:
    """
    Middleware for collecting metrics and traces.

    Usage:
        application.add_handler(ObservabilityMiddleware())
    """

    def __init__(self) -> None:
        pass

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        next_handler: Callable[..., Any],
    ) -> Any:
        """Wrap handler execution with observability."""
        start_time = time.perf_counter()

        # Generate Or Preserve Correlation ID At Entry Point
        if not get_correlation_id() or get_correlation_id() == "unknown":
            cid = f"req-{uuid.uuid4().hex[:12]}"
            set_correlation_id(cid)

        cid = get_correlation_id()
        if context.user_data is not None:
            context.user_data["_correlation_id"] = cid

        # Determine Handler Name
        handler_name = self._get_handler_name(update, context)

        # Determine User / Chat
        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else 0

        # Determine Tenant
        tenant = getattr(context, 'bot_data', {}).get('_tenant_bot_id', 'unknown')

        # Structured Log: Request Start
        logger.info("Request start", extra={
            "handler": handler_name,
            "user_id": user_id,
            "chat_id": chat_id,
            "correlation_id": cid,
        })

        status = "success"

        try:
            # Execute With Tracing
            async with traced_async(
                f"handle_{handler_name}",
                attributes={
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "tenant": tenant,
                    "correlation_id": cid,
                }
            ):
                result = await next_handler(update, context)

            # Record Success
            record_request(handler_name, status, tenant)
            return result

        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            status = "error"
            # Record Failure
            record_request(handler_name, status, tenant)
            logger.error("Handler failed", extra={
                "handler": handler_name,
                "correlation_id": cid,
                "user_id": user_id,
                "error": str(e),
            })
            raise

        finally:
            # Record Duration
            duration = time.perf_counter() - start_time
            duration_ms = round(duration * 1000, 2)
            record_request_duration(handler_name, duration)

            logger.info("Request end", extra={
                "handler": handler_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "status": status,
                "duration_ms": duration_ms,
            })

    def _get_handler_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Determine handler name from update."""
        if update.message:
            if update.message.text:
                if update.message.text.startswith('/'):
                    return f"command_{update.message.text[1:]}"
                return "message"
        if update.callback_query:
            return "callback"
        if update.inline_query:
            return "inline_query"
        if update.chosen_inline_result:
            return "chosen_inline_result"
        return "unknown"


async def metrics_endpoint() -> Any:
    """Generate /metrics endpoint content."""
    from tg_bot.infrastructure.observability import get_metrics_registry

    registry = get_metrics_registry()
    if registry:
        from prometheus_client import generate_latest
        return generate_latest(registry)
    return b"# Metrics not enabled"


async def health_endpoint(db_pool: Optional[Any] = None) -> dict[str, Any]:
    """Generate /health endpoint response."""
    from tg_bot.infrastructure.observability import check_health

    health = await check_health(db_pool=db_pool)
    return {
        "status": health.status,
        "checks": health.checks,
        "timestamp": health.timestamp,
    }


__all__ = [
    'ObservabilityMiddleware',
    'metrics_endpoint',
    'health_endpoint',
]
