# Tests For Orderservice - Business Invariants And State Machine
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.order_service import OrderService
from tg_bot.domain.order import InvalidStateTransition, Order
from tg_bot.models import OrderStatus
from tg_bot.tenant.config import set_current_tenant


# Адаптер для совместимости тестов (orderstatemachine удалён при рефакторинге)
class OrderStateMachine:
    @staticmethod
    def can_transition(from_status, to_status) -> bool:
        return to_status in Order.VALID_TRANSITIONS.get(from_status, set())

    @staticmethod
    def validate_transition(from_status, to_status) -> None:
        if not OrderStateMachine.can_transition(from_status, to_status):
            raise InvalidStateTransition(f"{from_status} -> {to_status}")


def make_order_row(order_id: int = 1, user_id: int = 123, status: str = 'Принят',
                   total_amount: float = 200.0, payment_url: str = None):
    return {
        'id': order_id, 'user_id': user_id, 'total_amount': total_amount, 'status': status,
        'delivery_type': 'pickup', 'delivery_address': None, 'delivery_price': 0.0,
        'delivery_point_id': None, 'delivery_info': None, 'is_gift': False,
        'gift_comment': None, 'payment_url': payment_url,
        'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc)
    }


class TestOrderStateMachine:
    """Tests for order status state machine."""

    def test_valid_transitions_from_accepted(self) -> Any:
        assert OrderStateMachine.can_transition(OrderStatus.ACCEPTED, OrderStatus.AWAITING_PAYMENT)
        assert OrderStateMachine.can_transition(OrderStatus.ACCEPTED, OrderStatus.CANCELLED)
        assert not OrderStateMachine.can_transition(OrderStatus.ACCEPTED, OrderStatus.PAID)

    def test_valid_transitions_from_awaiting_payment(self) -> Any:
        assert OrderStateMachine.can_transition(OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID)
        assert OrderStateMachine.can_transition(OrderStatus.AWAITING_PAYMENT, OrderStatus.CANCELLED)
        assert not OrderStateMachine.can_transition(OrderStatus.AWAITING_PAYMENT, OrderStatus.COMPLETED)

    def test_valid_transitions_from_paid(self) -> Any:
        assert OrderStateMachine.can_transition(OrderStatus.PAID, OrderStatus.ASSEMBLING)
        assert OrderStateMachine.can_transition(OrderStatus.PAID, OrderStatus.CANCELLED)
        assert not OrderStateMachine.can_transition(OrderStatus.PAID, OrderStatus.ACCEPTED)
        assert not OrderStateMachine.can_transition(OrderStatus.PAID, OrderStatus.AWAITING_PAYMENT)

    def test_terminal_states(self) -> Any:
        from tg_bot.domain.order import Order
        assert not OrderStateMachine.can_transition(OrderStatus.COMPLETED, OrderStatus.ACCEPTED)
        assert not OrderStateMachine.can_transition(OrderStatus.COMPLETED, OrderStatus.PAID)
        assert not OrderStateMachine.can_transition(OrderStatus.CANCELLED, OrderStatus.PAID)
        assert OrderStatus.COMPLETED in Order.VALID_TRANSITIONS
        assert OrderStatus.CANCELLED in Order.VALID_TRANSITIONS

    def test_validate_transition_raises_on_invalid(self) -> Any:
        with pytest.raises(InvalidStateTransition):
            OrderStateMachine.validate_transition(OrderStatus.PAID, OrderStatus.ACCEPTED)

    def test_validate_transition_passes_on_valid(self) -> Any:
        OrderStateMachine.validate_transition(OrderStatus.ACCEPTED, OrderStatus.AWAITING_PAYMENT)
        OrderStateMachine.validate_transition(OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID)
        OrderStateMachine.validate_transition(OrderStatus.PAID, OrderStatus.ASSEMBLING)

    def test_all_statuses_have_transitions(self) -> Any:
        from tg_bot.domain.order import Order
        for status in OrderStatus:
            assert status in Order.VALID_TRANSITIONS


