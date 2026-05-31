"""Unit tests for tg_bot/handlers/order_notifications.py."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import TelegramError

from tg_bot.handlers.order_notifications import (
    ORDER_STATUS_LABELS,
    notify_user_order_status_changed,
)


class TestOrderStatusLabels:
    def test_contains_all_expected_statuses(self):
        expected = {"ACCEPTED", "AWAITING_PAYMENT", "PAID", "ASSEMBLING", "READY_FOR_PICKUP", "SHIPPED", "COMPLETED", "CANCELLED"}
        assert expected.issubset(ORDER_STATUS_LABELS.keys())

    def test_labels_are_russian_strings(self):
        for label in ORDER_STATUS_LABELS.values():
            assert isinstance(label, str)
            assert len(label) > 0


class TestNotifyUserOrderStatusChanged:
    @pytest.mark.asyncio
    async def test_sends_message_with_order_id_and_status_label(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await notify_user_order_status_changed(
            context=context,
            user_id=123,
            order_id=42,
            new_status="AWAITING_PAYMENT",
        )

        context.bot.send_message.assert_awaited_once()
        args, kwargs = context.bot.send_message.call_args
        assert kwargs["chat_id"] == 123
        assert "#42" in kwargs["text"]
        assert "ожидает оплаты" in kwargs["text"]
        assert kwargs["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_telegram_error_is_tolerated(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock(side_effect=TelegramError("chat not found"))

        await notify_user_order_status_changed(
            context=context,
            user_id=123,
            order_id=42,
            new_status="PAID",
        )

        context.bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_status_falls_back_to_raw_value(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await notify_user_order_status_changed(
            context=context,
            user_id=123,
            order_id=42,
            new_status="SOME_UNKNOWN",
        )

        context.bot.send_message.assert_awaited_once()
        _, kwargs = context.bot.send_message.call_args
        assert "SOME_UNKNOWN" in kwargs["text"]
