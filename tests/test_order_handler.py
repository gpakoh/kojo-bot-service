"""Unit tests for tg_bot/handlers/order.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from tg_bot.handlers.order import (
    done,
    handle_order_created_actions,
    prompt_gift_choice,
    show_categories,
    show_product_list,
    start_user_order,
)
from tg_bot.models import UserStatus

SHOWING_CATEGORIES = 0
SHOWING_PRODUCTS = 1
ORDER_CREATED = 8


@pytest.fixture
def setup_auth(mock_context):
    """Configure context.di so auth_guard passes for an approved user."""
    mock_context.di = MagicMock()
    user_svc = MagicMock()
    user_svc.get_user = AsyncMock(
        return_value=MagicMock(status=UserStatus.APPROVED)
    )
    mock_context.di.get.return_value = user_svc


class TestStartUserOrder:
    @pytest.mark.asyncio
    async def test_guard_auth_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await start_user_order(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_deletes_incoming_message_and_starts(self, mock_update, mock_context, setup_auth):
        mock_update.message = MagicMock()
        mock_update.message.delete = AsyncMock()
        mock_context.bot_data['product_service'] = MagicMock()
        mock_context.bot_data['product_service'].get_category_tree = AsyncMock(return_value={})
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch(
            "tg_bot.handlers.order._get_and_cache_all_products",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.return_value = {}
            with patch(
                "tg_bot.handlers.order.get_category_keyboard",
                return_value=MagicMock(),
            ):
                result = await start_user_order(mock_update, mock_context)
                assert result == SHOWING_CATEGORIES
                assert mock_update.message.delete.await_count > 0


class TestShowCategories:
    @pytest.mark.asyncio
    async def test_guard_auth_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await show_categories(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_root_categories(self, mock_update, mock_context, setup_auth):
        mock_context.bot_data['product_service'] = MagicMock()
        mock_context.bot_data['product_service'].get_category_tree = AsyncMock(
            return_value={"Coffee": ["Espresso", "Filter"], "Tea": ["Green", "Black"]}
        )
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch(
            "tg_bot.handlers.order._get_and_cache_all_products",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.return_value = {}
            with patch(
                "tg_bot.handlers.order.get_category_keyboard",
                return_value=MagicMock(),
            ) as mock_keyboard:
                result = await show_categories(mock_update, mock_context)
                assert result == SHOWING_CATEGORIES
                mock_keyboard.assert_called_once()
                args, _ = mock_keyboard.call_args
                categories_arg = args[0]
                assert "Coffee" in categories_arg
                assert "Tea" in categories_arg
                mock_context.bot_data['product_service'].get_category_tree.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_selects_single_subcategory_directly(self, mock_update, mock_context, setup_auth):
        cq = MagicMock()
        cq.data = "cat_sel_Coffee"
        cq.answer = AsyncMock()
        cq.message = MagicMock()
        cq.message.photo = None
        cq.message.video = None
        cq.message.animation = None
        cq.edit_message_text = AsyncMock()
        cq.message.message_id = 1
        mock_update.callback_query = cq
        mock_context.bot_data['product_service'] = MagicMock()
        mock_context.bot_data['product_service'].get_category_tree = AsyncMock(
            return_value={"Coffee": ["Espresso"]}
        )
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch(
            "tg_bot.handlers.order._get_and_cache_all_products",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.return_value = {}
            with patch(
                "tg_bot.handlers.order.show_product_list",
                new_callable=AsyncMock,
            ) as mock_pl:
                mock_pl.return_value = SHOWING_PRODUCTS
                result = await show_categories(mock_update, mock_context)
                assert result == SHOWING_PRODUCTS


class TestShowProductList:
    @pytest.mark.asyncio
    async def test_guard_auth_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await show_product_list(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_products_in_category(self, mock_update, mock_context, setup_auth):
        mock_context.user_data['current_category'] = "Espresso"
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch(
            "tg_bot.handlers.order._get_and_cache_all_products",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.return_value = {
                1: MagicMock(
                    id=1, name="Product A",
                    chapters=["Espresso"],
                    variants=[MagicMock(price="100")],
                ),
            }
            with patch(
                "tg_bot.handlers.order.get_product_list_keyboard",
                return_value=MagicMock(),
            ) as mock_keyboard:
                result = await show_product_list(mock_update, mock_context)
                assert result == SHOWING_PRODUCTS
                mock_keyboard.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_all_products_when_category_all(self, mock_update, mock_context, setup_auth):
        mock_context.user_data['current_category'] = "all"
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch(
            "tg_bot.handlers.order._get_and_cache_all_products",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.return_value = {
                1: MagicMock(id=1, name="A", chapters=["Coffee"], variants=[MagicMock(price="50")]),
                2: MagicMock(id=2, name="B", chapters=["Tea"], variants=[MagicMock(price="30")]),
            }
            with patch(
                "tg_bot.handlers.order.get_product_list_keyboard",
                return_value=MagicMock(),
            ):
                result = await show_product_list(mock_update, mock_context)
                assert result == SHOWING_PRODUCTS


class TestPromptGiftChoice:
    @pytest.mark.asyncio
    async def test_shows_gift_selection(self, mock_update, mock_context):
        mock_update.effective_chat = MagicMock()
        mock_context.user_data['temp_delivery_data'] = {
            "delivery_type": "self_pickup",
            "delivery_price": 0.0,
            "delivery_address": "addr",
        }
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(return_value=None)
        mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=10))
        with patch(
            "tg_bot.handlers.order_gift.get_gift_choice_keyboard",
            return_value=MagicMock(),
        ) as mock_kb:
            with patch(
                "tg_bot.handlers.order.cleanup_previous_menu",
                new_callable=AsyncMock,
            ):
                result = await prompt_gift_choice(mock_update, mock_context)
                assert result == 6
                mock_kb.assert_called_once()


class TestDone:
    @pytest.mark.asyncio
    async def test_clears_user_data_returns_end(self, mock_update, mock_context):
        mock_context.user_data = {"some": "data", "temp": "value"}
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        result = await done(mock_update, mock_context)
        assert result == ConversationHandler.END
        assert mock_context.user_data == {}
        mock_update.message.reply_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_guard_no_message_raises_assertion(self, mock_update, mock_context):
        mock_update.message = None
        with pytest.raises(AssertionError):
            await done(mock_update, mock_context)


class TestHandleOrderCreatedActions:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_order_created_actions(mock_update, mock_context)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_cancel_order(self, mock_update, mock_context):
        cq = MagicMock()
        cq.data = "ord_act_cancel"
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        cq.message = MagicMock()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.user_data['current_active_order_id'] = 42
        mock_context.bot_data['order_service'] = MagicMock()
        mock_context.bot_data['order_service'].get_full_order_details = AsyncMock(
            return_value=(MagicMock(), [])
        )
        mock_context.bot_data['order_service'].cancel_order_with_reason = AsyncMock()
        with patch(
            "tg_bot.handlers.order_delivery_checkout.notify_admins_about_cancelled_order",
            new_callable=AsyncMock,
        ) as mock_notify:
            result = await handle_order_created_actions(mock_update, mock_context)
            assert result == ORDER_CREATED
            mock_context.bot_data['order_service'].cancel_order_with_reason.assert_awaited_once_with(
                42, "Отменен пользователем"
            )
            mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_change_delivery(self, mock_update, mock_context):
        cq = MagicMock()
        cq.data = "ord_act_change_dlv"
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        cq.message = MagicMock()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.user_data['current_active_order_id'] = 42
        order_service = MagicMock()
        order_service.get_full_order_details = AsyncMock(
            return_value=(
                MagicMock(),
                [MagicMock(product_id=1, quantity=2)],
            )
        )
        order_service.cancel_order_with_reason = AsyncMock()
        mock_context.bot_data['order_service'] = order_service
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].clear_cart = AsyncMock()
        mock_context.bot_data['cart_service'].update_item = AsyncMock()
        with patch(
            "tg_bot.handlers.order_delivery_checkout.get_delivery_method_keyboard",
            return_value=MagicMock(),
        ):
            result = await handle_order_created_actions(mock_update, mock_context)
            assert result == 4
            mock_context.bot_data['cart_service'].clear_cart.assert_awaited_once()
            mock_context.bot_data['cart_service'].update_item.assert_awaited_once_with(123456, 1, 2)
