"""Tests for DLQ integration (§3.4 manifest)."""
from typing import Any
from unittest.mock import patch

import pytest

from tg_bot.application.event_handlers.order_event_handler import OrderEventHandler
from tg_bot.domain.events import (
    OrderCreated,
    serialize_event,
)
from tg_bot.infrastructure.dlq import DeadLetterQueue


class TestDeadLetterQueueBasic:
    """Basic DLQ operations."""

    @pytest.fixture
    def dlq(self) -> DeadLetterQueue:
        return DeadLetterQueue()

    @pytest.mark.asyncio
    async def test_put_adds_item(self, dlq: DeadLetterQueue) -> None:
        dlq.put({"event_type": "test", "data": {}})
        assert len(dlq) == 1

    @pytest.mark.asyncio
    async def test_put_multiple_items(self, dlq: DeadLetterQueue) -> None:
        dlq.put({"event_type": "a"})
        dlq.put({"event_type": "b"})
        dlq.put({"event_type": "c"})
        assert len(dlq) == 3

    def test_len_empty(self, dlq: DeadLetterQueue) -> None:
        assert len(dlq) == 0

    @pytest.mark.asyncio
    async def test_reprocess_no_handler(self, dlq: DeadLetterQueue) -> None:
        dlq.put({"event_type": "test"})
        result = await dlq.reprocess()
        assert result == 0

    @pytest.mark.asyncio
    async def test_reprocess_success(self, dlq: DeadLetterQueue) -> None:
        async def handler(item: dict[str, Any]) -> bool:
            return True

        dlq.set_handler(handler)
        dlq.put({"event_type": "test", "data": {}})
        dlq.put({"event_type": "test2", "data": {}})

        result = await dlq.reprocess()
        assert result == 2
        assert len(dlq) == 0

    @pytest.mark.asyncio
    async def test_reprocess_partial_failure(self, dlq: DeadLetterQueue) -> None:
        results = [True, False, True]

        async def handler(item: dict[str, Any]) -> bool:
            return results.pop(0)

        dlq.set_handler(handler)
        dlq.put({"event_type": "a"})
        dlq.put({"event_type": "b"})
        dlq.put({"event_type": "c"})

        result = await dlq.reprocess()
        assert result == 2
        assert len(dlq) == 1

    @pytest.mark.asyncio
    async def test_reprocess_max_items(self, dlq: DeadLetterQueue) -> None:
        async def handler(item: dict[str, Any]) -> bool:
            return True

        dlq.set_handler(handler)
        dlq.put({"event_type": "a"})
        dlq.put({"event_type": "b"})
        dlq.put({"event_type": "c"})

        result = await dlq.reprocess(max_items=2)
        assert result == 2
        assert len(dlq) == 1


class TestDeadLetterQueueDrain:
    """DLQ drain behavior."""

    @pytest.mark.asyncio
    async def test_drain_with_handler(self) -> None:
        dlq = DeadLetterQueue()
        processed: list[str] = []

        async def handler(item: dict[str, Any]) -> bool:
            processed.append(item["event_type"])
            return True

        dlq.set_handler(handler)
        dlq.put({"event_type": "a"})
        dlq.put({"event_type": "b"})

        await dlq.drain(timeout=5.0)
        assert processed == ["a", "b"]
        assert len(dlq) == 0

    @pytest.mark.asyncio
    async def test_drain_without_handler_clears(self) -> None:
        dlq = DeadLetterQueue()
        dlq.put({"event_type": "a"})
        dlq.put({"event_type": "b"})

        await dlq.drain(timeout=5.0)
        assert len(dlq) == 0

    @pytest.mark.asyncio
    async def test_drain_handler_exception(self) -> None:
        dlq = DeadLetterQueue()

        async def handler(item: dict[str, Any]) -> bool:
            raise RuntimeError("boom")

        dlq.set_handler(handler)
        dlq.put({"event_type": "a"})

        await dlq.drain(timeout=5.0)
        # Item Stays In Queue After Exception — Drain Stops On Error
        assert len(dlq) == 1


class TestDLQEventIntegration:
    """DLQ integration with OrderEventHandler."""

    @pytest.fixture
    def dlq(self) -> DeadLetterQueue:
        return DeadLetterQueue()

    @pytest.mark.asyncio
    async def test_failed_event_goes_to_dlq(self, dlq: DeadLetterQueue) -> None:
        handler = OrderEventHandler(dlq=dlq)

        event = OrderCreated(order_id=1, user_id=101, items=[], total_amount=500.0)

        async def failing_handler(e):
            raise RuntimeError("processing error")

        handler._handlers[OrderCreated] = failing_handler

        await handler.handle(event)
        assert len(dlq) == 1

    @pytest.mark.asyncio
    async def test_dlq_reprocess_via_handler(self, dlq: DeadLetterQueue) -> None:
        handler = OrderEventHandler(dlq=dlq)
        processed_events: list[str] = []

        async def tracking_handler(e):
            processed_events.append(e.event_type)

        handler._handlers[OrderCreated] = tracking_handler

        event = OrderCreated(order_id=1, user_id=101, items=[], total_amount=500.0)
        data = serialize_event(event)

        dlq.put({
            "event_type": event.event_type,
            "event_id": event.event_id,
            "data": data,
            "error": "previous failure",
        })

        dlq.set_handler(lambda item: handler.handle_event_from_dlq(item))
        result = await dlq.reprocess()

        assert result == 1
        assert "OrderCreated" in processed_events
        assert len(dlq) == 0

    @pytest.mark.asyncio
    async def test_dlq_reprocess_still_fails(self, dlq: DeadLetterQueue) -> None:
        handler = OrderEventHandler(dlq=dlq)

        async def failing_handler(e):
            raise RuntimeError("still failing")

        handler._handlers[OrderCreated] = failing_handler

        event = OrderCreated(order_id=1, user_id=101, items=[], total_amount=500.0)
        data = serialize_event(event)

        dlq.put({
            "event_type": event.event_type,
            "event_id": event.event_id,
            "data": data,
            "error": "previous failure",
        })

        dlq.set_handler(lambda item: handler.handle_event_from_dlq(item))
        result = await dlq.reprocess()

        assert result == 0
        assert len(dlq) == 1  # Remaining because handler failed

    @pytest.mark.asyncio
    async def test_successful_event_not_sent_to_dlq(self, dlq: DeadLetterQueue) -> None:
        handler = OrderEventHandler(dlq=dlq)

        event = OrderCreated(order_id=1, user_id=101, items=[], total_amount=500.0)

        with patch('tg_bot.application.event_handlers.order_event_handler.logger'):
            await handler.handle(event)

        assert len(dlq) == 0

    @pytest.mark.asyncio
    async def test_no_dlq_no_crash(self) -> None:
        handler = OrderEventHandler(dlq=None)

        event = OrderCreated(order_id=1, user_id=101, items=[], total_amount=500.0)

        async def failing_handler(e):
            raise RuntimeError("error")

        handler._handlers[OrderCreated] = failing_handler

        with patch('tg_bot.application.event_handlers.order_event_handler.logger'):
            await handler.handle(event)
