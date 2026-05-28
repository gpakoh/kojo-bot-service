"""Unit tests for tg_bot/handlers/user_panel.py."""
import sys
from datetime import datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Message
from telegram.constants import ParseMode

# The @auth_guard() Decorator Fires At Module-import Time. We Must Replace
# The Function At The *source* (tg_bot.decorators) *before* User_panel Is
# Imported, Because User_panel Does `from Tg_bot.decorators Import Auth_guard`
# Which Copies The Reference Into Its Own Namespace At Import Time.
import tg_bot.decorators as _dec

_real_auth_guard = _dec.auth_guard
_dec.auth_guard = lambda **kwargs: lambda f: f  # no-op decorator

# Force A Fresh Import Of User_panel So @auth_guard() Sees Our No-op.
sys.modules.pop("tg_bot.handlers.user_panel", None)

try:
    from tg_bot.handlers.user_panel import (
        add_comment_to_order,
        delete_comment_of_order,
        handle_address_action,
        handle_logout_action,
        handle_support_routing,
        save_comment_to_order,
        send_or_edit_order_details,
        set_order_rating,
        show_address_details,
        show_logout_options,
        show_my_order_details,
        show_my_orders,
        show_user_addresses_list,
        show_user_settings,
        show_user_thread_history,
        start_order_rating,
    )
    from tg_bot.keyboards import (
        CB_PREFIX_ADDR_DEF,
        CB_PREFIX_ADDR_DEL,
        CB_PREFIX_ADDR_VIEW,
        CB_PREFIX_USER_CONTACT_SUPPORT,
        CB_PREFIX_USER_ORDER_DETAILS,
        CB_SUPPORT_CONSULTATION,
        CB_USER_DELETE_DATA,
        CB_USER_MY_ORDERS,
        CB_USER_RATE_ORDER_START,
        CB_USER_SET_RATING,
        CB_USER_VIEW_THREAD,
    )
    from tg_bot.models import Order, OrderStatus, SenderRole
finally:
    _dec.auth_guard = _real_auth_guard

# NOTE: Conversationhandler.end == -1 In Python-telegram-bot
_CONV_END = -1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cq():
    """A standard callback-query mock used by most handlers."""
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "dummy"
    cq.answer = AsyncMock()
    cq.edit_message_text = AsyncMock()
    cq.message = MagicMock(spec=Message)
    cq.message.message_id = 100
    cq.message.delete = AsyncMock()
    cq.message.photo = None
    cq.message.video = None
    return cq


@pytest.fixture
def mock_services(mock_context, mock_pool):
    """Seed mock_context.bot_data with fully-mocked services."""
    mock_context.bot_data["order_service"] = AsyncMock()
    mock_context.bot_data["order_service"].pool = mock_pool
    mock_context.bot_data["product_service"] = AsyncMock()
    mock_context.bot_data["product_service"].pool = mock_pool
    mock_context.bot_data["user_service"] = AsyncMock()
    mock_context.bot_data["address_service"] = AsyncMock()
    mock_context.bot_data["communication_service"] = AsyncMock()
    mock_context.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    sent_msg = MagicMock(spec=Message)
    sent_msg.message_id = 500
    mock_context.bot.send_message = AsyncMock(return_value=sent_msg)
    return mock_context


@pytest.fixture
def sample_order():
    return Order(
        id=42,
        user_id=123456,
        total_amount=1500.0,
        status=OrderStatus.PAID,
        delivery_type="courier",
        delivery_address="ул. Ленина, 1",
        delivery_price=300.0,
        is_gift=False,
        gift_comment=None,
        rating=None,
        rating_comment=None,
        created_at=datetime(2025, 1, 1, 12, 0),
    )


# ===================================================================
# Show_my_orders
# ===================================================================

