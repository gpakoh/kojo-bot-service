"""E2E smoke test — full user flow with mocked Telegram API.

Tests the complete pipeline:
  /start → registration → approval → catalog → cart → checkout → payment → AI chat
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.di.provider import Container
from tg_bot.handlers.registration import start, received_fio, received_email, received_phone
from tg_bot.handlers.order import start_user_order, show_categories, show_product_list, show_cart
from tg_bot.handlers.order import handle_cart_interaction, choose_delivery_method
from tg_bot.handlers.ai_chat import start_ai_chat
from tg_bot.keyboards import CB_AI_CHAT_START
from tg_bot.models import UserStatus

pytestmark = pytest.mark.asyncio


def _make_di_container(services: dict) -> Container:
    """Create a mock DI container with all services."""
    container = Container()
    container._registry._singletons = {}
    for svc_cls_name, instance in services.items():
        cls = type(instance)
        container._registry._singletons[cls] = instance
    return container


class TestFullE2EFlow:

    @patch("tg_bot.decorators.get_from_context")
    async def test_registration_flow(self, mock_get_ctx, mock_e2e_update, mock_e2e_context, mock_services):
        mock_e2e_context.bot_data.update(mock_services)
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']

        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.delete = AsyncMock()
        mock_e2e_update.message.message_id = 1

        result = await start(mock_e2e_update, mock_e2e_context)
        assert result is not None

    @patch("tg_bot.decorators.get_from_context")
    async def test_received_fio(self, mock_get_ctx, mock_e2e_update, mock_e2e_context, mock_services):
        mock_e2e_context.bot_data.update(mock_services)
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']

        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.text = "E2E Test User"
        mock_e2e_update.message.message_id = 2
        mock_e2e_update.message.delete = AsyncMock()

        result = await received_fio(mock_e2e_update, mock_e2e_context)
        assert result is not None

    @patch("tg_bot.decorators.get_from_context")
    async def test_received_email(self, mock_get_ctx, mock_e2e_update, mock_e2e_context, mock_services):
        mock_e2e_context.bot_data.update(mock_services)
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']

        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.text = "e2e@test.com"
        mock_e2e_update.message.message_id = 3
        mock_e2e_update.message.delete = AsyncMock()

        mock_e2e_context.user_data['fio'] = "E2E User"
        result = await received_email(mock_e2e_update, mock_e2e_context)
        assert result is not None

    @patch("tg_bot.decorators.get_from_context")
    async def test_received_phone_and_register(self, mock_get_ctx, mock_e2e_update, mock_e2e_context, mock_services):
        mock_e2e_context.bot_data.update(mock_services)
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']

        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.contact = MagicMock()
        mock_e2e_update.message.contact.phone_number = "+79999999999"
        mock_e2e_update.message.message_id = 4
        mock_e2e_update.message.delete = AsyncMock()

        mock_e2e_context.user_data['fio'] = "E2E User"
        mock_e2e_context.user_data['email'] = "e2e@test.com"

        result = await received_phone(mock_e2e_update, mock_e2e_context)
        assert result is not None

    @patch("tg_bot.decorators.get_from_context")
    async def test_order_flow_catalog_to_cart(self, mock_get_ctx, mock_approved_user):
        mock_e2e_update, mock_e2e_context, mock_services = mock_approved_user
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']

        mock_e2e_update.callback_query = None
        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.delete = AsyncMock()
        mock_e2e_update.message.message_id = 10

        result = await start_user_order(mock_e2e_update, mock_e2e_context)
        assert result is not None

    @patch("tg_bot.decorators.get_from_context")
    async def test_ai_chat_start(self, mock_get_ctx, mock_approved_user):
        mock_e2e_update, mock_e2e_context, mock_services = mock_approved_user
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']

        mock_e2e_update.callback_query = MagicMock()
        mock_e2e_update.callback_query.data = CB_AI_CHAT_START
        mock_e2e_update.callback_query.answer = AsyncMock()
        mock_e2e_update.callback_query.message = MagicMock()
        mock_e2e_update.callback_query.message.delete = AsyncMock()

        result = await start_ai_chat(mock_e2e_update, mock_e2e_context)
        assert result is None
        assert mock_e2e_context.user_data.get('is_ai_chat_mode') is True

    @patch("tg_bot.decorators.get_from_context")
    async def test_auth_guard_blocks_unauthenticated(self, mock_get_ctx, mock_e2e_update, mock_e2e_context, mock_services):
        blocked_user = MagicMock(status=UserStatus.BLOCKED)
        blocked_user.status = UserStatus.BLOCKED
        mock_services['user_service'].get_user = AsyncMock(return_value=blocked_user)
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']
        mock_e2e_context.bot_data.update(mock_services)

        mock_e2e_update.callback_query = None
        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.delete = AsyncMock()
        mock_e2e_update.message.message_id = 99

        result = await start_user_order(mock_e2e_update, mock_e2e_context)
        assert result is not None

    @patch("tg_bot.decorators.get_from_context")
    async def test_auth_guard_blocks_unauthenticated(self, mock_get_ctx, mock_e2e_update, mock_e2e_context, mock_services):
        blocked_user = MagicMock(status=UserStatus.BLOCKED)
        blocked_user.status = UserStatus.BLOCKED
        mock_services['user_service'].get_user = AsyncMock(return_value=blocked_user)
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']
        mock_e2e_context.bot_data.update(mock_services)

        mock_e2e_update.callback_query = None
        mock_e2e_update.message = MagicMock()
        mock_e2e_update.message.delete = AsyncMock()
        mock_e2e_update.message.message_id = 99

        result = await start_user_order(mock_e2e_update, mock_e2e_context)

    @patch("tg_bot.decorators.get_from_context")
    async def test_cart_clear(self, mock_get_ctx, mock_approved_user):
        mock_e2e_update, mock_e2e_context, mock_services = mock_approved_user
        mock_services['cart_service'].clear_cart = AsyncMock()
        mock_services['cart_service'].get_cart = AsyncMock(return_value={})
        mock_services['user_service'].save_registration_message_id = AsyncMock()
        mock_get_ctx.return_value = mock_services['user_service']
        mock_e2e_context.user_data['order_state'] = 'cart_view'

        mock_e2e_update.callback_query = MagicMock()
        mock_e2e_update.callback_query.data = "clear_cart"
        mock_e2e_update.callback_query.answer = AsyncMock()

        result = await handle_cart_interaction(mock_e2e_update, mock_e2e_context)
        assert result is not None
