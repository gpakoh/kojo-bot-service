from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, AsyncIterator, Optional

import asyncpg

logger = logging.getLogger(__name__)


class UnitOfWork:
    """
    Unit of Work pattern - manages database transactions.
    Ensures connection pool safety and transaction integrity.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._conn: Optional[asyncpg.Connection] = None

    async def __aenter__(self) -> 'UnitOfWork':
        """Acquire connection and start transaction."""
        self._conn = await self._pool.acquire()
        self._transaction = self._conn.transaction()
        await self._transaction.start()
        logger.debug("Transaction Started")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Commit on success, rollback on error."""
        if exc_type is not None:
            await self._transaction.rollback()
            logger.debug("Transaction Rolled Back")
        else:
            await self._transaction.commit()
            logger.debug("Transaction Committed")

        await self._pool.release(self._conn)
        self._conn = None

    @property
    def connection(self) -> asyncpg.Connection:
        """Get the current connection."""
        if self._conn is None:
            raise RuntimeError("UnitOfWork not started. Use 'async with UoW()'")
        return self._conn

    async def execute(self, query: str, *args: Any) -> Any:
        """Execute a query within the transaction."""
        return await self._conn.execute(query, *args)  # type: ignore[union-attr]

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        """Fetch rows within the transaction."""
        return await self._conn.fetch(query, *args)  # type: ignore[union-attr,no-any-return]

    async def fetchrow(self, query: str, *args: Any) -> Optional[dict[str, Any]]:
        """Fetch single row within the transaction."""
        return await self._conn.fetchrow(query, *args)  # type: ignore[union-attr,no-any-return]


class UnitOfWorkFactory:
    """Factory for creating UnitOfWork instances."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[UnitOfWork]:
        """Create and provide UnitOfWork context."""
        async with UnitOfWork(self._pool) as uow:
            yield uow


def create_uow_factory(pool: asyncpg.Pool) -> UnitOfWorkFactory:
    """Create UnitOfWorkFactory."""
    return UnitOfWorkFactory(pool)
