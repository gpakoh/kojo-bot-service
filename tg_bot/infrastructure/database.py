# Tg_bot/infrastructure/database.py
"""
Database Infrastructure Layer.

Provides connection pooling, retry logic, and health checks for PostgreSQL.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Optional, TypeVar

import asyncpg
from asyncpg.pool import Pool

T = TypeVar('T')

logger = logging.getLogger(__name__)

POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))
POOL_COMMAND_TIMEOUT = float(os.getenv("DB_COMMAND_TIMEOUT", "10"))
POOL_MAX_INACTIVE_TIME = float(os.getenv("DB_POOL_MAX_INACTIVE_TIME", "300"))
CONNECTION_TIMEOUT = float(os.getenv("DB_CONNECTION_TIMEOUT", "30"))
MAX_RETRY_ATTEMPTS = int(os.getenv("DB_MAX_RETRY_ATTEMPTS", "3"))
RETRY_BASE_DELAY = float(os.getenv("DB_RETRY_BASE_DELAY", "1.0"))


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Connection-related errors."""
    pass


class DatabaseRetryExhaustedError(DatabaseError):
    """Raised when all retry attempts are exhausted."""
    pass


class Database:
    """
    Database wrapper with connection pooling and retry logic.

    Provides:
    - Connection pooling with configurable parameters
    - Automatic retry on transient errors
    - Health check functionality
    - JSON codec registration
    """

    _instance: Optional['Database'] = None

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Optional[Pool] = None
        self._initialized = False

    @classmethod
    def get_instance(cls, dsn: Optional[str] = None) -> 'Database':
        """Get or create singleton instance."""
        if cls._instance is None:
            if dsn is None:
                raise ValueError("Database not initialized. Provide DSN on first call.")
            cls._instance = cls(dsn)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    async def connect(self) -> Pool:
        """Create connection pool with optimized settings."""
        if self._pool is not None:
            return self._pool

        logger.info(f"Creating database pool: min={POOL_MIN_SIZE}, max={POOL_MAX_SIZE}")

        try:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
                max_inactive_time=POOL_MAX_INACTIVE_TIME,
                command_timeout=POOL_COMMAND_TIMEOUT,
                timeout=CONNECTION_TIMEOUT,
                init=self._init_connection,
                server_settings={
                    'jit': 'off',
                    'timezone': 'UTC',
                }
            )
            self._initialized = True
            logger.info(f"Database pool created: {self._pool.get_min_size()}-{self._pool.get_max_size()}")
            return self._pool
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Failed to create database pool: {e}")
            raise DatabaseConnectionError(f"Failed to connect to database: {e}") from e

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize connection: register JSON codecs."""
        try:
            import json
            await conn.set_type_codec(
                'jsonb',
                encoder=json.dumps,
                decoder=json.loads,
                schema='pg_catalog'
            )
            await conn.set_type_codec(
                'json',
                encoder=json.dumps,
                decoder=json.loads,
                schema='pg_catalog'
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"JSON codec registration warning: {e}")

    @property
    def pool(self) -> Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise DatabaseError("Database not connected. Call connect() first.")
        return self._pool

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._pool is not None and self._initialized

    @asynccontextmanager
    async def acquire(self, timeout: float = CONNECTION_TIMEOUT) -> Any:
        """Acquire connection from pool with timeout."""
        async with self._pool.acquire(timeout=timeout) as conn:  # type: ignore[union-attr]
            yield conn

    @asynccontextmanager
    async def transaction(self, timeout: float = CONNECTION_TIMEOUT) -> Any:
        """Acquire connection with active transaction."""
        async with self._pool.acquire(timeout=timeout) as conn:  # type: ignore[union-attr]
            async with conn.transaction():
                yield conn

    async def execute(self, query: str, *args: object, retry: bool = True) -> str:
        """Execute query with optional retry."""
        return await self._execute_with_retry(
            lambda conn: conn.execute(query, *args),
            retry=retry
        )

    async def fetch(self, query: str, *args: object, retry: bool = True) -> list[dict[str, object]]:
        """Fetch rows with optional retry."""
        return await self._execute_with_retry(
            lambda conn: conn.fetch(query, *args),
            retry=retry
        )

    async def fetchrow(self, query: str, *args: object, retry: bool = True) -> Optional[dict[str, object]]:
        """Fetch single row with optional retry."""
        return await self._execute_with_retry(
            lambda conn: conn.fetchrow(query, *args),
            retry=retry
        )

    async def fetchval(self, query: str, *args: object, retry: bool = True) -> object:
        """Fetch single value with optional retry."""
        return await self._execute_with_retry(
            lambda conn: conn.fetchval(query, *args),
            retry=retry
        )

    async def _execute_with_retry(self, func: Callable[[asyncpg.Connection], T], retry: bool = True) -> T:
        """Execute function with retry logic for transient errors."""
        transient_errors = (
            ConnectionResetError,
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.ConnectionFailureError,
            asyncpg.TooManyConnectionsError,
        )

        last_error = None
        delay = RETRY_BASE_DELAY

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                async with self.acquire() as conn:
                        return await func(conn)  # type: ignore[no-any-return, misc]
            except transient_errors as e:
                last_error = e
                if retry and attempt < MAX_RETRY_ATTEMPTS:
                    logger.warning(
                        f"Database transient error (attempt {attempt}/{MAX_RETRY_ATTEMPTS}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    break
            except asyncpg.PostgresSyntaxError as e:
                logger.error(f"SQL syntax error: {e}")
                raise DatabaseError(f"SQL syntax error: {e}") from e
            except asyncpg.UndefinedTableError as e:
                logger.error(f"Table does not exist: {e}")
                raise DatabaseError(f"Undefined table: {e}") from e

        raise DatabaseRetryExhaustedError(
            f"Database operation failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    async def health_check(self) -> dict[str, object]:
        """
        Health check for database connectivity.
        Returns status and pool statistics.
        """
        if not self.is_connected:
            return {
                "status": "disconnected",
                "error": "Database pool not initialized"
            }

        try:
            async with self.acquire(timeout=5) as conn:
                result = await conn.fetchrow("SELECT 1 as health")
                if result and result['health'] == 1:
                    pool = self._pool
                    assert pool is not None
                    return {
                        "status": "healthy",
                        "pool": {
                            "min_size": pool.get_min_size(),
                            "max_size": pool.get_max_size(),
                            "free_connections": pool.get_idle_size(),
                        }
                    }
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

        return {"status": "unknown"}

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info("Database Pool Closed")


# Backward Compatibility: Create Module-level Functions
async def init_db_extensions(pool: Pool) -> None:
    """Initialize database extensions (backward compatible)."""
    logger.info("Initializing Database Extensions...")
    async with pool.acquire() as connection:
        await connection.execute("CREATE EXTENSION IF NOT EXISTS uuid-ossp")
        await connection.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        logger.info("Database Extensions Initialized.")


class DatabaseManager:
    """Lightweight database facade that wraps a pre-configured asyncpg pool.

    Used by integration tests that inject a mock pool directly.
    Supports RLS via set_tenant_context() and tenant_connection().
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def set_tenant_context(self, tenant_id: str) -> None:
        """Set PostgreSQL RLS context for current connection."""
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT set_tenant_context($1)", tenant_id)

    @asynccontextmanager
    async def tenant_connection(self, tenant_id: str | None = None) -> AsyncGenerator[Any, None]:
        """Acquire connection with tenant RLS context set.

        Usage:
            async with db.tenant_connection("bot_kojo") as conn:
                await conn.fetch("SELECT * FROM orders")
        """
        async with self._pool.acquire() as conn:
            if tenant_id:
                await conn.execute("SELECT set_tenant_context($1)", tenant_id)
            yield conn

    async def check_runtime_role_rls_safe(self) -> dict[str, bool | str]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    current_user AS role_name,
                    rolsuper AS is_superuser,
                    rolbypassrls AS bypasses_rls
                FROM pg_roles
                WHERE rolname = current_user
                """
            )

        if row is None:
            return {
                "role_name": "unknown",
                "is_superuser": True,
                "bypasses_rls": True,
                "safe_for_rls": False,
            }

        is_superuser = bool(row["is_superuser"])
        bypasses_rls = bool(row["bypasses_rls"])

        return {
            "role_name": str(row["role_name"]),
            "is_superuser": is_superuser,
            "bypasses_rls": bypasses_rls,
            "safe_for_rls": not is_superuser and not bypasses_rls,
        }

    async def execute(self, query: str, *args: object) -> str:
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *args)
            return str(result)

    async def fetch_all(self, query: str, *args: object) -> list[dict[str, object]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    @asynccontextmanager
    async def transaction(self) -> Any:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def health_check(self) -> bool:
        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchrow("SELECT 1 as health")
                if result:
                    row = dict(result)
                    return row.get("health") == 1
                return False
        except (RuntimeError, ConnectionError, TimeoutError, OSError):
            return False


__all__ = [
    'Database',
    'DatabaseError',
    'DatabaseConnectionError',
    'DatabaseRetryExhaustedError',
    'DatabaseManager',
    'init_db_extensions',
]
