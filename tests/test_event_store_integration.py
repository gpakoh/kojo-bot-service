"""Integration tests for EventStore with PostgreSQL."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.domain.events import OrderCreated
from tg_bot.infrastructure.event_store import EventStore


class TestEventStoreIntegration:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=0)  # No existing events (version 0)
        conn.execute = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool

    @pytest.fixture
    def store(self, mock_pool) -> EventStore:
        return EventStore(pool=mock_pool)

    @pytest.mark.asyncio
    async def test_append_event(self, store, mock_pool) -> Any:
        event = OrderCreated(order_id=1, user_id=123, items=[], total_amount=100.0)
        event_id = await store.append("order-1", event)
        assert event_id == 1

    @pytest.mark.asyncio
    async def test_get_events_returns_list(self, store, mock_pool) -> Any:
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[
            {"payload": {"event_type": "OrderCreated", "order_id": 1}, "version": 1, "event_type": "OrderCreated"}
        ])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        events = await store.get_events("order-1")
        assert len(events) == 1
        assert events[0].event_type == "OrderCreated"

    @pytest.mark.asyncio
    async def test_replay_returns_events_ordered(self, store, mock_pool) -> Any:
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[
            {"payload": {"event_type": "OrderCreated"}, "version": 1},
            {"payload": {"event_type": "OrderStatusChanged"}, "version": 2},
        ])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        events = await store.replay("order-1")
        assert len(events) == 2
        assert events[0].version == 1
        assert events[1].version == 2

    @pytest.mark.asyncio
    async def test_flush_is_noop(self, store) -> Any:
        # Should Not Raise
        await store.flush()