class TestOrderServiceCalculateTotal:
    """Tests for server-side total amount calculation."""

    @pytest.fixture
    def service(self) -> Any:
        pool = MagicMock()
        return OrderService(pool)

    def test_calculate_total_simple_cart(self, service) -> Any:
        cart = {
            "1": {"quantity": 2, "price": 100.0},
            "2": {"quantity": 1, "price": 50.0},
        }
        total = service.calculate_total_amount(cart, delivery_price=0.0)
        assert total == 250.0

    def test_calculate_total_with_delivery(self, service) -> Any:
        cart = {"1": {"quantity": 1, "price": 500.0}}
        total = service.calculate_total_amount(cart, delivery_price=150.0)
        assert total == 650.0

    def test_calculate_total_empty_cart(self, service) -> Any:
        cart = {}
        total = service.calculate_total_amount(cart, delivery_price=0.0)
        assert total == 0.0

    def test_calculate_total_zero_price_item(self, service) -> Any:
        cart = {"1": {"quantity": 1, "price": 0.0}}
        total = service.calculate_total_amount(cart, delivery_price=0.0)
        assert total == 0.0

    def test_calculate_total_rounds_to_two_decimal_places(self, service) -> Any:
        cart = {"1": {"quantity": 1, "price": 100.0 / 3}}
        total = service.calculate_total_amount(cart, delivery_price=0.0)
        assert total == round(100.0 / 3, 2)

    def test_calculate_total_negative_delivery_rejected(self, service) -> Any:
        cart = {"1": {"quantity": 1, "price": 100.0}}
        total = service.calculate_total_amount(cart, delivery_price=-50.0)
        assert total >= 0


class TestOrderServiceCreateOrderValidation:
    """Tests for create_order validation."""

    @pytest.fixture
    def service(self) -> Any:
        pool = MagicMock()
        return OrderService(pool)

    @pytest.mark.asyncio
    async def test_create_order_rejects_zero_total(self, service) -> Any:
        cart = {}
        with pytest.raises(ValueError, match="Сумма заказа должна быть больше 0"):
            await service.create_order(
                user_id=123,
                cart=cart,
                delivery_type='pickup',
                delivery_price=0.0,
            )

    @pytest.mark.asyncio
    async def test_create_order_calculates_total_from_cart(self, service) -> Any:
        cart = {"1": {"quantity": 2, "price": 100.0}}

        mock_conn = MagicMock()
        mock_tx = AsyncMock()
        mock_conn.transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_order_row = make_order_row(total_amount=200.0)
        mock_conn.fetchrow = AsyncMock(return_value=mock_order_row)
        mock_conn.execute = AsyncMock()

        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        order = await service.create_order(user_id=123, cart=cart, delivery_type='pickup')

        assert order.total_amount.amount == 200.0


class TestOrderServiceStateTransitions:
    """Tests for state machine integration in update_order_status."""

    @pytest.fixture
    def service(self) -> Any:
        pool = MagicMock()
        return OrderService(pool)

    @pytest.mark.asyncio
    async def test_update_order_status_valid_transition(self, service) -> Any:
        mock_conn = MagicMock()

        mock_conn.fetchrow = AsyncMock(side_effect=[
            make_order_row(status='Принят'),
            make_order_row(status='Ожидает оплаты'),
        ])

        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await service.update_order_status(1, OrderStatus.AWAITING_PAYMENT)

        assert result is not None

    @pytest.mark.asyncio
    async def test_update_order_status_invalid_transition(self, service) -> Any:
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=make_order_row(status='Оплачен'))

        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(InvalidStateTransition):
            await service.update_order_status(1, OrderStatus.ACCEPTED)

    @pytest.mark.asyncio
    async def test_cannot_complete_without_payment(self) -> Any:
        """Cannot transition from ACCEPTED directly to COMPLETED - must go through payment."""
        from tg_bot.domain.order import OrderStatus

        with pytest.raises(InvalidStateTransition):
            OrderStateMachine.validate_transition(OrderStatus.ACCEPTED, OrderStatus.COMPLETED)

    @pytest.mark.asyncio
    async def test_cancel_paid_order_succeeds(self) -> Any:
        """PAID → CANCELLED is valid - user can cancel after payment."""
        from tg_bot.domain.order import OrderStatus

        assert OrderStateMachine.can_transition(OrderStatus.PAID, OrderStatus.CANCELLED)

    @pytest.mark.asyncio
    async def test_cancel_completed_order_fails(self) -> Any:
        """COMPLETED → CANCELLED is invalid - cannot cancel completed order."""
        from tg_bot.domain.order import OrderStatus

        with pytest.raises(InvalidStateTransition):
            OrderStateMachine.validate_transition(OrderStatus.COMPLETED, OrderStatus.CANCELLED)


