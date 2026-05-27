"""Tests for ui_helpers.py."""
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError

from tg_bot.ui_helpers import (
    _handle_telegram_error,
    cleanup_previous_menu,
    safe_delete_message,
    safe_edit_ui,
    safe_update_ui,
)

# ───────────────────────────── _handle_telegram_error ─────────────────────────────

class TestHandleTelegramError:
    def test_message_not_found_logs_debug(self, caplog: Any) -> None:
        caplog.set_level(10)
        e = TelegramError("Message to delete not found")
        _handle_telegram_error(e, "test context")
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "DEBUG"

    def test_message_not_modified_logs_debug(self, caplog: Any) -> None:
        caplog.set_level(10)
        e = TelegramError("Message is not modified")
        _handle_telegram_error(e, "test context")
        assert caplog.records[0].levelname == "DEBUG"

    def test_other_error_logs_warning(self, caplog: Any) -> None:
        caplog.set_level(10)
        e = TelegramError("Some other error")
        _handle_telegram_error(e, "test context")
        assert caplog.records[0].levelname == "WARNING"

    def test_error_message_in_context(self, caplog: Any) -> None:
        caplog.set_level(10)
        e = TelegramError("Message to delete not found")
        _handle_telegram_error(e, "my_context")
        assert "my_context" in caplog.records[0].message


# ───────────────────────────── Cleanup_previous_menu ─────────────────────────────

@pytest.fixture
def cleanup_context() -> Any:
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.bot.delete_message = AsyncMock()
    return ctx


