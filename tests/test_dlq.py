"""Integration tests for DeadLetterQueue."""
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tg_bot.infrastructure.dlq import DeadLetterQueue


class TestDeadLetterQueue:
    @pytest.fixture
    def dlq(self) -> DeadLetterQueue:
        return DeadLetterQueue()

    def test_put_increases_size(self, dlq) -> Any:
        dlq.put({"event": "test"})
        assert len(dlq._queue) == 1

    def test_put_logs_warning(self, dlq, caplog) -> Any:
        import logging
        with caplog.at_level(logging.WARNING):
            dlq.put({"event": "test"})
        assert "DLQ: item added" in caplog.text

    @pytest.mark.asyncio
    async def test_drain_with_handler_processes_all(self, dlq) -> Any:
        dlq.put({"id": 1})
        dlq.put({"id": 2})

        handler = AsyncMock(return_value=True)
        dlq.set_handler(handler)

        await dlq.drain(timeout=1.0)
        assert handler.await_count == 2
        assert len(dlq._queue) == 0

    @pytest.mark.asyncio
    async def test_drain_handler_false_stops(self, dlq) -> Any:
        dlq.put({"id": 1})
        dlq.put({"id": 2})

        handler = AsyncMock(return_value=False)
        dlq.set_handler(handler)

        await dlq.drain(timeout=1.0)
        assert handler.await_count == 1
        # Items Preserved For Later Reprocess
        assert len(dlq._queue) == 2

    @pytest.mark.asyncio
    async def test_drain_no_handler_clears(self, dlq, caplog) -> Any:
        import logging
        dlq.put({"id": 1})
        with caplog.at_level(logging.INFO):
            await dlq.drain(timeout=1.0)
        assert len(dlq._queue) == 0
        assert "no handler set" in caplog.text

    @pytest.mark.asyncio
    async def test_drain_exception_logs_error(self, dlq, caplog) -> Any:
        import logging
        dlq.put({"id": 1})

        handler = AsyncMock(side_effect=RuntimeError("boom"))
        dlq.set_handler(handler)

        with caplog.at_level(logging.ERROR):
            await dlq.drain(timeout=1.0)
        assert "drain failed" in caplog.text
        # Item Preserved For Later Reprocess
        assert len(dlq._queue) == 1