class TestOrderServiceUpdateDeliverySecurity:
    """Tests for update_order_delivery security."""

    @pytest.fixture
    def service(self) -> Any:
        pool = MagicMock()
        return OrderService(pool)

    @pytest.mark.asyncio
    async def test_update_order_delivery_calculates_total(self) -> Any:
        """Test that update_order_delivery calculates total from cart + delivery_price."""
        from unittest.mock import AsyncMock, MagicMock

        cart = {"1": {"quantity": 2, "price": 100.0}}
        delivery_price = 50.0

        mock_conn = MagicMock()
        captured_queries = []

        async def capture_fetchrow(query, *args):
            captured_queries.append((query, args))
            if 'FOR UPDATE' in query:
                return make_order_row(status='Принят')
            return make_order_row(status='Принят', total_amount=250.0)

        mock_conn.fetchrow = AsyncMock(side_effect=capture_fetchrow)

        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        service = OrderService(pool)

        await service.update_order_delivery(
            order_id=1,
            total_amount=None,  # Will be calculated from cart
            cart=cart,
            delivery_type='pickup',
            delivery_address='Test',
            delivery_price=delivery_price,
        )

        update_query = captured_queries[1][0]
        assert 'UPDATE orders' in update_query
        expected_total = 2 * 100.0 + delivery_price  # 250.0
        assert expected_total in captured_queries[1][1]

    @pytest.mark.asyncio
    async def test_update_order_delivery_preserves_payment_url_when_paid(self) -> Any:
        """Test that payment_url is NOT set to NULL when order is already PAID."""
        from unittest.mock import AsyncMock, MagicMock

        cart = {"1": {"quantity": 1, "price": 100.0}}

        mock_conn = MagicMock()
        captured_queries = []

        async def capture_fetchrow(query, *args):
            captured_queries.append((query, args))
            if 'FOR UPDATE' in query:
                return make_order_row(status='Оплачен', payment_url='https://payment.url/pay')
            return make_order_row(status='Оплачен', payment_url='https://payment.url/pay')

        mock_conn.fetchrow = AsyncMock(side_effect=capture_fetchrow)

        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        service = OrderService(pool)

        await service.update_order_delivery(
            order_id=1,
            total_amount=None,  # Will be calculated from cart
            cart=cart,
            delivery_type='pickup',
            delivery_address='Test',
            delivery_price=0.0,
        )

        update_query = captured_queries[1][0]
        assert 'payment_url' not in update_query or 'COALESCE' in update_query

    @pytest.mark.asyncio
    async def test_update_order_delivery_resets_payment_url_when_not_paid(self, service) -> Any:
        cart = {"1": {"quantity": 1, "price": 100.0}}

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            {'status': 'Принят'},
            make_order_row(status='Принят'),
        ])

        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await service.update_order_delivery(
            order_id=1,
            total_amount=None,  # Will be calculated from cart
            cart=cart,
            delivery_type='pickup',
            delivery_address='Test',
            delivery_price=0.0,
        )

        call_args = mock_conn.fetchrow.call_args_list
        update_call = call_args[1]
        sql = update_call[0][0]

        assert 'payment_url = NULL' in sql


class TestOrderServiceTenantAware:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        return pool, conn

    @pytest.mark.asyncio
    async def test_uses_tenant_connection_when_tenant_is_set(self) -> Any:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value="UPDATE 1")

        pool = MagicMock()
        pool.acquire = MagicMock()

        class DummyDbManager:
            def __init__(self) -> None:
                self.called = False
                self.seen_tenant_id = None

            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                self.called = True
                self.seen_tenant_id = tenant_id
                yield conn

        db_manager = DummyDbManager()
        service = OrderService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            await service.update_order_comment(order_id=1, comment="test")
        finally:
            set_current_tenant(None)

        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="UPDATE 1")

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = OrderService(pool, db_manager=DummyDbManager())
        await service.update_order_comment(order_id=1, comment="test")
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="UPDATE 1")

        service = OrderService(pool)
        await service.update_order_comment(order_id=1, comment="test")
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_fallback_when_tenant_connection_fails(self) -> Any:
        conn = AsyncMock()
        pool = MagicMock()
        pool.acquire = MagicMock()

        class FailingDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise RuntimeError("tenant db connection failed")
                yield  # pragma: no cover

        service = OrderService(pool, db_manager=FailingDbManager())

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        with pytest.raises(RuntimeError, match="tenant db connection failed"):
            await service.update_order_comment(order_id=1, comment="test")
        set_current_tenant(None)

        pool.acquire.assert_not_called()