class TestCleanupPreviousMenu:
    @pytest.mark.asyncio
    async def test_no_user_service(self, cleanup_context: Any) -> None:
        with patch('tg_bot.di.get_from_context', return_value=None):
            result = await cleanup_previous_menu(cleanup_context, 123)
        assert result is None
        cleanup_context.bot.delete_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_registration_message_id(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=42)
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            result = await cleanup_previous_menu(cleanup_context, 123)
        assert result is None
        cleanup_context.bot.delete_message.assert_called_once_with(chat_id=123, message_id=42)

    @pytest.mark.asyncio
    async def test_with_prompt_msg_id(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=None)
        cleanup_context.user_data['prompt_msg_id'] = 99
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123)
        cleanup_context.bot.delete_message.assert_called_once_with(chat_id=123, message_id=99)

    @pytest.mark.asyncio
    async def test_exclude_id_skips(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=42)
        cleanup_context.user_data['prompt_msg_id'] = 99
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123, exclude_id=42)
        # Only Prompt_msg_id Should Be Deleted
        cleanup_context.bot.delete_message.assert_called_once_with(chat_id=123, message_id=99)

    @pytest.mark.asyncio
    async def test_exclude_id_allows_other_deletes(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=50)
        cleanup_context.user_data['prompt_msg_id'] = 99
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123, exclude_id=42)
        # Both Should Be Deleted Since Neither Matches Exclude_id=42
        assert cleanup_context.bot.delete_message.call_count == 2

    @pytest.mark.asyncio
    async def test_telegram_error_on_delete(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=42)
        cleanup_context.bot.delete_message.side_effect = TelegramError("Message to delete not found")
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123)
        # Should Not Raise

    @pytest.mark.asyncio
    async def test_unexpected_error_on_delete(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=42)
        cleanup_context.bot.delete_message.side_effect = Exception("unexpected")
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123)
        # Should Not Raise

    @pytest.mark.asyncio
    async def test_resets_anchor_when_no_exclude_id(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=42)
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123, exclude_id=None)
        user_service.save_registration_message_id.assert_called_once_with(123, None)
        assert 'prompt_msg_id' not in cleanup_context.user_data

    @pytest.mark.asyncio
    async def test_skips_reset_when_exclude_id_provided(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=42)
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123, exclude_id=999)
        user_service.save_registration_message_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_user_db_returns_none(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = None
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            result = await cleanup_previous_menu(cleanup_context, 123)
        assert result is None

    @pytest.mark.asyncio
    async def test_user_db_with_falsy_registration_id(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=0)
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            result = await cleanup_previous_menu(cleanup_context, 123)
        assert result is None
        cleanup_context.bot.delete_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_prompt_msg_id_after_deletion(self, cleanup_context: Any) -> None:
        user_service = AsyncMock()
        user_service.get_user.return_value = MagicMock(registration_message_id=None)
        cleanup_context.user_data['prompt_msg_id'] = 55
        with patch('tg_bot.di.get_from_context', return_value=user_service):
            await cleanup_previous_menu(cleanup_context, 123, exclude_id=None)
        assert 'prompt_msg_id' not in cleanup_context.user_data


# ───────────────────────────── Safe_delete_message ─────────────────────────────

class TestSafeDeleteMessage:
    @pytest.mark.asyncio
    async def test_success_returns_true(self) -> None:
        ctx = MagicMock()
        ctx.bot.delete_message = AsyncMock()
        result = await safe_delete_message(ctx, 123, 456)
        assert result is True
        ctx.bot.delete_message.assert_called_once_with(chat_id=123, message_id=456)

    @pytest.mark.asyncio
    async def test_telegram_error_returns_false(self) -> None:
        ctx = MagicMock()
        ctx.bot.delete_message = AsyncMock(side_effect=TelegramError("Message to delete not found"))
        result = await safe_delete_message(ctx, 123, 456)
        assert result is False

    @pytest.mark.asyncio
    async def test_general_exception_returns_false(self) -> None:
        ctx = MagicMock()
        ctx.bot.delete_message = AsyncMock(side_effect=Exception("boom"))
        result = await safe_delete_message(ctx, 123, 456)
        assert result is False

    @pytest.mark.asyncio
    async def test_telegram_error_other_returns_false(self) -> None:
        ctx = MagicMock()
        ctx.bot.delete_message = AsyncMock(side_effect=TelegramError("Some other error"))
        result = await safe_delete_message(ctx, 123, 456)
        assert result is False


# ───────────────────────────── Safe_update_ui ─────────────────────────────

@pytest.fixture
def mock_update() -> Any:
    update = MagicMock(spec=Update)
    update.effective_user.id = 123
    update.callback_query = None
    update.message = MagicMock()
    update.message.delete = AsyncMock()
    return update


@pytest.fixture
def mock_context() -> Any:
    context = MagicMock()
    mock_provider = MagicMock()
    mock_user_service = AsyncMock()
    mock_provider.get.return_value = mock_user_service
    context.di = mock_provider
    context.user_data = {}
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    context.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=999))
    context.bot.send_video = AsyncMock(return_value=MagicMock(message_id=888))
    context.bot.send_animation = AsyncMock(return_value=MagicMock(message_id=777))
    context.bot.delete_message = AsyncMock()
    return context


