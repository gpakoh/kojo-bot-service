"""Tests for UserService — GDPR anonymize_user, registration, approval flow."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.user_service import UserService
from tg_bot.models import UserStatus


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
