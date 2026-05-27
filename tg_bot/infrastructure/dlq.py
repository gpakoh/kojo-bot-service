import asyncio
import json
import logging
import time
from datetime import timedelta
from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

DLQ_SCOPE = "dlq:failed_events"


class DeadLetterQueue:
    """DLQ for failed domain events. Supports Redis persistence and reprocess (§3.4 manifest)."""

    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._queue: list[dict[str, Any]] = []
        self._handler: Callable[[dict[str, Any]], Awaitable[bool]] | None = None
        self._redis = redis_client
        self._ttl = int(timedelta(days=7).total_seconds())

    def _redis_key(self, idx: int) -> str:
        return f"{DLQ_SCOPE}:{idx}"

    async def _load_from_redis(self) -> None:
        if not self._redis:
            return
        try:
            cursor = 0
            pattern = f"{DLQ_SCOPE}:*"
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern)
                for key in keys:
                    raw = await self._redis.get(key)
                    if raw:
                        self._queue.append(json.loads(raw))
                if cursor == 0:
                    break
            self._queue.sort(key=lambda x: x.get("_ts", 0))
            if self._queue:
                logger.info("DLQ: loaded %d items from Redis", len(self._queue))
        except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
            logger.warning("DLQ: failed to load from Redis, using in-memory only: %s", e)

    def set_handler(self, handler: Callable[[dict[str, Any]], Awaitable[bool]]) -> None:
        self._handler = handler

    def put(self, item: dict[str, Any]) -> None:
        item["_ts"] = item.get("_ts", time.time())
        item["_retries"] = item.get("_retries", 0)
        self._queue.append(item)
        logger.warning("DLQ: item added, queue size=%d", len(self._queue))

    async def reprocess(self, max_items: int = 0) -> int:
        """
        Reprocess failed events from the queue.
        Returns the number of successfully reprocessed items.
        """
        if not self._handler:
            logger.warning("DLQ: No Handler Set For Reprocess")
            return 0

        to_process = list(self._queue)
        if max_items > 0:
            to_process = to_process[:max_items]

        success_count = 0
        remaining: list[dict[str, Any]] = []

        for item in to_process:
            try:
                result = await self._handler(item)
                if result:
                    success_count += 1
                    if self._redis:
                        try:
                            idx = self._queue.index(item)
                            await self._redis.delete(self._redis_key(idx))
                        except (ValueError, Exception) as e:
                            logger.warning("[dlq] ValueError in Redis delete: %s", e)
                else:
                    item["_retries"] = item.get("_retries", 0) + 1
                    remaining.append(item)
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error("DLQ reprocess failed for item: %s", e)
                item["_retries"] = item.get("_retries", 0) + 1
                remaining.append(item)

        self._queue = [x for x in self._queue if x not in to_process]
        self._queue.extend(remaining)

        if success_count:
            logger.info("DLQ: reprocessed %d items successfully", success_count)
        return success_count

    async def drain(self, timeout: float = 10.0) -> None:
        """Attempt to re-process queued items before shutdown."""
        if not self._handler:
            logger.info("DLQ: no handler set, dropping %d items", len(self._queue))
            self._queue.clear()
            if self._redis:
                await self._clear_redis()
            return

        deadline = asyncio.get_event_loop().time() + timeout
        remaining: list[dict[str, Any]] = []
        while self._queue and asyncio.get_event_loop().time() < deadline:
            item = self._queue.pop(0)
            try:
                success = await self._handler(item)
                if not success:
                    remaining.append(item)
                    break
                if self._redis:
                    try:
                        await self._redis.delete(self._redis_key(len(remaining)))
                    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                        logger.warning("[dlq] drain error in Redis delete: %s", e)
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error("DLQ drain failed for item: %s", e)
                remaining.append(item)
                break

        self._queue = remaining + self._queue
        remaining_count = len(self._queue)
        if remaining_count:
            logger.error("DLQ: %d items remaining after drain timeout", remaining_count)
        else:
            self._queue.clear()
            if self._redis:
                await self._clear_redis()

    async def _clear_redis(self) -> None:
        if not self._redis:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=f"{DLQ_SCOPE}:*")
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
            logger.warning("DLQ: failed to clear Redis keys: %s", e)

    def __len__(self) -> int:
        return len(self._queue)