class TestSafeUpdateUI:
    @pytest.mark.asyncio
    async def test_send_message(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(mock_update, mock_context, "Hello")
        assert result == 999
        mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_deletes_old_message(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            await safe_update_ui(mock_update, mock_context, "Hello")
        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_message_telegram_error(self, mock_update: Any, mock_context: Any) -> None:
        mock_update.message.delete.side_effect = TelegramError("Message to delete not found")
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(mock_update, mock_context, "Hello")
        assert result == 999

    @pytest.mark.asyncio
    async def test_delete_message_unexpected_error(self, mock_update: Any, mock_context: Any) -> None:
        mock_update.message.delete.side_effect = Exception("unexpected")
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(mock_update, mock_context, "Hello")
        assert result == 999

    @pytest.mark.asyncio
    async def test_with_callback_query(self, mock_context: Any) -> None:
        update = MagicMock(spec=Update)
        update.effective_user.id = 123
        update.callback_query = MagicMock()
        update.callback_query.message = MagicMock()
        update.callback_query.message.delete = AsyncMock()
        update.message = None
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(update, mock_context, "Hello")
        assert result == 999
        update.callback_query.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_query_delete_error(self, mock_context: Any) -> None:
        update = MagicMock(spec=Update)
        update.effective_user.id = 123
        update.callback_query = MagicMock()
        update.callback_query.message = MagicMock()
        update.callback_query.message.delete = AsyncMock(
            side_effect=TelegramError("Message to delete not found")
        )
        update.message = None
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(update, mock_context, "Hello")
        assert result == 999

    @pytest.mark.asyncio
    async def test_callback_query_delete_unexpected_error(self, mock_context: Any) -> None:
        update = MagicMock(spec=Update)
        update.effective_user.id = 123
        update.callback_query = MagicMock()
        update.callback_query.message = MagicMock()
        update.callback_query.message.delete = AsyncMock(
            side_effect=Exception("unexpected")
        )
        update.message = None
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(update, mock_context, "Hello")
        assert result == 999

    @pytest.mark.asyncio
    async def test_updates_anchor(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            await safe_update_ui(mock_update, mock_context, "Hello")
        mock_context.di.get.return_value.save_registration_message_id.assert_called_once_with(123, 999)
        assert mock_context.user_data.get('last_global_menu_id') == 999

    @pytest.mark.asyncio
    async def test_with_photo_path(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            with patch('builtins.open', MagicMock()):
                result = await safe_update_ui(
                    mock_update, mock_context, "Photo caption",
                    photo_path=Path("/tmp/test.jpg")
                )
        assert result == 999
        mock_context.bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_photo_id(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(
                mock_update, mock_context, "Photo",
                photo_id="AgAC...",
                photo_type="photo"
            )
        assert result == 999
        mock_context.bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_video(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(
                mock_update, mock_context, "Video",
                photo_id="VID...",
                photo_type="video"
            )
        assert result == 888
        mock_context.bot.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_animation(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_update_ui(
                mock_update, mock_context, "Animation",
                photo_id="ANI...",
                photo_type="animation"
            )
        assert result == 777
        mock_context.bot.send_animation.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_exclude_id(self, mock_update: Any, mock_context: Any) -> None:
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()) as mock_cleanup:
            await safe_update_ui(
                mock_update, mock_context, "Hello",
                exclude_id=100
            )
        mock_cleanup.assert_called_once_with(mock_context, 123, exclude_id=999)

    @pytest.mark.asyncio
    async def test_with_reply_markup(self, mock_update: Any, mock_context: Any) -> None:
        markup = InlineKeyboardMarkup([[]])
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            await safe_update_ui(mock_update, mock_context, "Hello", reply_markup=markup)
        mock_context.bot.send_message.assert_called_once()


# ───────────────────────────── Safe_edit_ui ─────────────────────────────

@pytest.fixture
def mock_update_with_callback() -> Any:
    update = MagicMock(spec=Update)
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.message.message_id = 888
    update.callback_query.edit_message_text = AsyncMock()
    return update


class TestSafeEditUI:
    @pytest.mark.asyncio
    async def test_success(self, mock_update_with_callback: Any, mock_context: Any) -> None:
        result = await safe_edit_ui(mock_update_with_callback, mock_context, "Edited")
        assert result == 888
        mock_update_with_callback.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_telegram_error(self, mock_update_with_callback: Any, mock_context: Any) -> None:
        mock_update_with_callback.callback_query.edit_message_text = AsyncMock(
            side_effect=TelegramError("Message is not modified")
        )
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_edit_ui(mock_update_with_callback, mock_context, "Edited")
        assert result == 777

    @pytest.mark.asyncio
    async def test_fallback_on_general_exception(self, mock_update_with_callback: Any, mock_context: Any) -> None:
        mock_update_with_callback.callback_query.edit_message_text = AsyncMock(
            side_effect=Exception("edit failed")
        )
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=666))
        with patch('tg_bot.ui_helpers.cleanup_previous_menu', AsyncMock()):
            result = await safe_edit_ui(mock_update_with_callback, mock_context, "Edited")
        assert result == 666

    @pytest.mark.asyncio
    async def test_no_callback_returns_none(self, mock_context: Any) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await safe_edit_ui(update, mock_context, "Hello")
        assert result is None
