# Tg_bot/infrastructure/event_store.py
"""
Event Store Implementation For Event Sourcing.

Uses PostgreSQL for persistent storage of domain events.
"""
import logging
from types import SimpleNamespace
from typing import Any, List, Optional, Union

import asyncpg

from tg_bot.domain.events import (
    DomainEvent,
    deserialize_event,
    serialize_event,
)

logger = logging.getLogger(__name__)


class EventStoreError(Exception):
    """Base exception for event store errors."""
    pass


class EventStore:
    """
    PostgreSQL-based event store for order event sourcing.

    # WARNING: EventStore uses raw pool.acquire() — no tenant context.
    # This is a system-level RLS bypass. Do not propagate data from here
    # into per-tenant tables without setting app.current_tenant first.

    Schema:
        CREATE TABLE event_store (
            id BIGSERIAL PRIMARY KEY,
            stream_id VARCHAR(255) NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL,
            version INT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB
        );

        CREATE INDEX idx_event_store_stream ON event_store(stream_id, version);
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        stream_id: str,
        events: Union[DomainEvent, List[DomainEvent]],
        metadata: Optional[dict[str, object]] = None
    ) -> int:
        """
        Append event(s) to a stream.
        Accepts a single DomainEvent or a list.
        Returns the version number of the last appended event.
        """
        if isinstance(events, DomainEvent):
            events = [events]

        if not events:
            return 0

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Get Current Version
                current_version = await conn.fetchval(
                    "SELECT COALESCE(MAX(version), 0) FROM event_store WHERE stream_id = $1",
                    stream_id
                )

                for i, event in enumerate(events):
                    version = current_version + i + 1
                    payload = serialize_event(event)

                    await conn.execute(
                        """
                        INSERT INTO event_store (stream_id, event_type, payload, version, metadata)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        stream_id,
                        event.event_type,
                        payload,
                        version,
                        metadata
                    )

                return int(current_version + len(events))

    async def get_stream(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None
    ) -> List[DomainEvent]:
        """Get all events for a stream in order."""
        async with self._pool.acquire() as conn:
            if to_version:
                rows = await conn.fetch(
                    """
                    SELECT payload FROM event_store
                    WHERE stream_id = $1 AND version > $2 AND version <= $3
                    ORDER BY version
                    """,
                    stream_id, from_version, to_version
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT payload FROM event_store
                    WHERE stream_id = $1 AND version > $2
                    ORDER BY version
                    """,
                    stream_id, from_version
                )

            return [deserialize_event(dict(row['payload'])) for row in rows]

    async def get_stream_count(self, stream_id: str) -> int:
        """Get total event count for a stream."""
        from typing import cast

        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM event_store WHERE stream_id = $1",
                stream_id
            )
            return cast(int, result)

    async def get_latest_version(self, stream_id: str) -> int:
        """Get the latest version number for a stream."""
        from typing import cast

        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) FROM event_store WHERE stream_id = $1",
                stream_id
            )
            return cast(int, result)

    async def get_events_by_type(
        self,
        event_type: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[DomainEvent]:
        """Get events of a specific type (for projections)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT payload FROM event_store
                WHERE event_type = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                event_type, limit, offset
            )

            return [deserialize_event(dict(row['payload'])) for row in rows]

    async def get_all_streams(self) -> List[str]:
        """Get all unique stream IDs."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT stream_id FROM event_store ORDER BY stream_id"
            )
            return [row['stream_id'] for row in rows]

    async def get_events(self, stream_id: str) -> List[DomainEvent]:
        """Get all events for a stream (alias for get_stream with defaults)."""
        return await self.get_stream(stream_id)

    async def replay(self, stream_id: str) -> List[Any]:
        """Replay all events for a stream, returning objects with .version."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT payload, version FROM event_store WHERE stream_id = $1 ORDER BY version",
                stream_id
            )
        result: List[Any] = []
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, dict):
                event = deserialize_event(payload)
            else:
                event = deserialize_event(dict(payload))
            result.append(
                SimpleNamespace(event_type=event.event_type, version=row["version"])
            )
        return result

    async def flush(self) -> None:
        """Flush WAL: ensures all pending events are committed.
        For PostgreSQL-backed store this is a no-op (each append is transactional).
        Kept for interface compatibility with §3.1 graceful shutdown."""
        logger.debug("Eventstore: Flush Called (no-op For Postgresql Backend)")

    async def delete_stream(self, stream_id: str) -> None:
        """Delete all events for a stream (use with caution)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM event_store WHERE stream_id = $1",
                stream_id
            )
            logger.warning(f"Deleted all events for stream: {stream_id}")


__all__ = [
    'EventStore',
    'EventStoreError',
]
