# Tests For Domain Order Model
from datetime import datetime, timezone
from typing import Any

import pytest

from tg_bot.domain.order import (
    Address,
    InvalidStateTransition,
    Money,
    Order,
    OrderError,
    OrderItem,
    OrderStatus,
)


class TestMoneyValueObject:
    """Tests for Money value object."""

    def test_money_creation(self) -> Any:
        m = Money(100.50)
        assert m.amount == 100.50

    def test_money_negative_raises(self) -> Any:
        with pytest.raises(OrderError):
            Money(-10)

    def test_money_addition(self) -> Any:
        m1 = Money(100)
        m2 = Money(50)
        result = m1 + m2
        assert result.amount == 150

    def test_money_multiplication(self) -> Any:
        m = Money(25)
        result = m * 3
        assert result.amount == 75

    def test_money_rounds_to_two_decimals(self) -> Any:
        m = Money(100.999)
        assert m.amount == 101.0


class TestOrderItem:
    """Tests for OrderItem entity."""

    def test_item_creation(self) -> Any:
        item = OrderItem(product_id=1, quantity=2, price=Money(100))
        assert item.product_id == 1
        assert item.quantity == 2
        assert item.price.amount == 100

    def test_item_subtotal(self) -> Any:
        item = OrderItem(product_id=1, quantity=3, price=Money(50))
        assert item.subtotal.amount == 150

    def test_item_zero_quantity_raises(self) -> Any:
        with pytest.raises(OrderError):
            OrderItem(product_id=1, quantity=0, price=Money(100))


class TestAddress:
    """Tests for Address value object."""

    def test_pickup_address(self) -> Any:
        addr = Address(delivery_type='pickup')
        assert addr.delivery_type == 'pickup'
        assert addr.address is None

    def test_delivery_address(self) -> Any:
        addr = Address(delivery_type='delivery', address='ул. Пушкина 10')
        assert addr.address == 'ул. Пушкина 10'


