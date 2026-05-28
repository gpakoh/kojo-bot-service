"""Unit tests for tg_bot/handlers/ai_chat.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update

from tg_bot.models import UserStatus


def _make_user_service():
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=MagicMock(status=UserStatus.APPROVED))
    return svc


patch("tg_bot.decorators.get_from_context", return_value=_make_user_service()).start()

from tg_bot.handlers.ai_chat import (
    handle_ai_history,
    handle_back_to_router,
    handle_router_ask_ai,
    handle_router_support,
    start_ai_chat,
)


@pytest.fixture(autouse=True)
def _setup_user_service(mock_context):
    """Provide user_service for cleanup_previous_menu calls."""
    mock_context.bot_data['user_service'] = MagicMock()
    mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
    mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()


class TestStartAiChat:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await start_ai_chat(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context):
        cq = MagicMock()
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await start_ai_chat(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_sends_welcome_message(self, mock_user, mock_context):
        cq = MagicMock()
        cq.answer = AsyncMock()
        cq.message = MagicMock()
        cq.message.delete = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        user_svc.get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'] = user_svc
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.send_message.return_value = MagicMock(message_id=555)
        await start_ai_chat(update, mock_context)
        mock_context.bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_message_delete_error_handled(self, mock_user, mock_context):
        cq = MagicMock()
        cq.answer = AsyncMock()
        cq.message = MagicMock()
        cq.message.delete = AsyncMock(side_effect=ValueError("msg to delete not found"))
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        user_svc.get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'] = user_svc
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=555))
        await start_ai_chat(update, mock_context)
        cq.message.delete.assert_awaited_once()


class TestHandleAiHistory:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await handle_ai_history(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context):
        cq = MagicMock()
        cq.data = "ai_chat_history"
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await handle_ai_history(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_history(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "ai_chat_history"
        cq.answer = AsyncMock()
        edit = AsyncMock()
        cq.edit_message_text = edit
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        ai_service = MagicMock()
        ai_service.get_chat_history_paged = AsyncMock(return_value={"pages": ["История пуста."]})
        mock_context.bot_data['ai_comm_service'] = ai_service
        mock_context.bot_data['user_service'] = MagicMock()
        await handle_ai_history(update, mock_context)
        edit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_history_shows_pages(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "ai_chat_history"
        cq.answer = AsyncMock()
        edit = AsyncMock()
        cq.edit_message_text = edit
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        ai_service = MagicMock()
        ai_service.get_chat_history_paged = AsyncMock(
            return_value={"pages": ["Message 1", "Message 2"]}
        )
        mock_context.bot_data['ai_comm_service'] = ai_service
        mock_context.bot_data['user_service'] = MagicMock()
        await handle_ai_history(update, mock_context)
        edit.assert_awaited_once()


class TestHandleRouterAskAi:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await handle_router_ask_ai(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context):
        cq = MagicMock()
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await handle_router_ask_ai(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_pending_message_shows_error(self, mock_user, mock_context):
        cq = MagicMock()
        cq.edit_message_text = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        mock_context.user_data = {}
        await handle_router_ask_ai(update, mock_context)
        cq.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_pending_message_routes_to_ai(self, mock_user, mock_context):
        ai_service = MagicMock()
        ai_service.handle_ai_workflow = AsyncMock()
        cq = MagicMock()
        cq.edit_message_text = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        mock_context.user_data = {'pending_message_text': 'какой кофе выбрать?'}
        mock_context.bot_data['ai_comm_service'] = ai_service
        app_config = MagicMock()
        app_config.get = AsyncMock(return_value="false")
        mock_context.bot_data['app_config'] = app_config
        await handle_router_ask_ai(update, mock_context)
        ai_service.handle_ai_workflow.assert_awaited_once()


class TestHandleRouterSupport:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await handle_router_support(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context):
        cq = MagicMock()
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await handle_router_support(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_support_options(self, mock_user, mock_context):
        cq = MagicMock()
        cq.edit_message_text = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        order_service = MagicMock()
        order_service.get_last_active_order_for_user = AsyncMock(return_value=None)
        order_service.get_orders_by_user_id = AsyncMock(return_value=[])
        mock_context.bot_data['order_service'] = order_service
        await handle_router_support(update, mock_context)
        cq.edit_message_text.assert_awaited_once()


class TestHandleBackToRouter:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await handle_back_to_router(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_to_router(self, mock_user, mock_context):
        cq = MagicMock()
        cq.edit_message_text = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        mock_context.user_data = {'pending_message_text': 'test'}
        await handle_back_to_router(update, mock_context)
        cq.edit_message_text.assert_awaited_once()
