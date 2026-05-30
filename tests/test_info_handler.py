from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from tg_bot.handlers.info import show_info_menu
from tg_bot.keyboards import CB_INFO_MENU, CB_PREFIX_INFO_GO
import telegram


@pytest.fixture()
def mock_context() -> MagicMock:
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.bot_data = {
        "info_service": AsyncMock(),
        "user_service": AsyncMock(),
    }
    ctx.user_data = {}
    ctx.bot = AsyncMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.send_photo = AsyncMock()
    ctx.bot.delete_message = AsyncMock()
    return ctx


@pytest.fixture
def mock_update() -> MagicMock:
    upd = MagicMock(spec=Update)
    upd.effective_user = MagicMock()
    upd.effective_user.id = 123
    upd.effective_chat = MagicMock()
    upd.effective_chat.id = 123
    upd.callback_query = AsyncMock()
    upd.callback_query.data = CB_INFO_MENU
    upd.callback_query.message = AsyncMock()
    upd.callback_query.message.message_id = 100
    upd.callback_query.message.photo = None
    upd.message = None
    return upd


class TestShowInfoMenu:
    @pytest.mark.asyncio
    async def test_shows_empty_state_when_no_pages(self, mock_update: MagicMock, mock_context: MagicMock) -> None:
        info_service = mock_context.bot_data["info_service"]
        info_service.get_page.return_value = None
        info_service.get_children.return_value = []

        await show_info_menu(mock_update, mock_context)

        text = mock_update.callback_query.edit_message_text.call_args[1]["text"]
        assert "Информационные страницы пока не добавлены" in text

    @pytest.mark.asyncio
    async def test_shows_root_pages_when_they_exist(self, mock_update: MagicMock, mock_context: MagicMock) -> None:
        info_service = mock_context.bot_data["info_service"]
        info_service.get_page.return_value = None
        info_service.get_children.return_value = [
            {"id": 1, "title": "О нас", "body_text": None, "image_id": None, "parent_id": None, "sort_order": 0},
            {"id": 2, "title": "Контакты", "body_text": "Мы тут", "image_id": "photo123", "parent_id": None, "sort_order": 1},
        ]

        await show_info_menu(mock_update, mock_context)

        assert mock_context.bot.send_message.called or mock_update.callback_query.edit_message_text.called

    @pytest.mark.asyncio
    async def test_renders_page_content(self, mock_update: MagicMock, mock_context: MagicMock) -> None:
        info_service = mock_context.bot_data["info_service"]
        mock_update.callback_query.data = f"{CB_PREFIX_INFO_GO}5"
        mock_update.callback_query.message.photo = None

        info_service.get_page.return_value = {
            "id": 5, "title": "Контакты", "body_text": "<b>Адрес:</b> ул. Примерная",
            "image_id": None, "parent_id": None,
        }
        info_service.get_children.return_value = []

        await show_info_menu(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        text = mock_update.callback_query.edit_message_text.call_args[1]["text"]
        assert "Контакты" in text
        assert "ул. Примерная" in text

    @pytest.mark.asyncio
    async def test_returns_to_root_on_info_menu(self, mock_update: MagicMock, mock_context: MagicMock) -> None:
        info_service = mock_context.bot_data["info_service"]
        mock_context.user_data["cms_current_view_id"] = 42
        mock_update.callback_query.data = CB_INFO_MENU

        info_service.get_children.return_value = []

        await show_info_menu(mock_update, mock_context)

        assert "cms_current_view_id" not in mock_context.user_data
        info_service.get_children.assert_called_with(None)

    @pytest.mark.asyncio
    async def test_tolerates_edit_failure(self, mock_update: MagicMock, mock_context: MagicMock) -> None:
        info_service = mock_context.bot_data["info_service"]
        info_service.get_page.return_value = None
        info_service.get_children.return_value = []

        mock_update.callback_query.message.photo = None
        mock_update.callback_query.edit_message_text.side_effect = telegram.error.TelegramError("edit failed")

        await show_info_menu(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handler_registration(self) -> None:
        handler = CallbackQueryHandler(show_info_menu, pattern=f"^{CB_INFO_MENU}$|^{CB_PREFIX_INFO_GO}")
        assert handler is not None
        assert callable(handler.callback)
