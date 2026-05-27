"""Unit tests for tg_bot/handlers/order_cart.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Message, Update
from telegram.ext import ConversationHandler

from tg_bot.handlers.order_cart import (
    handle_cart_edit_action,
    handle_cart_interaction,
    handle_cart_preset_qty,
    show_cart,
    show_cart_quantity_grid,
)
from tg_bot.keyboards import (
    CB_CHECKOUT,
    CB_CLEAR_CART,
    CB_PREFIX_CART_DEC,
    CB_PREFIX_CART_DEL,
    CB_PREFIX_CART_INC,
    CB_PREFIX_CART_QTY_GRID,
    CB_PREFIX_CART_SET_QTY,
)


def _make_cq(data: str) -> MagicMock:
    cq = MagicMock(spec=CallbackQuery)
    cq.data = data
    cq.answer = AsyncMock()
    cq.edit_message_text = AsyncMock(return_value=MagicMock(spec=Message, message_id=200))
    cq.edit_message_reply_markup = AsyncMock()
    cq.message = MagicMock()
    cq.message.message_id = 100
    cq.message.delete = AsyncMock()
    cq.message.photo = None
    cq.message.document = None
    cq.message.reply_markup = None
    return cq


def _setup_show_cart_deps(mock_update: MagicMock, mock_context: MagicMock, mock_cart_service: MagicMock) -> None:
    mock_context.bot_data["cart_service"] = mock_cart_service
    mock_context.bot_data["user_service"] = MagicMock()
    mock_context.bot_data["user_service"].save_registration_message_id = AsyncMock()
    mock_context.bot_data["user_service"].get_user = AsyncMock(return_value=None)


async def _noop_fn(*args, **kwargs) -> int:
    return 42


async def _get_and_cache_all_products_fn(context) -> dict:
    return {}


class TestShowCart:
    CART_VIEW_STATE = 3

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.effective_user = MagicMock(id=123)
        mock_context.bot_data = {}
        result = await show_cart(update, mock_context, _get_and_cache_all_products_fn, _noop_fn, self.CART_VIEW_STATE)
        assert result == self.CART_VIEW_STATE

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = MagicMock(spec=CallbackQuery)
        cq.data = None
        cq.answer = AsyncMock()
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.bot_data = {}
        result = await show_cart(update, mock_context, _get_and_cache_all_products_fn, _noop_fn, self.CART_VIEW_STATE)
        assert result == self.CART_VIEW_STATE

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = MagicMock(spec=CallbackQuery)
        cq.data = "test"
        cq.answer = AsyncMock()
        update.callback_query = cq
        update.effective_user = None
        update.effective_chat = None
        mock_context.bot_data = {}
        result = await show_cart(update, mock_context, _get_and_cache_all_products_fn, _noop_fn, self.CART_VIEW_STATE)
        assert result == self.CART_VIEW_STATE

    @pytest.mark.asyncio
    async def test_guard_query_message_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = MagicMock(spec=CallbackQuery)
        cq.data = "test"
        cq.answer = AsyncMock()
        cq.message = None
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.bot_data = {}
        result = await show_cart(update, mock_context, _get_and_cache_all_products_fn, _noop_fn, self.CART_VIEW_STATE)
        assert result == self.CART_VIEW_STATE

    @pytest.mark.asyncio
    async def test_empty_cart_shows_empty_message(self, mock_context: MagicMock, mock_cart_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("view_cart")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_cart_service.get_cart = AsyncMock(return_value={})
        mock_cart_service.validate_cart = AsyncMock(return_value=(MagicMock(), None))
        _setup_show_cart_deps(update, mock_context, mock_cart_service)

        sent_msg = MagicMock()
        sent_msg.message_id = 200
        mock_context.bot.send_message = AsyncMock(return_value=sent_msg)

        result = await show_cart(update, mock_context, _get_and_cache_all_products_fn, _noop_fn, self.CART_VIEW_STATE)
        assert result == self.CART_VIEW_STATE
        call_text = mock_context.bot.send_message.call_args[1]["text"]
        assert "пуста" in call_text

    @pytest.mark.asyncio
    async def test_cart_with_items_shows_items_and_total(
        self, mock_context: MagicMock, mock_cart_service: MagicMock
    ) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("view_cart")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_cart_service.get_cart = AsyncMock(
            return_value={
                "1": {"product_id": 1, "name": "Эфиопия", "quantity": 2, "price": 500.0},
                "2": {"product_id": 2, "name": "Колумбия", "quantity": 1, "price": 450.0},
            }
        )
        mock_cart_service.validate_cart = AsyncMock(return_value=(MagicMock(), None))
        _setup_show_cart_deps(update, mock_context, mock_cart_service)

        sent_msg = MagicMock()
        sent_msg.message_id = 200
        mock_context.bot.send_message = AsyncMock(return_value=sent_msg)

        async def fake_products_fn(ctx) -> dict:
            p1 = MagicMock()
            p1.id = 1
            p1.name = "Эфиопия"
            p1.variants = [MagicMock(price="500.0")]
            p1.short_description = "Вкусный кофе"
            p2 = MagicMock()
            p2.id = 2
            p2.name = "Колумбия"
            p2.variants = [MagicMock(price="450.0")]
            p2.short_description = "Фруктовый"
            return {"1": p1, "2": p2}

        result = await show_cart(update, mock_context, fake_products_fn, _noop_fn, self.CART_VIEW_STATE)
        assert result == self.CART_VIEW_STATE
        call_text = mock_context.bot.send_message.call_args[1]["text"]
        assert "Эфиопия" in call_text
        assert "Колумбия" in call_text
        assert "Итого" in call_text
        assert "1450" in call_text


class TestHandleCartInteraction:
    CART_VIEW = 3
    DELIVERY_METHOD = 4

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.effective_user = None
        mock_context.bot_data = {}
        result = await handle_cart_interaction(update, mock_context, _noop_fn, self.CART_VIEW, self.DELIVERY_METHOD)
        assert result == self.CART_VIEW

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = _make_cq("test")
        update.effective_user = None
        update.effective_chat = None
        mock_context.bot_data = {}
        result = await handle_cart_interaction(update, mock_context, _noop_fn, self.CART_VIEW, self.DELIVERY_METHOD)
        assert result == self.CART_VIEW

    @pytest.mark.asyncio
    async def test_clear_cart_clears_and_shows_cart(
        self, mock_context: MagicMock, mock_cart_service: MagicMock
    ) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(CB_CLEAR_CART)
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data["cart_service"] = mock_cart_service
        mock_context.bot_data["settings_service"] = MagicMock()

        show_cart_fn = AsyncMock(return_value=99)

        result = await handle_cart_interaction(update, mock_context, show_cart_fn, self.CART_VIEW, self.DELIVERY_METHOD)
        assert result == 99
        mock_cart_service.clear_cart.assert_awaited_once_with(123)
        cq.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_checkout_with_valid_cart_returns_delivery_method(
        self, mock_context: MagicMock, mock_cart_service: MagicMock
    ) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(CB_CHECKOUT)
        cq.message.message_id = 100
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        val_result = MagicMock()
        val_result.name = "VALID"
        mock_cart_service.validate_cart = AsyncMock(return_value=(val_result, None))
        mock_cart_service.get_cart = AsyncMock(return_value={"1": {"product_id": 1, "quantity": 1}})
        mock_context.bot_data["cart_service"] = mock_cart_service
        settings_svc = MagicMock()
        settings_svc.get_setting = AsyncMock(return_value="false")
        mock_context.bot_data["settings_service"] = settings_svc
        mock_context.user_data = {}

        result = await handle_cart_interaction(update, mock_context, _noop_fn, self.CART_VIEW, self.DELIVERY_METHOD)
        assert result == self.DELIVERY_METHOD
        cq.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_checkout_empty_cart_stays_in_cart_view(
        self, mock_context: MagicMock, mock_cart_service: MagicMock
    ) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(CB_CHECKOUT)
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        val_result = MagicMock()
        val_result.name = "VALID"
        mock_cart_service.validate_cart = AsyncMock(return_value=(val_result, None))
        mock_cart_service.get_cart = AsyncMock(return_value={})
        mock_context.bot_data["cart_service"] = mock_cart_service
        settings_svc = MagicMock()
        settings_svc.get_setting = AsyncMock(return_value="false")
        mock_context.bot_data["settings_service"] = settings_svc

        result = await handle_cart_interaction(update, mock_context, _noop_fn, self.CART_VIEW, self.DELIVERY_METHOD)
        assert result == self.CART_VIEW
        cq.answer.assert_called_once()


class TestHandleCartEditAction:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.effective_user = None
        mock_context.bot_data = {}
        result = await handle_cart_edit_action(update, mock_context, _noop_fn, _noop_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = _make_cq("test")
        update.effective_user = None
        update.effective_chat = None
        mock_context.bot_data = {}
        result = await handle_cart_edit_action(update, mock_context, _noop_fn, _noop_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_inc_increments_quantity(self, mock_context: MagicMock, mock_cart_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_INC}_99")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_cart_service.get_cart = AsyncMock(return_value={"99": {"product_id": 99, "quantity": 2}})
        mock_context.bot_data["cart_service"] = mock_cart_service

        show_fn = AsyncMock(return_value=42)

        result = await handle_cart_edit_action(update, mock_context, _noop_fn, show_fn)
        assert result == 42
        mock_cart_service.update_item.assert_awaited_once_with(123, 99, 3)

    @pytest.mark.asyncio
    async def test_dec_decrements_quantity(self, mock_context: MagicMock, mock_cart_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_DEC}_99")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_cart_service.get_cart = AsyncMock(return_value={"99": {"product_id": 99, "quantity": 3}})
        mock_context.bot_data["cart_service"] = mock_cart_service

        show_fn = AsyncMock(return_value=42)

        result = await handle_cart_edit_action(update, mock_context, _noop_fn, show_fn)
        assert result == 42
        mock_cart_service.update_item.assert_awaited_once_with(123, 99, 2)

    @pytest.mark.asyncio
    async def test_dec_to_zero_calls_internal_remove(
        self, mock_context: MagicMock, mock_cart_service: MagicMock
    ) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_DEC}_99")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_cart_service.get_cart = AsyncMock(return_value={"99": {"product_id": 99, "quantity": 1}})
        mock_context.bot_data["cart_service"] = mock_cart_service

        internal_rm = AsyncMock(return_value=77)

        result = await handle_cart_edit_action(update, mock_context, internal_rm, _noop_fn)
        assert result == 77
        internal_rm.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_del_calls_internal_remove(self, mock_context: MagicMock, mock_cart_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_DEL}_99")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_cart_service.get_cart = AsyncMock(return_value={"99": {"product_id": 99, "quantity": 2}})
        mock_context.bot_data["cart_service"] = mock_cart_service

        internal_rm = AsyncMock(return_value=77)

        result = await handle_cart_edit_action(update, mock_context, internal_rm, _noop_fn)
        assert result == 77
        internal_rm.assert_awaited_once()


class TestShowCartQuantityGrid:
    CART_VIEW = 3

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        mock_context.bot_data = {}
        result = await show_cart_quantity_grid(update, mock_context, _noop_fn, self.CART_VIEW)
        assert result == self.CART_VIEW

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = _make_cq("test")
        update.effective_user = None
        update.effective_chat = None
        mock_context.bot_data = {}
        result = await show_cart_quantity_grid(update, mock_context, _noop_fn, self.CART_VIEW)
        assert result == self.CART_VIEW

    @pytest.mark.asyncio
    async def test_valid_callback_shows_grid(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_QTY_GRID}42")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data = {}

        result = await show_cart_quantity_grid(update, mock_context, _noop_fn, self.CART_VIEW)
        assert result == self.CART_VIEW
        cq.edit_message_reply_markup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_callback_calls_bad_callback_fn(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_QTY_GRID}not_an_int")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data = {}

        bad_cb = AsyncMock()

        result = await show_cart_quantity_grid(update, mock_context, bad_cb, self.CART_VIEW)
        assert result == self.CART_VIEW
        bad_cb.assert_awaited_once()


class TestHandleCartPresetQty:
    CART_VIEW = 3

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.effective_user = None
        mock_context.bot_data = {}
        result = await handle_cart_preset_qty(update, mock_context, _noop_fn, _noop_fn, self.CART_VIEW)
        assert result == self.CART_VIEW

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = _make_cq("test")
        update.effective_user = None
        update.effective_chat = None
        mock_context.bot_data = {}
        result = await handle_cart_preset_qty(update, mock_context, _noop_fn, _noop_fn, self.CART_VIEW)
        assert result == self.CART_VIEW

    @pytest.mark.asyncio
    async def test_valid_preset_updates_quantity(self, mock_context: MagicMock, mock_cart_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_SET_QTY}42_5")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data["cart_service"] = mock_cart_service

        show_fn = AsyncMock(return_value=42)

        result = await handle_cart_preset_qty(update, mock_context, _noop_fn, show_fn, self.CART_VIEW)
        assert result == 42
        mock_cart_service.update_item.assert_awaited_once_with(123, 42, 5)

    @pytest.mark.asyncio
    async def test_invalid_preset_calls_bad_callback(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_CART_SET_QTY}invalid")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data = {}

        bad_cb = AsyncMock()

        result = await handle_cart_preset_qty(update, mock_context, bad_cb, _noop_fn, self.CART_VIEW)
        assert result == self.CART_VIEW
        bad_cb.assert_awaited_once()
