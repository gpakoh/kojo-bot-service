"""Unit tests for tg_bot/handlers/staff.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.models import OrderStatus


def _staff_auth_setup(mock_context, user_status="approved", has_staff_privs=True):
    """Configure context so auth_guard passes for staff_only handlers."""
    container = MagicMock()
    user_svc = MagicMock()
    user_svc.get_user = AsyncMock(return_value=MagicMock(status=user_status))
    user_svc.has_staff_privileges = MagicMock(return_value=has_staff_privs)
    container.get.return_value = user_svc
    mock_context.di = container
    mock_context.bot_data["admin_ids"] = [1, 2]
    return mock_context


class TestShowActiveOrdersShortcut:
    @pytest.mark.asyncio
    async def test_guard_when_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        _staff_auth_setup(mock_context)
        from tg_bot.handlers.staff import show_active_orders_shortcut

        result = await show_active_orders_shortcut(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_when_responder_none(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        mock_context.bot_data["order_service"] = MagicMock()
        mock_context.bot_data["order_service"].get_orders_for_staff_view = AsyncMock(
            return_value=[]
        )
        from tg_bot.handlers.staff import show_active_orders_shortcut

        result = await show_active_orders_shortcut(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_orders_shows_message(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        mock_context.bot_data["order_service"] = MagicMock()
        mock_context.bot_data["order_service"].get_orders_for_staff_view = AsyncMock(
            return_value=[]
        )
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        from tg_bot.handlers.staff import show_active_orders_shortcut

        await show_active_orders_shortcut(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_once()
        call_args = mock_update.message.reply_text.call_args[0]
        assert "Все активные заказы обработаны" in call_args[0]

    @pytest.mark.asyncio
    async def test_shows_active_orders(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        orders = [
            {
                "id": 1,
                "user_fio": "Иван",
                "items_str": "Кофе 2x",
                "total_amount": 500,
            }
        ]
        mock_context.bot_data["order_service"] = MagicMock()
        mock_context.bot_data["order_service"].get_orders_for_staff_view = AsyncMock(
            return_value=orders
        )
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        from tg_bot.handlers.staff import show_active_orders_shortcut

        await show_active_orders_shortcut(mock_update, mock_context)
        assert mock_update.message.reply_text.await_count >= 2


class TestShowStats:
    @pytest.mark.asyncio
    async def test_formats_stats_with_callback(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        mock_context.bot_data["order_service"] = MagicMock()
        mock_context.bot_data["order_service"].get_order_counts_by_status = AsyncMock(
            return_value={
                OrderStatus.AWAITING_PAYMENT: 1,
                OrderStatus.PAID: 2,
                OrderStatus.READY_FOR_PICKUP: 3,
                OrderStatus.COMPLETED: 4,
                OrderStatus.CANCELLED: 5,
            }
        )
        cq = MagicMock()
        cq.message = MagicMock()
        cq.message.edit_text = AsyncMock()
        cq.answer = AsyncMock()
        mock_update.callback_query = cq
        from tg_bot.handlers.staff import show_stats

        await show_stats(mock_update, mock_context)
        cq.message.edit_text.assert_awaited_once()
        text = cq.message.edit_text.call_args[0][0]
        assert "Статистика" in text
        assert "1" in text
        assert "2" in text
        assert "3" in text


class TestShowMyProfile:
    @pytest.mark.asyncio
    async def test_shows_profile_info(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        import datetime

        user_db = MagicMock()
        user_db.fio = "Иван Иванов"
        user_db.role = "admin"
        user_db.phone = "+79991112233"
        user_db.email = "ivan@test.com"
        user_db.telegram_id = 123456
        user_db.created_at = datetime.datetime(2024, 1, 15)
        mock_context.bot_data["user_service"] = MagicMock()
        mock_context.bot_data["user_service"].get_user = AsyncMock(
            return_value=user_db
        )
        cq = MagicMock()
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        mock_update.callback_query = cq
        from tg_bot.handlers.staff import show_my_profile

        await show_my_profile(mock_update, mock_context)
        cq.answer.assert_awaited_once()
        cq.edit_message_text.assert_awaited_once()
        text = cq.edit_message_text.call_args[0][0]
        assert "Иван Иванов" in text
        assert "+79991112233" in text
        assert "ivan@test.com" in text


class TestTriggerManualSync:
    @pytest.mark.asyncio
    async def test_calls_sync_products(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        mock_context.bot_data["db_pool"] = MagicMock()
        mock_context.bot_data["notification_service"] = MagicMock()
        mock_context.bot_data["notification_service"].process_restock_notifications = (
            AsyncMock()
        )
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = status_msg
        from tg_bot.handlers.staff import trigger_manual_sync

        with patch(
            "tg_bot.handlers.staff.sync_service.sync_products", new_callable=AsyncMock
        ) as mock_sync:
            await trigger_manual_sync(mock_update, mock_context)
            mock_sync.assert_awaited_once_with(mock_context.bot_data["db_pool"])

    @pytest.mark.asyncio
    async def test_handles_no_notification_service(self, mock_update, mock_context):
        _staff_auth_setup(mock_context)
        mock_context.bot_data["db_pool"] = MagicMock()
        mock_context.bot_data["notification_service"] = None
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = status_msg
        from tg_bot.handlers.staff import trigger_manual_sync

        with patch(
            "tg_bot.handlers.staff.sync_service.sync_products", new_callable=AsyncMock
        ) as mock_sync:
            await trigger_manual_sync(mock_update, mock_context)
            mock_sync.assert_awaited_once()
            status_msg.edit_text.assert_any_call(
                "⚠️ Каталог обновлен, но сервис уведомлений не найден. Рассылка пропущена.",
                parse_mode="HTML",
            )
