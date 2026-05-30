from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tg_bot.handlers.info import (
    show_info_menu,
    toggle_edit_mode,
    show_item_options,
    move_item,
    start_add_page,
    handle_title_creation_input,
    handle_content_input,
    cancel_cms,
    info_cms_conversation,
    AWAITING_TITLE,
    AWAITING_CONTENT,
)
from tg_bot.keyboards import (
    CB_INFO_MENU,
    CB_PREFIX_INFO_GO,
    CB_PREFIX_INFO_ADD,
    CB_CMS_MODE_TOGGLE,
    CB_CMS_ITEM_OPTS,
    CB_CMS_MOVE_UP,
    CB_CMS_MOVE_DOWN,
)
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


@pytest.fixture
def staff_context(mock_context: MagicMock) -> MagicMock:
    container = MagicMock()
    user_svc = MagicMock()
    user_svc.get_user = AsyncMock(return_value=MagicMock(status="approved"))
    user_svc.has_staff_privileges = MagicMock(return_value=True)
    container.get.return_value = user_svc
    mock_context.di = container
    mock_context.bot_data["admin_ids"] = [1, 2]
    return mock_context


class TestToggleEditMode:
    @pytest.mark.asyncio
    async def test_flips_info_edit_mode(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        info_service.get_page.return_value = None
        info_service.get_children.return_value = []

        await toggle_edit_mode(mock_update, staff_context)

        assert staff_context.user_data.get("info_edit_mode") is True

    @pytest.mark.asyncio
    async def test_toggles_back_to_false(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        info_service.get_page.return_value = None
        info_service.get_children.return_value = []
        staff_context.user_data["info_edit_mode"] = True

        await toggle_edit_mode(mock_update, staff_context)

        assert staff_context.user_data.get("info_edit_mode") is False


class TestShowItemOptions:
    @pytest.mark.asyncio
    async def test_renders_options_for_a_page(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        mock_update.callback_query.data = f"{CB_CMS_ITEM_OPTS}1"
        mock_update.callback_query.message.photo = None

        info_service.get_page.return_value = {
            "id": 1, "title": "Контакты", "body_text": "Мы тут",
            "image_id": None, "parent_id": None,
        }
        info_service.get_children.return_value = [
            {"id": 1, "title": "Контакты", "body_text": "Мы тут", "image_id": None, "parent_id": None, "sort_order": 0},
        ]

        await show_item_options(mock_update, staff_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        text = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Контакты" in text

    @pytest.mark.asyncio
    async def test_returns_to_menu_when_page_deleted(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        mock_update.callback_query.data = f"{CB_CMS_ITEM_OPTS}99"

        info_service.get_page.return_value = None
        info_service.get_children.return_value = []

        await show_item_options(mock_update, staff_context)


class TestMoveItem:
    @pytest.mark.asyncio
    async def test_moves_page_up(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        mock_update.callback_query.data = f"{CB_CMS_MOVE_UP}1"
        mock_update.callback_query.message.photo = None

        info_service.get_page.return_value = {
            "id": 1, "title": "Контакты", "body_text": "Мы тут",
            "image_id": None, "parent_id": None,
        }
        info_service.get_children.return_value = []

        await move_item(mock_update, staff_context)

        info_service.move_page.assert_called_with(1, "up")


class TestCMSRegistration:
    @pytest.mark.asyncio
    async def test_cms_handlers_registerable(self) -> None:
        toggle_handler = CallbackQueryHandler(toggle_edit_mode, pattern=f"^{CB_CMS_MODE_TOGGLE}$")
        options_handler = CallbackQueryHandler(show_item_options, pattern=f"^{CB_CMS_ITEM_OPTS}")
        move_handler = CallbackQueryHandler(move_item, pattern=f"^{CB_CMS_MOVE_UP}|^{CB_CMS_MOVE_DOWN}")
        for handler in (toggle_handler, options_handler, move_handler):
            assert isinstance(handler, CallbackQueryHandler)
            assert callable(handler.callback)


@pytest.fixture
def message_update() -> MagicMock:
    upd = MagicMock(spec=Update)
    upd.effective_user = MagicMock()
    upd.effective_user.id = 123
    upd.effective_chat = MagicMock()
    upd.effective_chat.id = 123
    upd.callback_query = None
    upd.message = AsyncMock()
    upd.message.text = "Тестовая страница"
    upd.message.photo = None
    upd.message.caption = None
    upd.message.message_id = 200
    upd.message.delete = AsyncMock()
    return upd


class TestStartAddPage:
    @pytest.mark.asyncio
    async def test_starts_conversation_for_root(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        mock_update.callback_query.data = CB_PREFIX_INFO_ADD + "root"

        result = await start_add_page(mock_update, staff_context)

        assert result == AWAITING_TITLE
        assert staff_context.user_data["cms_action"] == "create"
        assert staff_context.user_data["cms_parent_id"] is None

    @pytest.mark.asyncio
    async def test_starts_conversation_for_child(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        mock_update.callback_query.data = CB_PREFIX_INFO_ADD + "5"

        result = await start_add_page(mock_update, staff_context)

        assert result == AWAITING_TITLE
        assert staff_context.user_data["cms_action"] == "create"
        assert staff_context.user_data["cms_parent_id"] == 5


class TestHandleTitleCreationInput:
    @pytest.mark.asyncio
    async def test_stores_title_and_asks_content(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        message_update.message.text = "О нас"

        result = await handle_title_creation_input(message_update, staff_context)

        assert result == AWAITING_CONTENT
        assert staff_context.user_data["cms_title"] == "О нас"

    @pytest.mark.asyncio
    async def test_rejects_empty_title(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        message_update.message.text = ""

        result = await handle_title_creation_input(message_update, staff_context)

        assert result == AWAITING_TITLE

    @pytest.mark.asyncio
    async def test_rejects_long_title(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        message_update.message.text = "A" * 101

        result = await handle_title_creation_input(message_update, staff_context)

        assert result == AWAITING_TITLE


class TestHandleContentInputCreate:
    @pytest.mark.asyncio
    async def test_creates_page_with_text(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        staff_context.user_data["cms_action"] = "create"
        staff_context.user_data["cms_title"] = "О нас"
        staff_context.user_data["cms_parent_id"] = None
        message_update.message.text = "Мы лучшая компания!"
        info_service.create_page = AsyncMock(return_value=1)

        result = await handle_content_input(message_update, staff_context)

        assert result == ConversationHandler.END
        info_service.create_page.assert_called_once_with(None, "О нас", "Мы лучшая компания!", None)
        assert "cms_action" not in staff_context.user_data
        assert "cms_title" not in staff_context.user_data
        assert "cms_parent_id" not in staff_context.user_data

    @pytest.mark.asyncio
    async def test_skips_content_when_skip_command(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        staff_context.user_data["cms_action"] = "create"
        staff_context.user_data["cms_title"] = "Пустая"
        staff_context.user_data["cms_parent_id"] = None
        message_update.message.text = "/skip"
        info_service.create_page = AsyncMock(return_value=2)

        result = await handle_content_input(message_update, staff_context)

        assert result == ConversationHandler.END
        info_service.create_page.assert_called_once_with(None, "Пустая", None, None)

    @pytest.mark.asyncio
    async def test_creates_page_with_photo(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        info_service = staff_context.bot_data["info_service"]
        staff_context.user_data["cms_action"] = "create"
        staff_context.user_data["cms_title"] = "Фото"
        staff_context.user_data["cms_parent_id"] = 3
        message_update.message.text = None
        message_update.message.caption = "Подпись к фото"
        message_update.message.photo = [MagicMock(), MagicMock()]
        message_update.message.photo[-1].file_id = "AgAAAfake123"
        info_service.create_page = AsyncMock(return_value=3)

        result = await handle_content_input(message_update, staff_context)

        assert result == ConversationHandler.END
        info_service.create_page.assert_called_once_with(3, "Фото", "Подпись к фото", "AgAAAfake123")


class TestCancelCMS:
    @pytest.mark.asyncio
    async def test_clears_user_data_message(self, message_update: MagicMock, staff_context: MagicMock) -> None:
        staff_context.user_data["cms_action"] = "create"
        staff_context.user_data["cms_title"] = "Test"

        result = await cancel_cms(message_update, staff_context)

        assert result == ConversationHandler.END
        assert "cms_action" not in staff_context.user_data
        assert "cms_title" not in staff_context.user_data

    @pytest.mark.asyncio
    async def test_clears_user_data_callback(self, mock_update: MagicMock, staff_context: MagicMock) -> None:
        staff_context.user_data["cms_action"] = "create"
        staff_context.user_data["cms_title"] = "Test"

        result = await cancel_cms(mock_update, staff_context)

        assert result == ConversationHandler.END
        assert "cms_action" not in staff_context.user_data


class TestCMSConversation:
    def test_conversation_has_required_states(self) -> None:
        assert AWAITING_TITLE in info_cms_conversation.states
        assert AWAITING_CONTENT in info_cms_conversation.states

    def test_conversation_has_entry_point(self) -> None:
        assert len(info_cms_conversation.entry_points) == 1
        handler = info_cms_conversation.entry_points[0]
        assert isinstance(handler, CallbackQueryHandler)
        assert callable(handler.callback)

    def test_conversation_has_title_handler(self) -> None:
        handlers = info_cms_conversation.states[AWAITING_TITLE]
        assert len(handlers) == 1
        h = handlers[0]
        assert isinstance(h, MessageHandler)
        assert callable(h.callback)

    def test_conversation_has_content_handler(self) -> None:
        handlers = info_cms_conversation.states[AWAITING_CONTENT]
        assert len(handlers) == 2
        msg_handler, skip_handler = handlers
        assert isinstance(msg_handler, MessageHandler)
        assert isinstance(skip_handler, CommandHandler)

    def test_conversation_has_cancel_fallback(self) -> None:
        assert len(info_cms_conversation.fallbacks) == 1
        handler = info_cms_conversation.fallbacks[0]
        assert isinstance(handler, CommandHandler)
        assert "cancel" in handler.commands
