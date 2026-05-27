"""Tests for domain events."""
from tg_bot.domain.events import OrderCreated, OrderStatusChanged, deserialize_event, serialize_event


class TestDomainEvent:
    def test_order_created_minimal(self) -> None:
        event = OrderCreated(order_id=1, user_id=123, items=[], total_amount=1500.0)
        assert event.order_id == 1
        assert event.user_id == 123
        assert event.total_amount == 1500.0
        assert event.event_type == "OrderCreated"

    def test_order_status_changed(self) -> None:
        event = OrderStatusChanged(order_id=1, from_status="Принят", to_status="Оплачен")
        assert event.from_status == "Принят"
        assert event.to_status == "Оплачен"
        assert event.event_type == "OrderStatusChanged"


class TestSerializeDeserialize:
    def test_cycle(self) -> None:
        event = OrderCreated(order_id=1, user_id=123, items=[{"product_id": 1, "quantity": 2}], total_amount=1500.0)
        serialized = serialize_event(event)
        assert serialized['event_type'] == "OrderCreated"

        deserialized = deserialize_event(serialized)
        assert deserialized.order_id == 1
        assert deserialized.user_id == 123
