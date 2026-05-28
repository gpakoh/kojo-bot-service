"""Unit tests for tg_bot/handlers/order_delivery_checkout.py."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from tg_bot.handlers.order_delivery_checkout import (
    check_webapp_choice,
    choose_delivery_method,
    finalize_order_and_pay,
    handle_cdek_selection,
    handle_courier_selection,
    handle_pickup_point_choice,
    handle_self_pickup,
    handle_webapp_data,
    handle_yandex_selection,
    save_delivery_address_action,
)

DELIVERY_METHOD_STATE = 3
DELIVERY_WEBAPP_STATE = 4
ORDER_CREATED_STATE = 8


def _make_cq(data="test:data") -> MagicMock:
    cq = MagicMock()
    cq.data = data
    cq.answer = AsyncMock()
    cq.edit_message_text = AsyncMock()
    cq.edit_message_reply_markup = AsyncMock()
    cq.message = MagicMock()
    cq.message.message_id = 100
    return cq


class TestChooseDeliveryMethod:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await choose_delivery_method(
            mock_update, mock_context,
            show_cart_fn=MagicMock(),
            handle_self_pickup_fn=MagicMock(),
            handle_cdek_selection_fn=MagicMock(),
            handle_yandex_selection_fn=MagicMock(),
            delivery_back_callback="back",
            delivery_type_self_callback="self",
            delivery_type_pickup_callback="pickup",
            delivery_type_yandex_callback="yandex",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_guard_query_data_none_returns_end(self, mock_update, mock_context):
        cq = MagicMock()
        cq.data = None
        cq.message = MagicMock()
        mock_update.callback_query = cq
        result = await choose_delivery_method(
            mock_update, mock_context,
            show_cart_fn=MagicMock(),
            handle_self_pickup_fn=MagicMock(),
            handle_cdek_selection_fn=MagicMock(),
            handle_yandex_selection_fn=MagicMock(),
            delivery_back_callback="back",
            delivery_type_self_callback="self",
            delivery_type_pickup_callback="pickup",
            delivery_type_yandex_callback="yandex",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_back_callback_calls_show_cart(self, mock_update, mock_context):
        cq = _make_cq(data="go_back")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        show_cart_fn = AsyncMock(return_value=42)
        result = await choose_delivery_method(
            mock_update, mock_context,
            show_cart_fn=show_cart_fn,
            handle_self_pickup_fn=MagicMock(),
            handle_cdek_selection_fn=MagicMock(),
            handle_yandex_selection_fn=MagicMock(),
            delivery_back_callback="go_back",
            delivery_type_self_callback="self",
            delivery_type_pickup_callback="pickup",
            delivery_type_yandex_callback="yandex",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == 42
        show_cart_fn.assert_awaited_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_self_callback_calls_self_pickup(self, mock_update, mock_context):
        cq = _make_cq(data="pickup_self")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        handle_self_pickup_fn = AsyncMock(return_value=7)
        result = await choose_delivery_method(
            mock_update, mock_context,
            show_cart_fn=MagicMock(),
            handle_self_pickup_fn=handle_self_pickup_fn,
            handle_cdek_selection_fn=MagicMock(),
            handle_yandex_selection_fn=MagicMock(),
            delivery_back_callback="back",
            delivery_type_self_callback="pickup_self",
            delivery_type_pickup_callback="pickup",
            delivery_type_yandex_callback="yandex",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == 7
        handle_self_pickup_fn.assert_awaited_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_pickup_callback_calls_cdek(self, mock_update, mock_context):
        cq = _make_cq(data="cdek_sel")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        handle_cdek_selection_fn = AsyncMock(return_value=5)
        result = await choose_delivery_method(
            mock_update, mock_context,
            show_cart_fn=MagicMock(),
            handle_self_pickup_fn=MagicMock(),
            handle_cdek_selection_fn=handle_cdek_selection_fn,
            handle_yandex_selection_fn=MagicMock(),
            delivery_back_callback="back",
            delivery_type_self_callback="self",
            delivery_type_pickup_callback="cdek_sel",
            delivery_type_yandex_callback="yandex",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == 5
        handle_cdek_selection_fn.assert_awaited_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_yandex_callback_calls_yandex(self, mock_update, mock_context):
        cq = _make_cq(data="yandex_sel")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        handle_yandex_selection_fn = AsyncMock(return_value=6)
        result = await choose_delivery_method(
            mock_update, mock_context,
            show_cart_fn=MagicMock(),
            handle_self_pickup_fn=MagicMock(),
            handle_cdek_selection_fn=MagicMock(),
            handle_yandex_selection_fn=handle_yandex_selection_fn,
            delivery_back_callback="back",
            delivery_type_self_callback="self",
            delivery_type_pickup_callback="pickup",
            delivery_type_yandex_callback="yandex_sel",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == 6
        handle_yandex_selection_fn.assert_awaited_once_with(mock_update, mock_context)


class TestHandleSelfPickup:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_self_pickup(mock_update, mock_context, DELIVERY_METHOD_STATE)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_shows_active_pickup_points(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.bot_data['settings_service'] = MagicMock()
        mock_context.bot_data['settings_service'].get_setting = AsyncMock(
            return_value=json.dumps([
                {"name": "Point 1", "address": "Addr 1", "is_active": True, "schedule": "9-18"},
            ])
        )
        with patch("tg_bot.keyboards.get_pickup_points_keyboard") as mock_kb:
            mock_kb.return_value = MagicMock()
            result = await handle_self_pickup(mock_update, mock_context, DELIVERY_METHOD_STATE)
            assert result == DELIVERY_METHOD_STATE
            cq.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_active_points_shows_alert(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.bot_data['settings_service'] = MagicMock()
        mock_context.bot_data['settings_service'].get_setting = AsyncMock(
            return_value=json.dumps([
                {"name": "Inactive", "address": "Addr", "is_active": False},
            ])
        )
        result = await handle_self_pickup(mock_update, mock_context, DELIVERY_METHOD_STATE)
        assert result == DELIVERY_METHOD_STATE
        cq.answer.assert_awaited_once_with(
            "⚠️ К сожалению, сейчас нет доступных пунктов для самовывоза.",
            show_alert=True,
        )


class TestHandlePickupPointChoice:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_pickup_point_choice(
            mock_update, mock_context,
            pickup_point_select_callback="pp_",
            handle_self_pickup_fn=MagicMock(),
            finalize_pickup_choice_fn=MagicMock(),
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_valid_point_calls_finalize(self, mock_update, mock_context):
        cq = _make_cq(data="pp_0")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.bot_data['settings_service'] = MagicMock()
        mock_context.bot_data['settings_service'].get_setting = AsyncMock(
            return_value=json.dumps([
                {"name": "Point 1", "address": "Addr 1", "schedule": "9-18", "days": 1},
            ])
        )
        finalize_fn = AsyncMock(return_value=99)
        result = await handle_pickup_point_choice(
            mock_update, mock_context,
            pickup_point_select_callback="pp_",
            handle_self_pickup_fn=MagicMock(),
            finalize_pickup_choice_fn=finalize_fn,
        )
        assert result == 99
        finalize_fn.assert_awaited_once()
        point_arg = finalize_fn.call_args[0][2]
        assert point_arg["name"] == "Point 1"


class TestHandleCdekSelection:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_cdek_selection(
            mock_update, mock_context,
            get_and_cache_all_products_fn=MagicMock(),
            delivery_method_state=DELIVERY_METHOD_STATE,
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
            delivery_back_callback="back",
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_successful_init_returns_webapp_state(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        delivery_service = MagicMock()
        delivery_service.init_cdek_session_raw = AsyncMock(return_value="token123")
        delivery_service.map_url = "https://map.example.com"
        delivery_service.yandex_key = "key123"
        delivery_service.calculate_cart_weight = MagicMock(return_value=1.5)
        mock_context.bot_data['delivery_service'] = delivery_service
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['address_service'] = MagicMock()
        mock_context.bot_data['address_service'].get_default_address = AsyncMock(return_value=None)
        with patch("tg_bot.keyboards.get_webapp_keyboard") as mock_kb:
            mock_kb.return_value = MagicMock()
            result = await handle_cdek_selection(
                mock_update, mock_context,
                get_and_cache_all_products_fn=AsyncMock(return_value={}),
                delivery_method_state=DELIVERY_METHOD_STATE,
                delivery_webapp_state=DELIVERY_WEBAPP_STATE,
                delivery_back_callback="back",
            )
            assert result == DELIVERY_WEBAPP_STATE
            cq.edit_message_text.assert_awaited_once()


class TestHandleYandexSelection:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_yandex_selection(
            mock_update, mock_context,
            get_and_cache_all_products_fn=MagicMock(),
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_successful_init_returns_webapp_state(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        delivery_service = MagicMock()
        delivery_service.yandex_key = "key123"
        delivery_service.calculate_cart_weight = MagicMock(return_value=2.0)
        mock_context.bot_data['delivery_service'] = delivery_service
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        mock_context.bot_data['address_service'] = MagicMock()
        mock_context.bot_data['address_service'].get_default_address = AsyncMock(return_value=None)
        with patch("tg_bot.keyboards.get_webapp_keyboard") as mock_kb:
            mock_kb.return_value = MagicMock()
            with patch(
                "tg_bot.infrastructure.secrets_loader.SecretsLoader.get",
                return_value="https://widget.example.com",
            ):
                result = await handle_yandex_selection(
                    mock_update, mock_context,
                    get_and_cache_all_products_fn=AsyncMock(return_value={}),
                    delivery_webapp_state=DELIVERY_WEBAPP_STATE,
                )
                assert result == DELIVERY_WEBAPP_STATE
                cq.edit_message_text.assert_awaited_once()


class TestCheckWebappChoice:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await check_webapp_choice(
            mock_update, mock_context,
            finalize_order_and_pay_fn=MagicMock(),
            delivery_method_state=DELIVERY_METHOD_STATE,
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_no_token_shows_expired(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.user_data = {}
        result = await check_webapp_choice(
            mock_update, mock_context,
            finalize_order_and_pay_fn=MagicMock(),
            delivery_method_state=DELIVERY_METHOD_STATE,
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == DELIVERY_METHOD_STATE
        cq.edit_message_text.assert_awaited_once_with("Сессия истекла. Начните выбор заново.")

    @pytest.mark.asyncio
    async def test_got_choice_calls_finalize(self, mock_update, mock_context):
        cq = _make_cq(data="check_webapp_choice")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.user_data['cdek_token'] = "tok_123"
        delivery_service = MagicMock()
        delivery_service.get_user_choice = AsyncMock(
            return_value={"price": "350", "city_name": "Moscow", "address": "Lenina 1", "pvz_code": "PVZ001"}
        )
        mock_context.bot_data['delivery_service'] = delivery_service
        finalize_fn = AsyncMock(return_value=ORDER_CREATED_STATE)
        result = await check_webapp_choice(
            mock_update, mock_context,
            finalize_order_and_pay_fn=finalize_fn,
            delivery_method_state=DELIVERY_METHOD_STATE,
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == ORDER_CREATED_STATE
        finalize_fn.assert_awaited_once()
        kwargs = finalize_fn.call_args.kwargs
        assert kwargs['delivery_type'] == 'cdek_point'
        assert kwargs['delivery_price'] == 350.0


class TestHandleWebappData:
    @pytest.mark.asyncio
    async def test_no_webapp_data_returns_webapp_state(self, mock_update, mock_context):
        mock_update.message = MagicMock()
        mock_update.message.web_app_data = None
        result = await handle_webapp_data(
            mock_update, mock_context,
            prompt_gift_choice_fn=MagicMock(),
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == DELIVERY_WEBAPP_STATE

    @pytest.mark.asyncio
    async def test_no_message_returns_webapp_state(self, mock_update, mock_context):
        mock_update.message = None
        result = await handle_webapp_data(
            mock_update, mock_context,
            prompt_gift_choice_fn=MagicMock(),
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == DELIVERY_WEBAPP_STATE

    @pytest.mark.asyncio
    async def test_valid_cdek_data_calls_prompt_gift(self, mock_update, mock_context):
        webapp_data = MagicMock()
        webapp_data.data = json.dumps({
            "type": "cdek_point",
            "pvz_code": "PVZ001",
            "price": "350",
            "days": 2,
            "city_name": "Moscow",
            "address": "Lenina 1",
        })
        mock_update.message = MagicMock()
        mock_update.message.web_app_data = webapp_data
        mock_update.message.message_id = 50
        mock_update.message.delete = AsyncMock()
        mock_update.effective_chat = MagicMock()
        delivery_service = MagicMock()
        delivery_service.assembly_days = 1
        mock_context.bot_data['delivery_service'] = delivery_service
        prompt_fn = AsyncMock(return_value=99)
        result = await handle_webapp_data(
            mock_update, mock_context,
            prompt_gift_choice_fn=prompt_fn,
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == 99
        prompt_fn.assert_awaited_once()
        dd = prompt_fn.call_args[0][2]
        assert dd['delivery_type'] == 'cdek_point'
        assert dd['delivery_price'] == 350.0
        assert dd['delivery_point_id'] == 'PVZ001'
        mock_update.message.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_yandex_data_calls_prompt_gift(self, mock_update, mock_context):
        webapp_data = MagicMock()
        webapp_data.data = json.dumps({
            "type": "yandex_point",
            "pvz_code": "YNX002",
            "price": "500",
            "days": 3,
            "address": "Tverskaya 10",
        })
        mock_update.message = MagicMock()
        mock_update.message.web_app_data = webapp_data
        mock_update.message.message_id = 50
        mock_update.message.delete = AsyncMock()
        mock_update.effective_chat = MagicMock()
        delivery_service = MagicMock()
        delivery_service.assembly_days = 1
        mock_context.bot_data['delivery_service'] = delivery_service
        prompt_fn = AsyncMock(return_value=99)
        result = await handle_webapp_data(
            mock_update, mock_context,
            prompt_gift_choice_fn=prompt_fn,
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == 99
        prompt_fn.assert_awaited_once()
        dd = prompt_fn.call_args[0][2]
        assert dd['delivery_type'] == 'yandex_point'
        assert dd['delivery_price'] == 500.0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_end(self, mock_update, mock_context):
        webapp_data = MagicMock()
        webapp_data.data = "not-json"
        mock_update.message = MagicMock()
        mock_update.message.web_app_data = webapp_data
        mock_update.message.message_id = 50
        mock_update.message.delete = AsyncMock()
        mock_update.effective_chat = MagicMock()
        mock_context.bot.send_message = AsyncMock()
        delivery_service = MagicMock()
        delivery_service.assembly_days = 1
        mock_context.bot_data['delivery_service'] = delivery_service
        result = await handle_webapp_data(
            mock_update, mock_context,
            prompt_gift_choice_fn=MagicMock(),
            delivery_webapp_state=DELIVERY_WEBAPP_STATE,
        )
        assert result == ConversationHandler.END
        mock_context.bot.send_message.assert_awaited_once()


class TestFinalizeOrderAndPay:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none_returns_end(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await finalize_order_and_pay(
            mock_update, mock_context,
            delivery_type="self_pickup",
            delivery_price=0.0,
            delivery_address="addr",
            get_and_cache_all_products_fn=MagicMock(),
            send_order_success_message_fn=MagicMock(),
            order_created_state=ORDER_CREATED_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_empty_cart_returns_end(self, mock_update, mock_context):
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(return_value={})
        result = await finalize_order_and_pay(
            mock_update, mock_context,
            delivery_type="self_pickup",
            delivery_price=0.0,
            delivery_address="addr",
            get_and_cache_all_products_fn=MagicMock(),
            send_order_success_message_fn=MagicMock(),
            order_created_state=ORDER_CREATED_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_successful_order_creates_payment(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.bot_data['cart_service'] = MagicMock()
        mock_context.bot_data['cart_service'].get_cart = AsyncMock(
            side_effect=[
                {"1": {"price": "500", "quantity": 2}},
                None,
            ]
        )
        mock_context.bot_data['cart_service'].clear_cart = AsyncMock()
        mock_context.bot_data['order_service'] = MagicMock()
        created_order = MagicMock(id=42, total_amount=1000.0)
        mock_context.bot_data['order_service'].create_order = AsyncMock(return_value=created_order)
        mock_context.bot_data['order_service'].set_payment_url = AsyncMock()
        mock_context.bot_data['user_service'] = MagicMock()
        mock_context.bot_data['user_service'].get_user = AsyncMock(
            return_value=MagicMock(fio="Test User", registration_message_id=None)
        )
        mock_context.bot_data['payment_service'] = MagicMock()
        mock_context.bot_data['payment_service'].create_payment_url = AsyncMock(
            return_value="https://pay.example.com/order/42"
        )
        mock_context.bot_data['app_config'] = MagicMock()
        mock_context.bot_data['app_config'].get = AsyncMock(return_value=None)
        get_and_cache_all_products_fn = AsyncMock(return_value={1: MagicMock(id=1)})
        send_success_fn = AsyncMock()
        result = await finalize_order_and_pay(
            mock_update, mock_context,
            delivery_type="self_pickup",
            delivery_price=0.0,
            delivery_address="Test Address",
            get_and_cache_all_products_fn=get_and_cache_all_products_fn,
            send_order_success_message_fn=send_success_fn,
            order_created_state=ORDER_CREATED_STATE,
        )
        assert result == ORDER_CREATED_STATE
        mock_context.bot_data['order_service'].create_order.assert_awaited_once()
        mock_context.bot_data['payment_service'].create_payment_url.assert_awaited_once()
        send_success_fn.assert_awaited_once()


class TestSaveDeliveryAddressAction:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await save_delivery_address_action(
            mock_update, mock_context,
            save_delivery_address_callback="save_addr",
            order_created_state=ORDER_CREATED_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_no_order_id_returns_state(self, mock_update, mock_context):
        cq = _make_cq(data="save_addr")
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.user_data = {}
        result = await save_delivery_address_action(
            mock_update, mock_context,
            save_delivery_address_callback="save_addr",
            order_created_state=ORDER_CREATED_STATE,
        )
        assert result == ORDER_CREATED_STATE
        cq.answer.assert_awaited_once_with("Ошибка: заказ не найден в контексте.", show_alert=True)

    @pytest.mark.asyncio
    async def test_saves_address_successfully(self, mock_update, mock_context):
        cq = _make_cq(data="save_addr")
        cq.message.reply_markup = MagicMock()
        cq.message.reply_markup.inline_keyboard = [
            [MagicMock(callback_data="save_addr"), MagicMock(callback_data="other")],
        ]
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.user_data['current_active_order_id'] = 42
        mock_context.bot_data['order_service'] = MagicMock()
        delivery = MagicMock()
        delivery.point_id = "PVZ001"
        delivery.delivery_type = "cdek_point"
        delivery.address = "Lenina 1"
        delivery.info = None
        mock_context.bot_data['order_service'].get_full_order_details = AsyncMock(
            return_value=(MagicMock(delivery=delivery), [])
        )
        mock_context.bot_data['address_service'] = MagicMock()
        mock_context.bot_data['address_service'].add_address = AsyncMock()
        result = await save_delivery_address_action(
            mock_update, mock_context,
            save_delivery_address_callback="save_addr",
            order_created_state=ORDER_CREATED_STATE,
        )
        assert result == ORDER_CREATED_STATE
        mock_context.bot_data['address_service'].add_address.assert_awaited_once_with(
            user_id=123456,
            provider="cdek",
            point_id="PVZ001",
            address_text="Lenina 1",
            custom_name="ПВЗ Cdek",
        )
        cq.answer.assert_awaited_once_with("✅ Адрес успешно сохранен!", show_alert=True)


class TestHandleCourierSelection:
    @pytest.mark.asyncio
    async def test_guard_query_none_returns_end(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_courier_selection(
            mock_update, mock_context,
            delivery_back_callback="back",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_with_cities_shows_cities(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.bot_data['settings_service'] = MagicMock()
        mock_context.bot_data['settings_service'].get_setting = AsyncMock(
            return_value=json.dumps([
                {"name": "Moscow", "cost": "500"},
                {"name": "SPB", "cost": "400"},
            ])
        )
        with patch("tg_bot.keyboards.get_courier_cities_keyboard") as mock_kb:
            mock_kb.return_value = MagicMock()
            result = await handle_courier_selection(
                mock_update, mock_context,
                delivery_back_callback="back",
                delivery_method_state=DELIVERY_METHOD_STATE,
            )
            assert result == DELIVERY_METHOD_STATE
            cq.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_cities_shows_error(self, mock_update, mock_context):
        cq = _make_cq()
        mock_update.callback_query = cq
        mock_update.effective_chat = MagicMock()
        mock_context.bot_data['settings_service'] = MagicMock()
        mock_context.bot_data['settings_service'].get_setting = AsyncMock(return_value="[]")
        result = await handle_courier_selection(
            mock_update, mock_context,
            delivery_back_callback="back",
            delivery_method_state=DELIVERY_METHOD_STATE,
        )
        assert result == DELIVERY_METHOD_STATE
        cq.edit_message_text.assert_awaited_once()
        assert "не настроена" in cq.edit_message_text.call_args[0][0]
