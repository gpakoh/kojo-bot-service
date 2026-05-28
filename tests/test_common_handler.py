"""Unit tests for tg_bot/handlers/common.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.handlers.common import (
    clean_response,
    cleanup_previous_menu,
    handle_stale_callback,
    safe_delete_message,
)
from tg_bot.models import UserStatus


class TestCleanResponse:
    def test_normal_text(self):
        assert clean_response("  hello world  ") == "hello world"

    def test_whitespace_text(self):
        assert clean_response("   ") == ""


class TestCleanupPreviousMenu:
    @pytest.mark.asyncio
    async def test_no_user_service_skips_db(self, mock_context):
        mock_context.bot_data = {}
        await cleanup_previous_menu(mock_context, 123)
        mock_context.bot.delete_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_prompt_from_user_data(self, mock_context):
        mock_context.bot_data = {"user_service": AsyncMock()}
        mock_context.bot_data["user_service"].get_user = AsyncMock(return_value=None)
        mock_context.user_data = {"prompt_msg_id": 42}
        await cleanup_previous_menu(mock_context, 123)
        mock_context.bot.delete_message.assert_awaited_once_with(
            chat_id=123, message_id=42
        )

    @pytest.mark.asyncio
    async def test_exclude_id_skips_matching(self, mock_context):
        mock_context.bot_data = {"user_service": AsyncMock()}
        mock_context.bot_data["user_service"].get_user = AsyncMock(return_value=None)
        mock_context.user_data = {"prompt_msg_id": 42}
        await cleanup_previous_menu(mock_context, 123, exclude_id=42)
        mock_context.bot.delete_message.assert_not_called()
        assert mock_context.user_data.get("prompt_msg_id") == 42

    @pytest.mark.asyncio
    async def test_exceptions_handled_gracefully(self, mock_context):
        mock_context.bot_data = {"user_service": AsyncMock()}
        mock_context.bot_data["user_service"].get_user = AsyncMock(return_value=None)
        mock_context.user_data = {"prompt_msg_id": 42}
        mock_context.bot.delete_message.side_effect = ValueError("gone")
        await cleanup_previous_menu(mock_context, 123)


class TestSafeDeleteMessage:
    @pytest.mark.asyncio
    async def test_success_returns_true(self, mock_context):
        result = await safe_delete_message(mock_context, 123, 456)
        assert result is True
        mock_context.bot.delete_message.assert_awaited_once_with(
            chat_id=123, message_id=456
        )

    @pytest.mark.asyncio
    async def test_error_returns_false(self, mock_context):
        mock_context.bot.delete_message.side_effect = ValueError(
            "Message to delete not found"
        )
        result = await safe_delete_message(mock_context, 123, 456)
        assert result is False


class TestHandleStaleCallback:
    @pytest.mark.asyncio
    async def test_guard_when_query_is_none(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_stale_callback(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_when_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock()
        result = await handle_stale_callback(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_blocked_user_shows_alert(self, mock_update, mock_context):
        cq = MagicMock()
        cq.data = "test"
        cq.answer = AsyncMock()
        mock_update.callback_query = cq
        mock_user_svc = MagicMock()
        mock_user_svc.get_user = AsyncMock(
            return_value=MagicMock(status=UserStatus.BLOCKED)
        )
        mock_context.bot_data["user_service"] = mock_user_svc
        await handle_stale_callback(mock_update, mock_context)
        cq.answer.assert_awaited_once_with(
            "Ваш аккаунт заблокирован.", show_alert=True
        )

    @pytest.mark.asyncio
    async def test_normal_flow_calls_start(self, mock_update, mock_context):
        cq = MagicMock()
        cq.data = "test"
        cq.answer = AsyncMock()
        cq.message = MagicMock()
        cq.message.message_id = 789
        mock_update.callback_query = cq
        mock_user_svc = MagicMock()
        mock_user_svc.get_user = AsyncMock(
            return_value=MagicMock(status=UserStatus.PENDING)
        )
        mock_user_svc.save_registration_message_id = AsyncMock()
        mock_context.bot_data["user_service"] = mock_user_svc
        with patch(
            "tg_bot.handlers.registration.start", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = 42
            result = await handle_stale_callback(mock_update, mock_context)
            assert result == 42
            cq.answer.assert_awaited_once_with("Восстанавливаю меню...")
            mock_user_svc.save_registration_message_id.assert_awaited_once_with(
                123456, 789
            )
            mock_start.assert_awaited_once_with(mock_update, mock_context)
