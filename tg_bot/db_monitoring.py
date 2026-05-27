# Database Query Monitoring And Slow Query Logging
import logging
import os
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional

import asyncpg

logger = logging.getLogger(__name__)

SLOW_QUERY_THRESHOLD_MS = float(os.getenv("SLOW_QUERY_THRESHOLD_MS", "100"))


class QueryMonitor:
    """
    Monitors database queries and logs slow queries.
    Integrates with pg_stat_statements for query analysis.
    """

    _enabled = os.getenv("QUERY_MONITORING", "true").lower() == "true"
    _slow_threshold_ms = SLOW_QUERY_THRESHOLD_MS

    @classmethod
    async def init_extension(cls, pool: asyncpg.Pool) -> None:
        """Initialize pg_stat_statements extension. Must be called from async context (e.g., main.py at startup)."""
        if not cls._enabled:
            return

        try:
            async with pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
                logger.info("Pg_stat_statements Extension Enabled")
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"Could not enable pg_stat_statements: {e}")

    @classmethod
    def set_threshold(cls, threshold_ms: float) -> None:
        """Set slow query threshold in milliseconds."""
        cls._slow_threshold_ms = threshold_ms

    @classmethod
    @contextmanager
    def track(cls, query_name: str, query: str | None = None) -> Any:
        """
        Context manager to track query execution time.
        Usage:
            with QueryMonitor.track("get_cart", query):
                await conn.fetch(...)
        """
        if not cls._enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > cls._slow_threshold_ms:
                logger.warning(
                    f"🐢 Slow Query [{query_name}]: {elapsed_ms:.0f}ms"
                    + (f" | {query}" if query else "")
                )

    @classmethod
    async def track_slow(cls, query_name: str, duration_ms: float) -> None:
        """Log slow query to database."""
        if not cls._enabled:
            return
        async with cls._pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                "INSERT INTO slow_queries (query_name, duration_ms) VALUES ($1, $2)",
                query_name, duration_ms
            )

    @classmethod
    async def get_slow_queries(cls, pool: asyncpg.Pool, limit: int = 10) -> list[Any]:
        """Get top slow queries from pg_stat_statements."""
        if not cls._enabled:
            return []

        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT query, calls, total_exec_time, mean_exec_time, max_exec_time
                    FROM pg_stat_statements
                    ORDER BY total_exec_time DESC
                    LIMIT $1
                """, limit)
                return [dict[str, Any](row) for row in rows]
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Could not get slow queries: {e}")
                return []

    @classmethod
    async def reset_stats(cls, pool: asyncpg.Pool) -> None:
        """Reset pg_stat_statements statistics."""
        if not cls._enabled:
            return

        async with pool.acquire() as conn:
            try:
                await conn.execute("SELECT pg_stat_statements_reset()")
                logger.info("Pg_stat_statements Statistics Reset")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Could not reset stats: {e}")


def monitored_query(query_name: str) -> Any:
    """
    Decorator to monitor async query functions.
    Usage:
        @monitored_query("get_cart")
        async def get_cart(user_id):
            ...
    """
    def decorator(func: Callable[..., Any]) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            query_str = getattr(func, '__query__', None)
            with QueryMonitor.track(query_name, query_str):
                return await func(*args, **kwargs)
        wrapper.__query_name__ = query_name  # type: ignore[attr-defined]
        return wrapper
    return decorator


async def log_query_stats(pool: asyncpg.Pool, logger_instance: Optional[logging.Logger] = None) -> Any:
    """Log current query statistics."""
    if not QueryMonitor._enabled:
        return

    slow_queries = await QueryMonitor.get_slow_queries(pool)
    if not slow_queries:
        return

    log = logger_instance or logger
    log.info("=== Top Slow Queries ===")
    for i, q in enumerate(slow_queries, 1):
        log.info(
            f"{i}. {q['query'][:80]}... "
            f"calls={q['calls']} "
            f"total={q['total_exec_time']:.2f}ms "
            f"mean={q['mean_exec_time']:.2f}ms"
        )


class QueryLoggerMiddleware:
    """
    Middleware for logging all database queries in development.
    """

    def __init__(self, pool: asyncpg.Pool, log_queries: Optional[bool] = None) -> None:
        self.pool = pool
        self.log_queries = log_queries if log_queries is not None else os.getenv("LOG_ALL_QUERIES", "false").lower() == "true"

    async def execute(self, query: str, *args: Any) -> Any:
        """Execute query with logging."""
        if not self.log_queries:
            return await self.pool.execute(query, *args)

        start = time.perf_counter()
        result = await self.pool.execute(query, *args)
        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.debug(f"QUERY ({elapsed_ms:.2f}ms): {query[:200]}")

        if elapsed_ms > QueryMonitor._slow_threshold_ms:
            logger.warning(f"SLOW: {query[:200]}")

        return result

    async def fetch(self, query: str, *args: Any) -> Any:
        """Fetch with logging."""
        start = time.perf_counter()
        result = await self.pool.fetch(query, *args)
        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.debug(f"FETCH ({elapsed_ms:.2f}ms): {query[:200]} rows={len(result)}")

        return result

    async def fetchrow(self, query: str, *args: Any) -> Any:
        """Fetchrow with logging."""
        start = time.perf_counter()
        result = await self.pool.fetchrow(query, *args)
        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.debug(f"FETCHROW ({elapsed_ms:.2f}ms): {query[:200]}")

        return result