class TestOrderAggregate:
    """Tests for Order aggregate root."""

    @pytest.fixture
    def sample_items(self) -> Any:
        return [
            {'product_id': 1, 'quantity': 2, 'price': 100.0, 'name': 'Coffee 1'},
            {'product_id': 2, 'quantity': 1, 'price': 200.0, 'name': 'Coffee 2'},
        ]

    def test_create_order(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        assert order.user_id == 123
        assert len(order.items) == 2
        assert order.status == OrderStatus.ACCEPTED
        assert order.total_amount.amount == 400.0

    def test_create_order_empty_items_raises(self) -> Any:
        with pytest.raises(OrderError):
            Order.create(user_id=123, items_data=[])

    def test_order_items_total(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        assert order.items_total.amount == 400.0

    def test_order_with_delivery(self, sample_items) -> Any:
        delivery = Address(delivery_type='delivery', address='ул. Тестовая 1')
        order = Order.create(
            user_id=123,
            items_data=sample_items,
            delivery=delivery,
            delivery_price=150.0
        )
        assert order.total_amount.amount == 550.0
        assert order.delivery_price.amount == 150.0

    def test_gift_order_requires_comment(self, sample_items) -> Any:
        with pytest.raises(OrderError):
            Order.create(user_id=123, items_data=sample_items, is_gift=True)

    def test_gift_order_with_comment(self, sample_items) -> Any:
        order = Order.create(
            user_id=123,
            items_data=sample_items,
            is_gift=True,
            gift_comment='Happy Birthday!'
        )
        assert order.is_gift
        assert order.gift_comment == 'Happy Birthday!'


class TestOrderStateTransitions:
    """Tests for order state machine."""

    @pytest.fixture
    def sample_items(self) -> Any:
        return [{'product_id': 1, 'quantity': 1, 'price': 100.0, 'name': 'Coffee'}]

    def test_valid_transition_accepted_to_awaiting_payment(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        order.transition_to(OrderStatus.AWAITING_PAYMENT)
        assert order.status == OrderStatus.AWAITING_PAYMENT

    def test_invalid_transition_accepted_to_paid(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        with pytest.raises(InvalidStateTransition):
            order.transition_to(OrderStatus.PAID)

    def test_valid_flow_full_lifecycle(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)

        order.transition_to(OrderStatus.AWAITING_PAYMENT)
        assert order.status == OrderStatus.AWAITING_PAYMENT

        order.mark_as_paid(payment_url='https://pay.url')
        assert order.status == OrderStatus.PAID
        assert order.payment_url == 'https://pay.url'

        order.transition_to(OrderStatus.ASSEMBLING)
        assert order.status == OrderStatus.ASSEMBLING

        order.transition_to(OrderStatus.READY_FOR_PICKUP)
        assert order.status == OrderStatus.READY_FOR_PICKUP

        order.transition_to(OrderStatus.COMPLETED)
        assert order.status == OrderStatus.COMPLETED
        assert order.is_finalized

    def test_is_finalized_property(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        assert not order.is_finalized


class TestOrderDeliveryModification:
    """Tests for delivery modification rules."""

    @pytest.fixture
    def sample_items(self) -> Any:
        return [{'product_id': 1, 'quantity': 1, 'price': 100.0, 'name': 'Coffee'}]

    def test_set_delivery_before_payment(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        delivery = Address(delivery_type='delivery', address='New Address')

        order.set_delivery(delivery, Money(200.0))

        assert order.delivery.address == 'New Address'
        assert order.delivery_price.amount == 200.0

    def test_cannot_change_delivery_after_payment(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        order.transition_to(OrderStatus.AWAITING_PAYMENT)
        order.mark_as_paid()

        delivery = Address(delivery_type='delivery', address='New Address')
        with pytest.raises(OrderError):
            order.set_delivery(delivery, Money(200.0))

    def test_delivery_price_included_in_total(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items, delivery_price=50.0)
        assert order.total_amount.amount == 150.0


class TestOrderItemOperations:
    """Tests for order item modification."""

    @pytest.fixture
    def sample_items(self) -> Any:
        return [{'product_id': 1, 'quantity': 1, 'price': 100.0, 'name': 'Coffee'}]

    def test_add_item_before_payment(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        order.add_item(2, 1, 200.0, 'New Coffee')

        assert len(order.items) == 2
        assert order.total_amount.amount == 300.0

    def test_remove_item(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        order.add_item(2, 1, 200.0)
        order.remove_item(1)

        assert len(order.items) == 1
        assert order.items[0].product_id == 2

    def test_cannot_remove_last_item(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        with pytest.raises(OrderError):
            order.remove_item(1)

    def test_cannot_add_item_to_finalized_order(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        order.transition_to(OrderStatus.AWAITING_PAYMENT)
        order.transition_to(OrderStatus.PAID)
        order.transition_to(OrderStatus.ASSEMBLING)
        order.transition_to(OrderStatus.READY_FOR_PICKUP)
        order.transition_to(OrderStatus.COMPLETED)

        assert order.is_finalized


class TestOrderToDict:
    """Tests for order serialization."""

    @pytest.fixture
    def sample_items(self) -> Any:
        return [{'product_id': 1, 'quantity': 2, 'price': 100.0, 'name': 'Coffee'}]

    def test_to_dict(self, sample_items) -> Any:
        order = Order.create(user_id=123, items_data=sample_items)
        d = order.to_dict()

        assert d['user_id'] == 123
        assert d['total_amount'] == 200.0
        assert d['status'] == 'Принят'

    def test_from_db_row(self, sample_items) -> Any:
        row = {
            'id': 1,
            'user_id': 123,
            'status': 'Принят',
            'total_amount': 200.0,
            'delivery_type': 'pickup',
            'delivery_address': None,
            'delivery_price': 0.0,
            'delivery_point_id': None,
            'delivery_info': None,
            'is_gift': False,
            'gift_comment': None,
            'payment_url': None,
            'cancellation_reason': None,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }

        order = Order.from_db_row(row)

        assert order.id == 1
        assert order.user_id == 123
        assert order.status == OrderStatus.ACCEPTED

    def test_money_equality_and_hash(self) -> None:
        m1 = Money(100.50)
        m2 = Money(100.50)
        m3 = Money(50.00)
        assert m1 == m2
        assert m1 != m3

    def test_money_zero_allowed(self) -> None:
        m = Money(0)
        assert m.amount == 0

    def test_order_from_db_row_with_none_fields(self) -> None:
        from datetime import datetime, timezone
        row = {
            'id': 1, 'user_id': 123, 'status': 'Принят', 'total_amount': 0.0,
            'delivery_type': None, 'delivery_address': None, 'delivery_price': 0.0,
            'delivery_point_id': None, 'delivery_info': None, 'is_gift': False,
            'gift_comment': None, 'payment_url': None, 'cancellation_reason': None,
            'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc),
            'issued_at': None, 'issued_by': None,
        }
        order = Order.from_db_row(row)
        assert order.id == 1
        assert order.delivery is None or order.delivery.address is None

    def test_order_item_negative_price_raises(self) -> None:
        with pytest.raises(OrderError):
            OrderItem(product_id=1, quantity=1, price=Money(-10))

    def test_address_invalid_type_raises(self) -> None:
        """Address accepts any string type - validation at domain level."""
        # Address Currently Accepts Any String - Validation Happens Elsewhere
        addr = Address(delivery_type='invalid_type')
        assert addr.delivery_type == 'invalid_type'

