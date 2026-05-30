"""Tests for UserService — GDPR anonymize_user, registration, approval flow."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.user_service import UserService
from tg_bot.models import UserStatus
from tg_bot.tenant.config import set_current_tenant


def _mock_conn(user_row: dict[str, Any] | None = None) -> MagicMock:
    conn = MagicMock()

    async def fetchrow_side(sql: str, *args: Any) -> dict[str, Any] | None:
        return user_row

    conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    conn.execute = AsyncMock(return_value=None)
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def _make_service(conn: MagicMock) -> UserService:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return UserService(pool=pool)


USER_ROW = {
    "id": 42,
    "telegram_id": 12345,
    "fio": "Иван Иванов",
    "phone": "+79001234567",
    "email": "ivan@example.com",
    "status": UserStatus.APPROVED.value,
    "role": "user",
    "data_cleared_at": None,
    "registration_message_id": 777,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}


class TestUserServiceAnonymize:
    """GDPR anonymize_user — PII clearing, data deletion, order preservation."""

    @pytest.mark.asyncio
    async def test_anonymize_clears_pii(self) -> None:
        conn = _mock_conn(dict(USER_ROW))
        service = _make_service(conn)

        result = await service.anonymize_user(telegram_id=12345, requested_by=999)

        assert result is True

        calls = [str(c) for c in conn.execute.call_args_list]
        update_users_calls = [c for c in calls if "UPDATE users" in c and "[deleted]" in c]
        assert len(update_users_calls) == 1
        assert "registration_message_id = NULL" in update_users_calls[0]

    @pytest.mark.asyncio
    async def test_anonymize_deletes_user_data(self) -> None:
        conn = _mock_conn(dict(USER_ROW))
        service = _make_service(conn)

        await service.anonymize_user(telegram_id=12345, requested_by=999)

        calls = [str(c) for c in conn.execute.call_args_list]
        tables_deleted = set()
        for call_str in calls:
            for table in ("user_favorites", "user_favorite_recipes", "cart_items", "user_saved_addresses"):
                if f"DELETE FROM {table}" in call_str:
                    tables_deleted.add(table)

        assert tables_deleted == {
            "user_favorites", "user_favorite_recipes",
            "cart_items", "user_saved_addresses",
        }

    @pytest.mark.asyncio
    async def test_anonymize_updates_orders_not_deletes(self) -> None:
        conn = _mock_conn(dict(USER_ROW))
        service = _make_service(conn)

        await service.anonymize_user(telegram_id=12345, requested_by=999)

        calls = [str(c) for c in conn.execute.call_args_list]
        order_updates = [c for c in calls if "UPDATE orders" in c]
        order_deletes = [c for c in calls if "DELETE FROM orders" in c]
        assert len(order_updates) == 1
        assert len(order_deletes) == 0

    @pytest.mark.asyncio
    async def test_anonymize_not_found_returns_false(self) -> None:
        conn = _mock_conn(user_row=None)
        service = _make_service(conn)

        result = await service.anonymize_user(telegram_id=99999, requested_by=999)

        assert result is False
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_anonymize_idempotent(self) -> None:
        conn = _mock_conn(dict(USER_ROW))
        service = _make_service(conn)

        result1 = await service.anonymize_user(telegram_id=12345, requested_by=999)
        result2 = await service.anonymize_user(telegram_id=12345, requested_by=999)

        assert result1 is True
        assert result2 is True
        assert conn.execute.call_count >= 4


class TestUserServiceTenantAware:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        return pool, conn

    @pytest.mark.asyncio
    async def test_uses_tenant_connection_when_tenant_is_set(self) -> Any:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=dict(USER_ROW))

        pool = MagicMock()
        pool.acquire = MagicMock()

        class DummyDbManager:
            def __init__(self) -> None:
                self.called = False
                self.seen_tenant_id = None

            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                self.called = True
                self.seen_tenant_id = tenant_id
                yield conn

        db_manager = DummyDbManager()
        service = UserService(pool, db_manager=db_manager)

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        try:
            result = await service.get_user(telegram_id=12345)
        finally:
            set_current_tenant(None)

        assert result is not None
        assert result.fio == "Иван Иванов"
        assert db_manager.called is True
        assert db_manager.seen_tenant_id == "kojo-test"
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_tenant(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=dict(USER_ROW))

        class DummyDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise AssertionError("should not be called")

        service = UserService(pool, db_manager=DummyDbManager())
        result = await service.get_user(telegram_id=12345)
        assert result is not None
        assert result.fio == "Иван Иванов"

    @pytest.mark.asyncio
    async def test_falls_back_to_pool_when_no_db_manager(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=dict(USER_ROW))

        service = UserService(pool)
        result = await service.get_user(telegram_id=12345)
        assert result is not None
        assert result.fio == "Иван Иванов"

    @pytest.mark.asyncio
    async def test_does_not_fallback_when_tenant_connection_fails(self) -> Any:
        conn = AsyncMock()
        pool = MagicMock()
        pool.acquire = MagicMock()

        class FailingDbManager:
            @asynccontextmanager
            async def tenant_connection(self, tenant_id: str) -> Any:
                raise RuntimeError("tenant db connection failed")
                yield  # pragma: no cover

        service = UserService(pool, db_manager=FailingDbManager())

        set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
        with pytest.raises(RuntimeError, match="tenant db connection failed"):
            await service.get_user(telegram_id=12345)
        set_current_tenant(None)

        pool.acquire.assert_not_called()
