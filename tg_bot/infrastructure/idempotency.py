import json
import logging
from datetime import timedelta
from typing import Any, Optional, cast

logger = logging.getLogger(__name__)


class IdempotencyStore:
    """Redis-backed idempotency for order/payment operations (§3.3 manifest).

    Gracefully falls back to no-op when redis_client is None (Redis unavailable).
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client
        self._ttl = int(timedelta(hours=24).total_seconds())

    def _key(self, scope: str, idempotency_key: str) -> str:
        return f"idempotency:{scope}:{idempotency_key}"

    async def check(self, scope: str, idempotency_key: str) -> Optional[dict[str, Any]]:
        """Return cached result if key exists, else None."""
        if not self._redis:
            return None
        key = self._key(scope, idempotency_key)
        raw = await self._redis.get(key)
        if raw:
            logger.info("Idempotency hit: %s/%s", scope, idempotency_key)
            return cast(dict[str, Any], json.loads(raw))
        return None

    async def start(self, scope: str, idempotency_key: str) -> None:
        """Mark operation as in-progress to block duplicates."""
        if not self._redis:
            return
        key = self._key(scope, idempotency_key)
        await self._redis.setex(key, self._ttl, json.dumps({"status": "processing"}))

    async def complete(self, scope: str, idempotency_key: str, result: dict[str, Any]) -> None:
        """Store final result for 24h."""
        if not self._redis:
            return
        key = self._key(scope, idempotency_key)
        await self._redis.setex(key, self._ttl, json.dumps(result))
