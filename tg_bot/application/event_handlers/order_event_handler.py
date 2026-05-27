# Tg_bot/application/event_handlers/order_event_handler.py
"""
Event Handlers For Order Domain.

These handlers process domain events asynchronously.
They update read models, send notifications, etc.
"""
import logging
from typing import Any, Awaitable, Callable, Optional, cast

from tg_bot.domain.events import (
    DomainEvent,
    OrderCancelled,
    OrderCreated,
    OrderDeliveryUpdated,
    OrderItemAdded,
    OrderItemRemoved,
    OrderPaymentUrlSet,
    OrderStatusChanged,
    deserialize_event,
    serialize_event,
)
from tg_bot.infrastructure.metrics import (
    kojo_active_users,
    kojo_order_value_sum,
    kojo_orders_total,
)
from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


def _tenant_id() -> str:
    tenant = get_current_tenant()
    return tenant.bot_id if tenant else "default"


class OrderEventHandler:
    """
    Handles order domain events.

    In production, this would:
    - Update search indexes (Elasticsearch)
    - Send notifications (Telegram, Email)
    - Update analytics (stats, dashboards)
    - Trigger webhooks
    """

    def __init__(self, dlq: Optional[Any] = None) -> None:
        self._dlq = dlq
        self._handlers = {
            OrderCreated: self._handle_order_created,
            OrderStatusChanged: self._handle_status_changed,
            OrderDeliveryUpdated: self._handle_delivery_updated,
            OrderPaymentUrlSet: self._handle_payment_url_set,
            OrderCancelled: self._handle_cancelled,
            OrderItemAdded: self._handle_item_added,
            OrderItemRemoved: self._handle_item_removed,
        }

    async def handle_event_from_dlq(self, item: dict[str, Any]) -> bool:
        """Re-process a failed event from the DLQ. Returns True on success.
        Calls the handler directly (not via handle()) to avoid re-adding to DLQ on failure."""
        event_type = item.get("event_type", "")
        data = item.get("data", {})
        if not data:
            logger.warning("DLQ Handler: No Event Data To Reprocess")
            return False
        try:
            event = deserialize_event(data)
            handler = self._handlers.get(type(event))
            if handler:
                await cast(Callable[[DomainEvent], Awaitable[Any]], handler)(event)
                return True
            logger.warning("DLQ handler: no handler for event type %s", event_type)
            return False
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error("DLQ reprocess failed for %s: %s", event_type, e)
            return False

    async def handle(self, event: DomainEvent) -> None:
        """Dispatch event to appropriate handler."""
        handler = self._handlers.get(type(event))
        if handler:
            try:
                await handler(event)  # type: ignore[operator]
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Error handling {event.event_type}: {e}")
                if self._dlq is not None:
                    self._dlq.put({
                        "event_type": event.event_type,
                        "event_id": event.event_id,
                        "data": serialize_event(event),
                        "error": str(e),
                    })
        else:
            logger.warning(f"No handler for event type: {type(event).__name__}")

    async def _handle_order_created(self, event: OrderCreated) -> None:
        """Handle order creation."""
        tid = _tenant_id()
        logger.info(
            "Order %s created by user %s. Total: %s",
            event.order_id, event.user_id, event.total_amount,
        )
        kojo_orders_total.labels(status="created", tenant_id=tid).inc()
        kojo_order_value_sum.observe(event.total_amount)
        kojo_active_users.labels(tenant_id=tid).set(1)
        logger.debug("Event OrderCreated %s — search index update: not configured", event.order_id)
        logger.debug("Event OrderCreated %s — user confirmation: not configured", event.order_id)

    async def _handle_status_changed(self, event: OrderStatusChanged) -> None:
        """Handle status change."""
        tid = _tenant_id()
        logger.info(
            "Order %s: %s -> %s",
            event.order_id, event.from_status, event.to_status,
        )
        kojo_orders_total.labels(status=event.to_status, tenant_id=tid).inc()
        logger.debug("Event OrderStatusChanged %s — user notification: not configured", event.order_id)
        logger.debug("Event OrderStatusChanged %s — admin dashboard: not configured", event.order_id)

    async def _handle_delivery_updated(self, event: OrderDeliveryUpdated) -> None:
        """Handle delivery info update."""
        logger.info(
            f"🚚 [Event] Order {event.order_id} delivery updated: {event.delivery_type}"
        )
        logger.debug("Event OrderDeliveryUpdated %s — shipping integration: not configured", event.order_id)

    async def _handle_payment_url_set(self, event: OrderPaymentUrlSet) -> None:
        """Handle payment URL being set."""
        logger.info(
            f"💳 [Event] Order {event.order_id} payment URL set"
        )
        logger.debug("Event OrderPaymentUrlSet %s — send payment link: not configured", event.order_id)

    async def _handle_cancelled(self, event: OrderCancelled) -> None:
        """Handle order cancellation."""
        tid = _tenant_id()
        logger.info(
            "Order %s cancelled. Reason: %s", event.order_id, event.reason,
        )
        kojo_orders_total.labels(status="cancelled", tenant_id=tid).inc()
        logger.debug("Event OrderCancelled %s — inventory release: not configured", event.order_id)
        logger.debug("Event OrderCancelled %s — cancellation notification: not configured", event.order_id)

    async def _handle_item_added(self, event: OrderItemAdded) -> None:
        """Handle item added to order."""
        logger.debug(
            f"➕ [Event] Item {event.product_id} added to order {event.order_id}"
        )

    async def _handle_item_removed(self, event: OrderItemRemoved) -> None:
        """Handle item removed from order."""
        logger.debug(
            f"➖ [Event] Item {event.product_id} removed from order {event.order_id}"
        )


def create_order_event_handler() -> OrderEventHandler:
    """Factory: создаёт свежий экземпляр без глобального состояния."""
    return OrderEventHandler()


__all__ = [
    'OrderEventHandler',
    'create_order_event_handler',
    'EventHandler',
]
