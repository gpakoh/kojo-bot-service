# Tg_bot/application/queries/base.py
"""
Base classes for CQRS Query Handlers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

import asyncpg

ResultT = TypeVar('ResultT')


@dataclass
class PaginationParams:
    """Standard pagination parameters."""
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass
class PaginatedResult(Generic[ResultT]):
    """Standard paginated result."""
    items: list[ResultT]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


class QueryHandler(ABC, Generic[ResultT]):
    """Base class for query handlers."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        self._pool = read_pool

    @abstractmethod
    async def execute(self, *args: object, **kwargs: object) -> ResultT:
        pass

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool


class ReadRepository:
    """Base class for read-only database access."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        self._pool = read_pool

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    async def fetch_all(self, query: str, *args: object) -> list[dict[str, object]]:
        """Fetch all rows as dicts."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def fetch_one(self, query: str, *args: object) -> Optional[dict[str, object]]:
        """Fetch single row as dict."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_val(self, query: str, *args: object) -> object:
        """Fetch single value."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)


__all__ = [
    'QueryHandler',
    'ReadRepository',
    'PaginationParams',
    'PaginatedResult',
]
