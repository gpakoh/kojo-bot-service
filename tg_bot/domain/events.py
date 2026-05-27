# Tg_bot/domain/events.py
"""
Domain Events For Event Sourcing.

All events are immutable (frozen=True) and contain all data needed to reconstruct state.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""
    event_id: str = field(default_factory=lambda: f"{datetime.now(timezone.utc).timestamp()}")
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        return self.__class__.__name__


@dataclass(frozen=True)
class OrderCreated(DomainEvent):
    """Event emitted when an order is created."""
    order_id: int = field(default=0)
    user_id: int = field(default=0)
    items: list[dict[str, object]] = field(default_factory=list)
    delivery_type: str = field(default="")
    delivery_address: Optional[str] = field(default=None)
    delivery_price: float = field(default=0.0)
    is_gift: bool = field(default=False)
    gift_comment: Optional[str] = field(default=None)
    total_amount: float = field(default=0.0)


@dataclass(frozen=True)
class OrderStatusChanged(DomainEvent):
    """Event emitted when order status changes."""
    order_id: int = field(default=0)
    from_status: str = field(default="")
    to_status: str = field(default="")
    reason: Optional[str] = field(default=None)


@dataclass(frozen=True)
class OrderDeliveryUpdated(DomainEvent):
    """Event emitted when delivery info is updated."""
    order_id: int = field(default=0)
    delivery_type: str = field(default="")
    delivery_address: Optional[str] = field(default=None)
    delivery_price: float = field(default=0.0)
    is_gift: bool = field(default=False)
    gift_comment: Optional[str] = field(default=None)


@dataclass(frozen=True)
class OrderPaymentUrlSet(DomainEvent):
    """Event emitted when payment URL is set."""
    order_id: int = field(default=0)
    payment_url: str = field(default="")


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """Event emitted when order is cancelled."""
    order_id: int = field(default=0)
    reason: str = field(default="")


@dataclass(frozen=True)
class OrderItemAdded(DomainEvent):
    """Event emitted when item is added to order."""
    order_id: int = field(default=0)
    product_id: int = field(default=0)
    quantity: int = field(default=0)
    price: float = field(default=0.0)
    name: str = field(default="")


@dataclass(frozen=True)
class OrderItemRemoved(DomainEvent):
    """Event emitted when item is removed from order."""
    order_id: int = field(default=0)
    product_id: int = field(default=0)


# Event Type To Class Mapping
EVENT_TYPES = {
    'OrderCreated': OrderCreated,
    'OrderStatusChanged': OrderStatusChanged,
    'OrderDeliveryUpdated': OrderDeliveryUpdated,
    'OrderPaymentUrlSet': OrderPaymentUrlSet,
    'OrderCancelled': OrderCancelled,
    'OrderItemAdded': OrderItemAdded,
    'OrderItemRemoved': OrderItemRemoved,
}


def serialize_event(event: DomainEvent) -> dict[str, object]:
    """Serialize event to dict for storage."""
    data: dict[str, object] = {
        'event_type': event.event_type,
        'event_id': event.event_id,
        'occurred_at': event.occurred_at.isoformat(),
    }

    # Add Event-specific Fields
    for key, value in event.__dict__.items():
        if key.startswith('_'):
            continue
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, (list, dict)):
            data[key] = json.dumps(value, default=str)
        else:
            data[key] = value

    return data


def deserialize_event(data: dict[str, object]) -> DomainEvent:
    """Deserialize event from dict."""
    event_type = data.get('event_type')
    if not event_type or not isinstance(event_type, str):
        raise ValueError("Missing event_type in event data")
    cls = EVENT_TYPES.get(event_type)

    if not cls:
        raise ValueError(f"Unknown event type: {event_type}")

    # Parse Datetime Fields
    kwargs: dict[str, object] = {}
    for key, value in data.items():
        if key == 'event_type':
            continue
        if 'at' in key.lower() and isinstance(value, str):
            kwargs[key] = datetime.fromisoformat(value)
        elif key == 'items' and isinstance(value, str):
            kwargs[key] = json.loads(value)
        else:
            kwargs[key] = value

    event: DomainEvent = cls(**kwargs)
    return event


__all__ = [
    'DomainEvent',
    'OrderCreated',
    'OrderStatusChanged',
    'OrderDeliveryUpdated',
    'OrderPaymentUrlSet',
    'OrderCancelled',
    'OrderItemAdded',
    'OrderItemRemoved',
    'serialize_event',
    'deserialize_event',
    'EVENT_TYPES',
]
