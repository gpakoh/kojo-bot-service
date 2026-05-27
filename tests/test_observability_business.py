"""Tests for business metrics integration in event handlers."""
from typing import Any
from unittest.mock import patch

import pytest

from tg_bot.application.event_handlers.order_event_handler import OrderEventHandler
from tg_bot.domain.events import OrderCancelled, OrderCreated, OrderStatusChanged


class TestBusinessMetrics:
    @pytest.fixture
    def handler(self) -> OrderEventHandler:
        return OrderEventHandler()

    @pytest.mark.asyncio
    async def test_order_created_increments_orders_total(self, handler: OrderEventHandler) -> Any:
        with patch('tg_bot.application.event_handlers.order_event_handler.kojo_orders_total') as mock_total:
            with patch('tg_bot.application.event_handlers.order_event_handler.get_current_tenant', return_value=None):
                event = OrderCreated(order_id=1, user_id=123, items=[], total_amount=100.0)
                await handler._handle_order_created(event)
                mock_total.labels.assert_called_with(status="created", tenant_id="default")
                mock_total.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_order_created_observes_order_value(self, handler: OrderEventHandler) -> Any:
        with patch('tg_bot.application.event_handlers.order_event_handler.kojo_order_value_sum') as mock_sum:
            event = OrderCreated(order_id=1, user_id=123, items=[], total_amount=250.0)
            await handler._handle_order_created(event)
            mock_sum.observe.assert_called_with(250.0)

    @pytest.mark.asyncio
    async def test_order_created_sets_active_users(self, handler: OrderEventHandler) -> Any:
        with patch('tg_bot.application.event_handlers.order_event_handler.kojo_active_users') as mock_gauge:
            with patch('tg_bot.application.event_handlers.order_event_handler.get_current_tenant', return_value=None):
                event = OrderCreated(order_id=1, user_id=456, items=[], total_amount=100.0)
                await handler._handle_order_created(event)
                mock_gauge.labels.assert_called_with(tenant_id="default")
                mock_gauge.labels.return_value.set.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_status_changed_increments_orders_total(self, handler: OrderEventHandler) -> Any:
        with patch('tg_bot.application.event_handlers.order_event_handler.kojo_orders_total') as mock_total:
            with patch('tg_bot.application.event_handlers.order_event_handler.get_current_tenant', return_value=None):
                event = OrderStatusChanged(order_id=1, from_status="Принят", to_status="Оплачен")
                await handler._handle_status_changed(event)
                mock_total.labels.assert_called_with(status="Оплачен", tenant_id="default")
                mock_total.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_increments_orders_total(self, handler: OrderEventHandler) -> Any:
        with patch('tg_bot.application.event_handlers.order_event_handler.kojo_orders_total') as mock_total:
            with patch('tg_bot.application.event_handlers.order_event_handler.get_current_tenant', return_value=None):
                event = OrderCancelled(order_id=1, reason="Customer request")
                await handler._handle_cancelled(event)
                mock_total.labels.assert_called_with(status="cancelled", tenant_id="default")
                mock_total.labels.return_value.inc.assert_called_once()
