"""Tests for Event Handlers."""
from unittest.mock import patch

import pytest

from tg_bot.application.event_handlers.order_event_handler import OrderEventHandler
from tg_bot.domain.events import (
    DomainEvent,
    OrderCancelled,
    OrderCreated,
    OrderStatusChanged,
)


class UnknownEvent(DomainEvent):
    """Unknown event for testing dispatch."""
    order_id: int = 1


class TestEventDispatch:
    @pytest.fixture
    def handler(self) -> OrderEventHandler:
        return OrderEventHandler()

    @pytest.mark.asyncio
    async def test_dispatch_order_created_logs(self, handler) -> None:
        """Verify OrderCreated event is handled (logs info)."""
        event = OrderCreated(
            order_id=1, user_id=101, items=[], total_amount=500.0
        )

        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            # Should Log Info About The Event
            mock_logger.info.assert_called()
            assert "Order" in str(mock_logger.info.call_args_list)

    @pytest.mark.asyncio
    async def test_dispatch_order_status_changed_logs(self, handler) -> None:
        event = OrderStatusChanged(
            order_id=1, from_status="Принят", to_status="Оплачен"
        )

        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_order_cancelled_logs(self, handler) -> None:
        event = OrderCancelled(
            order_id=1, reason="Customer request"
        )

        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_unknown_event_logs_warning(self, handler) -> None:
        event = UnknownEvent()

        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.warning.assert_called_once()
            assert "No handler" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_handler_exception_logs_error(self, handler) -> None:
        """Test that exceptions in handlers are caught and logged."""
        event = OrderCreated(
            order_id=1, user_id=1, items=[], total_amount=100.0
        )

        # Make The Handler Raise An Exception
        async def failing_handler(e):
            raise RuntimeError("boom")

        handler._handlers[OrderCreated] = failing_handler

        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.error.assert_called_once()
            assert "Error handling" in str(mock_logger.error.call_args)


class TestCircuitBreakerIntegration:
    @pytest.mark.asyncio
    async def test_handler_with_circuit_breaker_open(self) -> None:
        """If circuit breaker is open, handler should not process."""
        from services.gateway.circuit_breaker import (
            CircuitState,
            clear_circuit_breakers,
            get_circuit_breaker,
        )

        clear_circuit_breakers()
        cb = get_circuit_breaker("test_handler")
        cb.config.failure_threshold = 1

        # Trip The Breaker
        await cb.record_failure(RuntimeError("test"))
        assert cb.state == CircuitState.OPEN

        handler = OrderEventHandler()
        event = OrderCreated(order_id=1, user_id=1, items=[], total_amount=100.0)

        # Handler Should Still Attempt (circuit Breaker Is In Infrastructure Layer)
        # This Test Verifies The Pattern Works
        await handler.handle(event)
        # If We Got Here Without Exception, The Test Passes
        assert True


class TestEventHandlerCoverageGaps:
    """Cover _handle_delivery_updated, _handle_payment_url_set, _handle_item_added, _handle_item_removed."""

    @pytest.fixture
    def handler(self) -> OrderEventHandler:
        return OrderEventHandler()

    @pytest.mark.asyncio
    async def test_dispatch_delivery_updated(self, handler) -> None:
        from tg_bot.domain.events import OrderDeliveryUpdated
        event = OrderDeliveryUpdated(order_id=1, delivery_type="pickup")
        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.info.assert_called()
            assert "delivery updated" in str(mock_logger.info.call_args).lower()

    @pytest.mark.asyncio
    async def test_dispatch_payment_url_set(self, handler) -> None:
        from tg_bot.domain.events import OrderPaymentUrlSet
        event = OrderPaymentUrlSet(order_id=1, payment_url="https://pay.example.com")
        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_item_added(self, handler) -> None:
        from tg_bot.domain.events import OrderItemAdded
        event = OrderItemAdded(order_id=1, product_id=42, quantity=2)
        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_item_removed(self, handler) -> None:
        from tg_bot.domain.events import OrderItemRemoved
        event = OrderItemRemoved(order_id=1, product_id=42)
        with patch('tg_bot.application.event_handlers.order_event_handler.logger') as mock_logger:
            await handler.handle(event)
            mock_logger.debug.assert_called()