class TestShowMyOrders:
    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await show_my_orders(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_orders_callback_flow(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = CB_USER_MY_ORDERS
        mock_services.bot_data["order_service"].get_orders_by_user_id = AsyncMock(return_value=[])

        await show_my_orders(mock_update, mock_services)

        mock_cq.answer.assert_awaited_once()
        mock_cq.edit_message_text.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "нет ни одного заказа" in text

    @pytest.mark.asyncio
    async def test_with_orders_sends_message(self, mock_update, mock_cq, mock_services, sample_order):
        mock_update.callback_query = mock_cq
        mock_cq.data = CB_USER_MY_ORDERS
        mock_services.bot_data["order_service"].get_orders_by_user_id = AsyncMock(
            return_value=[sample_order]
        )

        await show_my_orders(mock_update, mock_services)

        mock_cq.answer.assert_awaited_once()
        mock_cq.edit_message_text.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "Ваши заказы" in text

    @pytest.mark.asyncio
    async def test_no_query_sends_new_message(self, mock_update, mock_services):
        mock_update.callback_query = None
        mock_services.bot_data["order_service"].get_orders_by_user_id = AsyncMock(return_value=[])
        mock_services.bot_data["user_service"].save_registration_message_id = AsyncMock()

        with patch("tg_bot.handlers.user_panel.cleanup_previous_menu", AsyncMock()):
            await show_my_orders(mock_update, mock_services)

        mock_services.bot.send_message.assert_awaited_once()
        text = mock_services.bot.send_message.call_args[1]["text"]
        assert "нет ни одного заказа" in text


# ===================================================================
# Show_my_order_details
# ===================================================================

class TestShowMyOrderDetails:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await show_my_order_details(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await show_my_order_details(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_order_id(self, mock_update, mock_cq, mock_services, sample_order):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_PREFIX_USER_ORDER_DETAILS}42"
        mock_services.bot_data["order_service"].get_full_order_details = AsyncMock(
            return_value=(sample_order, [])
        )
        mock_services.bot_data["product_service"].pool.fetch = AsyncMock(return_value=[])
        mock_services.bot_data["communication_service"].check_order_has_messages = AsyncMock(
            return_value=False
        )

        await show_my_order_details(mock_update, mock_services)

        mock_cq.answer.assert_awaited_once()
        mock_services.bot.edit_message_text.assert_awaited_once()
        text = mock_services.bot.edit_message_text.call_args[1]["text"]
        assert "#42" in text


# ===================================================================
# Show_user_settings
# ===================================================================

class TestShowUserSettings:
    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await show_user_settings(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_with_query(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_services.bot_data["user_service"].save_registration_message_id = AsyncMock()

        with patch("tg_bot.handlers.user_panel.cleanup_previous_menu", AsyncMock()):
            await show_user_settings(mock_update, mock_services)

        mock_cq.answer.assert_awaited_once()
        mock_services.bot.send_message.assert_awaited_once()
        text = mock_services.bot.send_message.call_args[1]["text"]
        assert "Настройки" in text

    @pytest.mark.asyncio
    async def test_without_query(self, mock_update, mock_services):
        mock_update.callback_query = None
        mock_services.bot_data["user_service"].save_registration_message_id = AsyncMock()

        with patch("tg_bot.handlers.user_panel.cleanup_previous_menu", AsyncMock()):
            await show_user_settings(mock_update, mock_services)

        mock_services.bot.send_message.assert_awaited_once()
        text = mock_services.bot.send_message.call_args[1]["text"]
        assert "Настройки" in text


# ===================================================================
# Show_user_addresses_list
# ===================================================================

class TestShowUserAddressesList:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await show_user_addresses_list(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_addresses(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_services.bot_data["address_service"].get_addresses = AsyncMock(return_value=[])

        await show_user_addresses_list(mock_update, mock_services)

        mock_cq.answer.assert_awaited_once()
        mock_cq.edit_message_text.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "нет сохраненных адресов" in text

    @pytest.mark.asyncio
    async def test_with_addresses(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        addr = {
            "id": 1, "provider": "yandex", "is_default": True,
            "custom_name": "Дом", "address_text": "ул. Тестовая, 10",
            "point_id": "yandex_1",
        }
        mock_services.bot_data["address_service"].get_addresses = AsyncMock(return_value=[addr])

        await show_user_addresses_list(mock_update, mock_services)

        text = mock_cq.edit_message_text.call_args[0][0]
        assert "сохраненные адреса" in text


# ===================================================================
# Handle_logout_action
# ===================================================================

class TestHandleLogoutAction:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await handle_logout_action(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await handle_logout_action(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "some_data"
        mock_update.callback_query.answer = AsyncMock()
        result = await handle_logout_action(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_logout_only(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = "user_logout_only"
        mock_services.bot_data["user_service"].logout_user = AsyncMock()

        await handle_logout_action(mock_update, mock_services)

        mock_services.bot_data["user_service"].logout_user.assert_awaited_once_with(
            123456, clear_data=False
        )
        text = mock_cq.edit_message_text.call_args[1]["text"]
        assert "вышли из аккаунта" in text
        assert "очищена" not in text

    @pytest.mark.asyncio
    async def test_logout_with_clear_data(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = CB_USER_DELETE_DATA
        mock_services.bot_data["user_service"].logout_user = AsyncMock()

        await handle_logout_action(mock_update, mock_services)

        mock_services.bot_data["user_service"].logout_user.assert_awaited_once_with(
            123456, clear_data=True
        )
        text = mock_cq.edit_message_text.call_args[1]["text"]
        assert "очищена" in text


# ===================================================================
# Handle_support_routing
# ===================================================================

class TestHandleSupportRouting:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await handle_support_routing(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await handle_support_routing(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "some_data"
        mock_update.callback_query.answer = AsyncMock()
        result = await handle_support_routing(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_pending_message_calls_prompt(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = CB_SUPPORT_CONSULTATION

        with patch(
            "tg_bot.handlers.user_panel.prompt_user_for_message",
            AsyncMock(return_value=0),
        ) as mock_prompt:
            result = await handle_support_routing(mock_update, mock_services)
            assert result == 0
            mock_prompt.assert_awaited_once_with(mock_update, mock_services)

    @pytest.mark.asyncio
    async def test_consultation_flow(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = CB_SUPPORT_CONSULTATION
        mock_services.user_data["pending_message_text"] = "Hello support!"
        mock_thread = MagicMock()
        mock_thread.id = 99
        mock_services.bot_data["communication_service"].get_or_create_consultation_thread = AsyncMock(
            return_value=mock_thread
        )
        mock_services.bot_data["communication_service"].add_message_general = AsyncMock()

        await handle_support_routing(mock_update, mock_services)

        mock_services.bot_data["communication_service"].get_or_create_consultation_thread.assert_awaited_once_with(
            123456
        )
        mock_services.bot_data["communication_service"].add_message_general.assert_awaited_once_with(
            99, 123456, SenderRole.USER, "Hello support!"
        )
        mock_cq.edit_message_text.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "передано" in text

    @pytest.mark.asyncio
    async def test_order_support_flow(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_PREFIX_USER_CONTACT_SUPPORT}77"
        mock_services.user_data["pending_message_text"] = "Where is my order?"
        mock_thread = MagicMock()
        mock_thread.id = 88
        mock_services.bot_data["communication_service"].get_or_create_thread = AsyncMock(
            return_value=mock_thread
        )
        mock_services.bot_data["communication_service"].add_message_general = AsyncMock()

        await handle_support_routing(mock_update, mock_services)

        mock_services.bot_data["communication_service"].get_or_create_thread.assert_awaited_once_with(
            77
        )
        mock_services.bot_data["communication_service"].add_message_general.assert_awaited_once_with(
            88, 123456, SenderRole.USER, "Where is my order?"
        )

    @pytest.mark.asyncio
    async def test_thread_none_shows_error(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = CB_SUPPORT_CONSULTATION
        mock_services.user_data["pending_message_text"] = "msg"
        mock_services.bot_data["communication_service"].get_or_create_consultation_thread = AsyncMock(
            return_value=None
        )

        await handle_support_routing(mock_update, mock_services)

        mock_cq.answer.assert_called_with("Ошибка выбора линии поддержки.", show_alert=True)


# ===================================================================
# Show_logout_options
# ===================================================================

class TestShowLogoutOptions:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await show_logout_options(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_options(self, mock_update, mock_cq, mock_context):
        mock_update.callback_query = mock_cq

        await show_logout_options(mock_update, mock_context)

        mock_cq.answer.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "Выход из аккаунта" in text


# ===================================================================
# Add_comment_to_order
# ===================================================================

class TestAddCommentToOrder:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await add_comment_to_order(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await add_comment_to_order(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "user_add_comment_order_42"
        mock_update.callback_query.answer = AsyncMock()
        # Message Is None — Triggers Another Conversationhandler.end Early
        mock_update.callback_query.message = None
        result = await add_comment_to_order(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_normal_flow(self, mock_update, mock_cq, mock_context):
        mock_update.callback_query = mock_cq
        mock_cq.data = "user_add_comment_order_42"

        result = await add_comment_to_order(mock_update, mock_context)

        assert result == 0  # AWAITING_USER_MESSAGE
        mock_cq.answer.assert_awaited_once()
        mock_cq.edit_message_text.assert_awaited_once()
        assert mock_context.user_data["comment_order_id"] == 42
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "комментарий" in text


# ===================================================================
# Save_comment_to_order
# ===================================================================

class TestSaveCommentToOrder:
    @pytest.mark.asyncio
    async def test_guard_none_message(self, mock_update, mock_context):
        result = await save_comment_to_order(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_saves_order_comment(self, mock_update, mock_context, mock_pool):
        msg = MagicMock(spec=Message)
        msg.text = "  позвоните за час  "
        msg.message_id = 200
        msg.delete = AsyncMock()
        mock_update.message = msg
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 123456
        mock_context.user_data["comment_order_id"] = 42
        mock_context.user_data["last_order_details_msg_id"] = 300
        mock_context.bot_data["order_service"] = AsyncMock()
        mock_context.bot_data["order_service"].update_order_comment = AsyncMock()
        mock_context.bot_data["order_service"].pool = mock_pool

        with patch("tg_bot.handlers.user_panel.send_or_edit_order_details", AsyncMock()) as mock_send:
            result = await save_comment_to_order(mock_update, mock_context)

        assert result == _CONV_END
        mock_context.bot_data["order_service"].update_order_comment.assert_awaited_once_with(
            42, "позвоните за час"
        )
        mock_send.assert_awaited_once()
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_saves_rating_text(self, mock_update, mock_context, mock_pool):
        msg = MagicMock(spec=Message)
        msg.text = "  отличный кофе!  "
        msg.message_id = 201
        msg.delete = AsyncMock()
        mock_update.message = msg
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 123456
        mock_context.user_data["rating_order_id"] = 42
        mock_context.user_data["last_order_details_msg_id"] = 300
        mock_context.bot_data["order_service"] = AsyncMock()
        mock_context.bot_data["order_service"].pool = mock_pool

        with patch("tg_bot.handlers.user_panel.send_or_edit_order_details", AsyncMock()) as mock_send:
            result = await save_comment_to_order(mock_update, mock_context)

        assert result == _CONV_END
        mock_context.bot_data["order_service"].pool.acquire.assert_called_once()
        mock_send.assert_awaited_once()
        msg.delete.assert_awaited_once()


# ===================================================================
# Delete_comment_of_order
# ===================================================================

class TestDeleteCommentOfOrder:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await delete_comment_of_order(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await delete_comment_of_order(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "user_delete_comment_order_42"
        mock_update.callback_query.answer = AsyncMock()
        result = await delete_comment_of_order(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_deletes_and_updates(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = "user_delete_comment_order_42"
        mock_services.bot_data["order_service"].update_order_comment = AsyncMock()

        with patch("tg_bot.handlers.user_panel.send_or_edit_order_details", AsyncMock()) as mock_send:
            await delete_comment_of_order(mock_update, mock_services)

        mock_services.bot_data["order_service"].update_order_comment.assert_awaited_once_with(
            42, None
        )
        mock_cq.answer.assert_called_with("🗑️ Комментарий удален!", show_alert=False)
        mock_send.assert_awaited_once()


# ===================================================================
# Start_order_rating
# ===================================================================

class TestStartOrderRating:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await start_order_rating(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await start_order_rating(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "u_rate_start_42"
        mock_update.callback_query.answer = AsyncMock()
        result = await start_order_rating(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_normal_flow(self, mock_update, mock_cq):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_USER_RATE_ORDER_START}42"

        await start_order_rating(mock_update, mock_cq)

        mock_cq.answer.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "Оцените заказ" in text


# ===================================================================
# Set_order_rating
# ===================================================================

class TestSetOrderRating:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await set_order_rating(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await set_order_rating(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "u_set_rat_42_5"
        mock_update.callback_query.answer = AsyncMock()
        result = await set_order_rating(mock_update, mock_context)
        assert result == _CONV_END

    @pytest.mark.asyncio
    async def test_normal_flow(self, mock_update, mock_cq, mock_context, mock_pool):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_USER_SET_RATING}42_5"
        mock_context.bot_data["order_service"] = AsyncMock()
        mock_context.bot_data["order_service"].pool = mock_pool

        result = await set_order_rating(mock_update, mock_context)

        assert result == 0  # AWAITING_USER_MESSAGE
        mock_cq.answer.assert_awaited_once()
        mock_cq.edit_message_text.assert_awaited_once()
        assert mock_context.user_data["rating_order_id"] == 42
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "Спасибо за оценку" in text


# ===================================================================
# Handle_address_action
# ===================================================================

class TestHandleAddressAction:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await handle_address_action(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await handle_address_action(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_address(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_PREFIX_ADDR_DEL}5"
        mock_services.bot_data["address_service"].delete_address = AsyncMock()
        mock_services.bot_data["address_service"].get_addresses = AsyncMock(return_value=[])

        await handle_address_action(mock_update, mock_services)

        mock_services.bot_data["address_service"].delete_address.assert_awaited_once_with(
            5, 123456
        )

    @pytest.mark.asyncio
    async def test_set_default_address(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_PREFIX_ADDR_DEF}5"
        mock_services.bot_data["address_service"].set_default_address = AsyncMock()
        mock_services.bot_data["address_service"].get_addresses = AsyncMock(return_value=[])

        await handle_address_action(mock_update, mock_services)

        mock_services.bot_data["address_service"].set_default_address.assert_awaited_once_with(
            123456, 5
        )


# ===================================================================
# Show_address_details
# ===================================================================

class TestShowAddressDetails:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await show_address_details(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await show_address_details(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = "addr_view_5"
        mock_update.callback_query.answer = AsyncMock()
        result = await show_address_details(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_address_found(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_PREFIX_ADDR_VIEW}1"
        addr = {
            "id": 1, "provider": "yandex", "is_default": True,
            "custom_name": "Дом", "address_text": "ул. Тестовая, 10",
            "point_id": "yandex_1",
        }
        mock_services.bot_data["address_service"].get_addresses = AsyncMock(return_value=[addr])

        await show_address_details(mock_update, mock_services)

        mock_cq.answer.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "Дом" in text
        assert "Основной адрес" in text

    @pytest.mark.asyncio
    async def test_address_not_found_returns_to_list(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_PREFIX_ADDR_VIEW}999"
        mock_services.bot_data["address_service"].get_addresses = AsyncMock(return_value=[])

        await show_address_details(mock_update, mock_services)

        mock_cq.answer.assert_any_call(
            "Адрес не найден (возможно, удален).", show_alert=True
        )


# ===================================================================
# Show_user_thread_history
# ===================================================================

class TestShowUserThreadHistory:
    @pytest.mark.asyncio
    async def test_guard_none_query(self, mock_update, mock_context):
        result = await show_user_thread_history(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_none_query_data(self, mock_update, mock_context):
        mock_update.callback_query = MagicMock(spec=CallbackQuery)
        mock_update.callback_query.data = None
        mock_update.callback_query.answer = AsyncMock()
        result = await show_user_thread_history(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_thread(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_USER_VIEW_THREAD}42"
        mock_services.bot_data["communication_service"].get_thread_by_order_id = AsyncMock(
            return_value=None
        )

        await show_user_thread_history(mock_update, mock_services)

        mock_cq.edit_message_text.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "История сообщений" in text

    @pytest.mark.asyncio
    async def test_no_messages(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_USER_VIEW_THREAD}42"
        mock_thread = MagicMock()
        mock_thread.id = 99
        mock_services.bot_data["communication_service"].get_thread_by_order_id = AsyncMock(
            return_value=mock_thread
        )
        mock_services.bot_data["communication_service"].get_messages_for_thread = AsyncMock(
            return_value=[]
        )

        await show_user_thread_history(mock_update, mock_services)

        mock_cq.edit_message_text.assert_called_with("История сообщений пуста.")

    @pytest.mark.asyncio
    async def test_with_messages(self, mock_update, mock_cq, mock_services):
        mock_update.callback_query = mock_cq
        mock_cq.data = f"{CB_USER_VIEW_THREAD}42"
        mock_thread = MagicMock()
        mock_thread.id = 99
        mock_services.bot_data["communication_service"].get_thread_by_order_id = AsyncMock(
            return_value=mock_thread
        )
        msg = MagicMock()
        msg.sender_role = SenderRole.USER
        msg.text = "Привет!"
        msg.created_at = datetime(2025, 1, 1, 12, 0)
        mock_services.bot_data["communication_service"].get_messages_for_thread = AsyncMock(
            return_value=[msg]
        )

        await show_user_thread_history(mock_update, mock_services)

        mock_cq.edit_message_text.assert_awaited_once()
        text = mock_cq.edit_message_text.call_args[0][0]
        assert "Чат по заказу" in text


# ===================================================================
# Send_or_edit_order_details
# ===================================================================

class TestSendOrEditOrderDetails:
    @pytest.mark.asyncio
    async def test_guard_none_effective_user(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await send_or_edit_order_details(mock_update, mock_context, 42)
        assert result is None

    @pytest.mark.asyncio
    async def test_order_not_found(self, mock_update, mock_services):
        mock_services.bot_data["order_service"].get_full_order_details = AsyncMock(return_value=[])

        result = await send_or_edit_order_details(mock_update, mock_services, 42)
        assert result is None

    @pytest.mark.asyncio
    async def test_edits_existing_message(self, mock_update, mock_cq, mock_services, sample_order):
        mock_update.callback_query = mock_cq
        mock_services.bot_data["order_service"].get_full_order_details = AsyncMock(
            return_value=[sample_order, []]
        )
        mock_services.bot_data["product_service"].pool.fetch = AsyncMock(return_value=[])
        mock_services.bot_data["communication_service"].check_order_has_messages = AsyncMock(
            return_value=False
        )

        await send_or_edit_order_details(mock_update, mock_services, 42)

        mock_services.bot.edit_message_text.assert_awaited_once()
        text = mock_services.bot.edit_message_text.call_args[1]["text"]
        assert "Детали Заказа" in text
        assert "1500" in text

    @pytest.mark.asyncio
    async def test_force_msg_id(self, mock_update, mock_services, sample_order):
        mock_update.callback_query = None
        mock_services.bot_data["order_service"].get_full_order_details = AsyncMock(
            return_value=[sample_order, []]
        )
        mock_services.bot_data["product_service"].pool.fetch = AsyncMock(return_value=[])
        mock_services.bot_data["communication_service"].check_order_has_messages = AsyncMock(
            return_value=False
        )

        await send_or_edit_order_details(mock_update, mock_services, 42, force_msg_id=999)

        mock_services.bot.edit_message_text.assert_awaited_once_with(
            chat_id=123456,
            message_id=999,
            text=ANY,
            reply_markup=ANY,
            parse_mode=ParseMode.HTML,
        )


# ===================================================================
# Send_or_edit_order_details — Fallback To Send_message
# ===================================================================

class TestSendOrEditOrderDetailsFallback:
    @pytest.mark.asyncio
    async def test_fallback_on_edit_error(self, mock_update, mock_cq, mock_services, sample_order):
        mock_update.callback_query = mock_cq
        mock_services.bot_data["order_service"].get_full_order_details = AsyncMock(
            return_value=[sample_order, []]
        )
        mock_services.bot_data["product_service"].pool.fetch = AsyncMock(return_value=[])
        mock_services.bot_data["communication_service"].check_order_has_messages = AsyncMock(
            return_value=False
        )
        mock_services.bot.edit_message_text = AsyncMock(side_effect=ValueError("edit failed"))

        await send_or_edit_order_details(mock_update, mock_services, 42)

        mock_services.bot.send_message.assert_awaited_once()
