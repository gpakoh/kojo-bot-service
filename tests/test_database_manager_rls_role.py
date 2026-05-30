"""Unit tests for DatabaseManager.check_runtime_role_rls_safe()."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.infrastructure.database import DatabaseManager


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_runtime_role_check_marks_non_bypass_role_safe():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "role_name": "kojo_app",
            "is_superuser": False,
            "bypasses_rls": False,
        }
    )

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acquire(conn))

    db = DatabaseManager(pool)

    result = await db.check_runtime_role_rls_safe()

    assert result == {
        "role_name": "kojo_app",
        "is_superuser": False,
        "bypasses_rls": False,
        "safe_for_rls": True,
    }


@pytest.mark.asyncio
async def test_runtime_role_check_rejects_superuser():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "role_name": "postgres",
            "is_superuser": True,
            "bypasses_rls": True,
        }
    )

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acquire(conn))

    db = DatabaseManager(pool)

    result = await db.check_runtime_role_rls_safe()

    assert result["safe_for_rls"] is False
    assert result["is_superuser"] is True
    assert result["bypasses_rls"] is True


@pytest.mark.asyncio
async def test_runtime_role_check_handles_none_row():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acquire(conn))

    db = DatabaseManager(pool)

    result = await db.check_runtime_role_rls_safe()

    assert result["safe_for_rls"] is False
    assert result["role_name"] == "unknown"
