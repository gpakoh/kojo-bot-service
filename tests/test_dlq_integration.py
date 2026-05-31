"""Tests for DLQ infrastructure (§3.4 manifest)."""
from typing import Any

import pytest

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
        assert result == 2  # Two Succeeded
        assert len(dlq) == 1  # One Failed

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

    @pytest.mark.asyncio
    async def test_drain_timeout_handler_exception(self, dlq: DeadLetterQueue) -> None:
        async def handler(item: dict[str, Any]) -> bool:
            raise RuntimeError("boom")

        dlq.set_handler(handler)
        dlq.put({"event_type": "a"})

        await dlq.drain(timeout=5.0)
        assert len(dlq) == 1
