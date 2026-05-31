"""Integration tests proving RLS isolates tenant data at the DB level."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://kojo_user:kojo_password@127.0.0.1:5435/kojo_db",
).replace("+asyncpg", "")

# Use a non-superuser role so RLS actually applies
RLS_TEST_URL = DATABASE_URL.replace("kojo_user:kojo_password", "kojo_rls_test:rls_test_pass")


@asynccontextmanager
async def _pool(url: str = RLS_TEST_URL) -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
    assert pool is not None
    try:
        yield pool
    finally:
        await pool.close()


async def _set_tenant(conn: asyncpg.Connection, tenant: str) -> None:
    await conn.execute("SELECT set_tenant_context($1)", tenant)


async def _reset_tenant(conn: asyncpg.Connection) -> None:
    await conn.execute("SELECT set_config('app.current_tenant', '', false)")


class TestRlsIsolatesUsers:
    async def _insert_user(
        self, conn: asyncpg.Connection, telegram_id: int, tenant: str
    ) -> None:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, fio, phone, email, status, role, tenant_id)
            VALUES ($1, $2, $3, $4, 'approved', 'user', $5)
            ON CONFLICT (tenant_id, telegram_id) DO NOTHING
            """,
            telegram_id,
            f"User {telegram_id}",
            f"+{telegram_id}",
            f"{telegram_id}@test.local",
            tenant,
        )

    async def test_tenant_a_sees_its_own_user(self) -> None:
        async with _pool() as pool:
            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_a")
                await self._insert_user(conn, 2001, "tenant_a")

                row = await conn.fetchrow(
                    "SELECT fio FROM users WHERE telegram_id = 2001"
                )
                assert row is not None
                assert row["fio"] == "User 2001"

    async def test_tenant_b_does_not_see_tenant_a_user(self) -> None:
        async with _pool() as pool:
            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_a")
                await self._insert_user(conn, 2002, "tenant_a")

            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_b")
                row = await conn.fetchrow(
                    "SELECT fio FROM users WHERE telegram_id = 2002"
                )
                assert row is None, "tenant_b should not see tenant_a's user"

    async def test_no_tenant_context_returns_empty(self) -> None:
        async with _pool() as pool:
            async with pool.acquire() as conn:
                await _set_tenant(conn, "kojo")
                await self._insert_user(conn, 2003, "kojo")

            async with pool.acquire() as conn:
                await _reset_tenant(conn)
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE telegram_id = 2003"
                )
                assert rows == [], "no tenant context should see no rows"

    async def test_superuser_bypasses_rls(self) -> None:
        """Verify that superuser bypasses RLS — this documents the risk."""
        async with _pool(url=DATABASE_URL) as pool:
            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_a")
                await self._insert_user(conn, 2099, "tenant_a")

            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_b")
                row = await conn.fetchrow(
                    "SELECT fio FROM users WHERE telegram_id = 2099"
                )
                assert row is not None, (
                    "superuser should bypass RLS and see cross-tenant data"
                )


class TestRlsTestRoleNoBypass:
    async def test_rls_test_role_does_not_bypass_rls(self) -> None:
        async with _pool() as pool:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT rolsuper, rolbypassrls
                    FROM pg_roles
                    WHERE rolname = current_user
                    """
                )

        assert row is not None
        assert row["rolsuper"] is False
        assert row["rolbypassrls"] is False


class TestRlsIsolatesProducts:
    async def test_tenant_a_sees_its_own_product(self) -> None:
        async with _pool() as pool:
            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_a")
                await conn.execute(
                    """
                    INSERT INTO products (name, tenant_id)
                    VALUES ($1, $2)
                    ON CONFLICT (tenant_id, name) DO NOTHING
                    """,
                    "rls_test_product_a",
                    "tenant_a",
                )
                row = await conn.fetchrow(
                    "SELECT name FROM products WHERE name = 'rls_test_product_a'"
                )
                assert row is not None
                assert row["name"] == "rls_test_product_a"

    async def test_tenant_b_does_not_see_tenant_a_product(self) -> None:
        async with _pool() as pool:
            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_a")
                await conn.execute(
                    """
                    INSERT INTO products (name, tenant_id)
                    VALUES ($1, $2)
                    ON CONFLICT (tenant_id, name) DO NOTHING
                    """,
                    "rls_test_product_b",
                    "tenant_a",
                )

            async with pool.acquire() as conn:
                await _set_tenant(conn, "tenant_b")
                row = await conn.fetchrow(
                    "SELECT name FROM products WHERE name = 'rls_test_product_b'"
                )
                assert row is None, "tenant_b should not see tenant_a's product"
