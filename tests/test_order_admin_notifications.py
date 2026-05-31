"""Unit tests for tg_bot/handlers/order_admin_notifications.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram

from tg_bot.handlers.order_admin_notifications import notify_admins_about_cancelled_order


class TestNotifyAdminsAboutCancelledOrder:
    @pytest.mark.asyncio
    async def test_sends_to_admin_chat_id(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot_data = {"admin_chat_id": -100999, "admin_ids": []}

        with patch(
            "tg_bot.keyboards.get_admin_order_keyboard",
            return_value=MagicMock(),
        ):
            await notify_admins_about_cancelled_order(
                context=context,
                order_id=42,
                user_id=123,
                reason="Передумал",
            )

        context.bot.send_message.assert_awaited_once()
        _, kwargs = context.bot.send_message.call_args
        assert kwargs["chat_id"] == -100999
        assert "#42" in kwargs["text"]
        assert "Передумал" in kwargs["text"]
        assert kwargs["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_sends_to_admin_ids(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot_data = {"admin_chat_id": None, "admin_ids": [111, 222]}

        with patch(
            "tg_bot.keyboards.get_admin_order_keyboard",
            return_value=MagicMock(),
        ):
            await notify_admins_about_cancelled_order(
                context=context,
                order_id=7,
                user_id=456,
                reason="Долго ждать",
            )

        assert context.bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_telegram_error_is_tolerated(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock(side_effect=telegram.error.TelegramError("chat blocked"))
        context.bot_data = {"admin_chat_id": -100999, "admin_ids": []}

        with patch(
            "tg_bot.keyboards.get_admin_order_keyboard",
            return_value=MagicMock(),
        ):
            await notify_admins_about_cancelled_order(
                context=context,
                order_id=42,
                user_id=123,
                reason="Ошибка",
            )

        context.bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_admins_skips_send(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot_data = {"admin_chat_id": None, "admin_ids": []}

        await notify_admins_about_cancelled_order(
            context=context,
            order_id=42,
            user_id=123,
            reason="Причина",
        )

        context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_includes_customer_name_when_provided(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot_data = {"admin_chat_id": -100999, "admin_ids": []}

        with patch(
            "tg_bot.keyboards.get_admin_order_keyboard",
            return_value=MagicMock(),
        ):
            await notify_admins_about_cancelled_order(
                context=context,
                order_id=42,
                user_id=123,
                reason="Передумал",
                customer_name="Иван",
            )

        _, kwargs = context.bot.send_message.call_args
        assert "Иван" in kwargs["text"]
        assert "123" in kwargs["text"]

    @pytest.mark.asyncio
    async def test_falls_back_to_id_when_no_name(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot_data = {"admin_chat_id": -100999, "admin_ids": []}

        with patch(
            "tg_bot.keyboards.get_admin_order_keyboard",
            return_value=MagicMock(),
        ):
            await notify_admins_about_cancelled_order(
                context=context,
                order_id=42,
                user_id=123,
                reason="Передумал",
            )

        _, kwargs = context.bot.send_message.call_args
        assert "id 123" in kwargs["text"]
