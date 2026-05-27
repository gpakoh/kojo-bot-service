# Tg_bot/tenant/database.py
"""
Multi-tenant Database Isolation.

Provides database access with tenant context.
Supports both:
- Schema-per-tenant (PostgreSQL schemas)
- Tenant-ID column in shared tables
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg
from asyncpg.pool import Pool

from tg_bot.tenant.config import TenantConfig, get_current_tenant

logger = logging.getLogger(__name__)


class TenantDatabase:
    """
    Database access with multi-tenant isolation.

    Supports two strategies:
    1. Schema-per-tenant: SET search_path TO "tenant_schema"
    2. Shared schema with tenant_id: auto-filter by tenant

    Configuration:
        TENANT_ISOLATION_STRATEGY=schema_per_tenant  # or shared_schema
    """

    _instance: Optional['TenantDatabase'] = None

    def __init__(self, pool: Pool, strategy: Optional[str] = None) -> None:
        self._pool = pool
        self._strategy = strategy or os.environ.get(
            "TENANT_ISOLATION_STRATEGY",
            "schema_per_tenant"
        )
        self._current_tenant_schema: Optional[str] = None

    @classmethod
    def get_instance(cls, pool: Pool = None) -> 'TenantDatabase':
        if cls._instance is None:
            if pool is None:
                raise ValueError("Pool required on first initialization")
            cls._instance = cls(pool)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset instance (for testing)."""
        cls._instance = None

    @property
    def strategy(self) -> Optional[str]:
        return self._strategy

    @asynccontextmanager
    async def tenant_context(self, tenant: TenantConfig) -> Any:
        """
        Context manager to set tenant schema for database operations.

        Usage:
            async with db.tenant_context(tenant):
                await conn.fetch("SELECT * FROM orders")
        """
        previous_schema = self._current_tenant_schema

        if self._strategy == "schema_per_tenant":
            self._current_tenant_schema = tenant.db_schema

        try:
            yield self
        finally:
            self._current_tenant_schema = previous_schema

    async def execute_with_tenant(
        self,
        conn: asyncpg.Connection,
        query: str,
        *args: Any
    ) -> Any:
        """Execute query in tenant context."""
        if self._strategy == "schema_per_tenant" and self._current_tenant_schema:
            # Set Schema For This Connection
            await conn.execute(
                f'SET search_path TO "{self._current_tenant_schema}", public'
            )

        return await conn.execute(query, *args)

    async def fetch_with_tenant(
        self,
        conn: asyncpg.Connection,
        query: str,
        *args: Any
    ) -> list[Any]:
        """Fetch rows in tenant context."""
        if self._strategy == "schema_per_tenant" and self._current_tenant_schema:
            await conn.execute(
                f'SET search_path TO "{self._current_tenant_schema}", public'
            )

        return await conn.fetch(query, *args)  # type: ignore[no-any-return]

    async def fetchrow_with_tenant(
        self,
        conn: asyncpg.Connection,
        query: str,
        *args: Any
    ) -> Optional[dict[str, Any]]:
        """Fetch single row in tenant context."""
        if self._strategy == "schema_per_tenant" and self._current_tenant_schema:
            await conn.execute(
                f'SET search_path TO "{self._current_tenant_schema}", public'
            )

        return await conn.fetchrow(query, *args)  # type: ignore[no-any-return]

    def add_tenant_filter(self, query: str, tenant_id_column: str = "bot_id") -> str:
        """
        Add tenant_id filter to query for shared_schema strategy.

        For shared tables, automatically adds WHERE bot_id = $X
        """
        if self._strategy == "shared_schema":
            tenant = get_current_tenant()
            if tenant:
                # Simple Injection - In Production Use Proper Parameterization
                if "WHERE" in query.upper():
                    return f"{query} AND {tenant_id_column} = '{tenant.bot_id}'"
                else:
                    return f"{query} WHERE {tenant_id_column} = '{tenant.bot_id}'"

        return query

    async def create_tenant_schema(self, tenant: TenantConfig) -> None:
        """Create schema for new tenant."""
        if self._strategy != "schema_per_tenant":
            return

        schema = tenant.db_schema

        async with self._pool.acquire() as conn:
            # Create Schema
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

            # Grant Permissions (if Needed)
            # Await Conn.execute(f'grant ALL ON SCHEMA {schema} TO Current_user')

            logger.info(f"✅ Created schema for tenant: {tenant.bot_id}")

    async def drop_tenant_schema(self, tenant: TenantConfig) -> None:
        """Drop schema for tenant (dangerous!)."""
        if self._strategy != "schema_per_tenant":
            return

        schema = tenant.db_schema

        async with self._pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            logger.warning(f"🗑️ Dropped schema for tenant: {tenant.bot_id}")


def get_tenant_database() -> Optional[TenantDatabase]:
    """Get the tenant database instance."""
    return TenantDatabase._instance


__all__ = [
    'TenantDatabase',
    'get_tenant_database',
]
