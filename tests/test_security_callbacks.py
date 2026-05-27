from typing import Any
from unittest.mock import AsyncMock, MagicMock

from tg_bot.callback_validator import validate_callback
from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram
from tg_bot.schemas.callbacks import (
    AddressCallback,
    AIChatCallback,
    CartCallback,
    CategoryCallback,
    DeliveryCallback,
    FavoriteCallback,
    NavigationCallback,
    OrderCallback,
    ProductCallback,
    UserActionCallback,
    parse_callback_data,
)


class TestParseCallbackData:
    def test_product_callback_parsed(self) -> None:
        result = parse_callback_data("prod_sel_42")
        assert isinstance(result, ProductCallback)
        assert result.product_id == 42

    def test_add_to_cart_callback_parsed(self) -> None:
        result = parse_callback_data("add_to_cart_99")
        assert isinstance(result, ProductCallback)
        assert result.product_id == 99

    def test_category_callback_parsed(self) -> None:
        result = parse_callback_data("cat_sel_7")
        assert isinstance(result, CategoryCallback)
        assert result.category_id == 7

    def test_cart_increment_callback_parsed(self) -> None:
        result = parse_callback_data("c_inc_15")
        assert isinstance(result, CartCallback)
        assert result.action == "inc"
        assert result.product_id == 15

    def test_cart_decrement_callback_parsed(self) -> None:
        result = parse_callback_data("c_dec_3")
        assert isinstance(result, CartCallback)
        assert result.action == "dec"
        assert result.product_id == 3

    def test_cart_delete_callback_parsed(self) -> None:
        result = parse_callback_data("c_del_8")
        assert isinstance(result, CartCallback)
        assert result.action == "del"
        assert result.product_id == 8

    def test_cart_qty_grid_callback_parsed(self) -> None:
        result = parse_callback_data("c_q_grid_12")
        assert isinstance(result, CartCallback)
        assert result.action == "qty_grid"
        assert result.product_id == 12

    def test_fav_to_cart_callback_parsed(self) -> None:
        result = parse_callback_data("fav_to_cart_5")
        assert isinstance(result, FavoriteCallback)
        assert result.action == "to_cart"
        assert result.product_id == 5

    def test_fav_inc_callback_parsed(self) -> None:
        result = parse_callback_data("f_inc_10")
        assert isinstance(result, FavoriteCallback)
        assert result.action == "inc"
        assert result.product_id == 10

    def test_fav_qty_grid_callback_parsed(self) -> None:
        result = parse_callback_data("f_q_grid_20")
        assert isinstance(result, FavoriteCallback)
        assert result.action == "qty_grid"
        assert result.product_id == 20

    def test_user_order_details_parsed(self) -> None:
        result = parse_callback_data("user_order_details_77")
        assert isinstance(result, OrderCallback)
        assert result.order_id == 77

    def test_approve_user_callback_parsed(self) -> None:
        result = parse_callback_data("approve_100")
        assert isinstance(result, UserActionCallback)
        assert result.action == "approve"
        assert result.user_id == 100

    def test_decline_user_callback_parsed(self) -> None:
        result = parse_callback_data("decline_200")
        assert isinstance(result, UserActionCallback)
        assert result.action == "decline"
        assert result.user_id == 200

    def test_address_def_callback_parsed(self) -> None:
        result = parse_callback_data("addr_def_30")
        assert isinstance(result, AddressCallback)
        assert result.action == "def"
        assert result.address_id == 30

    def test_address_del_callback_parsed(self) -> None:
        result = parse_callback_data("addr_del_40")
        assert isinstance(result, AddressCallback)
        assert result.action == "del"
        assert result.address_id == 40

    def test_empty_data_returns_none(self) -> None:
        assert parse_callback_data("") is None

    def test_none_data_returns_none(self) -> None:
        assert parse_callback_data(None) is None

    def test_unknown_prefix_returns_none(self) -> None:
        assert parse_callback_data("unknown_prefix_123") is None

    def test_malformed_nan_suffix_cart(self) -> None:
        assert parse_callback_data("c_inc_abc") is None

    def test_zero_product_id_rejected(self) -> None:
        # Product_id Must Be > 0
        result = parse_callback_data("prod_sel_0")
        assert result is None

    def test_delivery_yandex_callback_parsed(self) -> None:
        result = parse_callback_data("delivery_yandex")
        assert isinstance(result, DeliveryCallback)
        assert result.delivery_type == "yandex"

    def test_delivery_pickup_callback_parsed(self) -> None:
        result = parse_callback_data("delivery_pickup")
        assert isinstance(result, DeliveryCallback)
        assert result.delivery_type == "pickup"

    def test_delivery_courier_callback_parsed(self) -> None:
        result = parse_callback_data("delivery_courier")
        assert isinstance(result, DeliveryCallback)
        assert result.delivery_type == "courier"

    def test_back_to_cat_callback_parsed(self) -> None:
        result = parse_callback_data("back_to_cat")
        assert isinstance(result, NavigationCallback)
        assert result.screen == "categories"

    def test_back_to_prod_list_callback_parsed(self) -> None:
        result = parse_callback_data("back_to_prod_list")
        assert isinstance(result, NavigationCallback)
        assert result.screen == "products"

    def test_ai_chat_history_callback_parsed(self) -> None:
        result = parse_callback_data("ai_chat_history")
        assert isinstance(result, AIChatCallback)
        assert result.action == "history"

    def test_ai_chat_start_callback_parsed(self) -> None:
        result = parse_callback_data("ai_chat_start")
        assert isinstance(result, AIChatCallback)
        assert result.action == "start"

    def test_unknown_delivery_type_returns_none(self) -> None:
        assert parse_callback_data("delivery_unknown") is None

    def test_back_to_unknown_screen_returns_none(self) -> None:
        assert parse_callback_data("back_to_nonexistent") is None

    def test_ai_chat_unknown_action_returns_none(self) -> None:
        assert parse_callback_data("ai_chat_unknown") is None

    def test_empty_suffix_no_data_returns_none(self) -> None:
        assert parse_callback_data("c_inc_") is None


class TestHtmlSanitizeRegistration:
    def test_fio_with_script_tag_stripped(self) -> None:
        malicious = "<script>alert(1)</script>Иванов"
        result = prepare_html_for_telegram(malicious)
        assert "script" not in result
        assert "Иванов" in result

    def test_fio_with_safe_html_preserved(self) -> None:
        malicious = "<b>Иванов</b>"
        result = prepare_html_for_telegram(malicious)
        assert "<b>Иванов</b>" in result

    def test_email_with_javascript_link_stripped(self) -> None:
        malicious = '<a href="javascript:alert(1)">click</a>'
        result = prepare_html_for_telegram(malicious)
        assert "javascript" not in result
        assert "click" in result

    def test_phone_with_event_handler_stripped(self) -> None:
        malicious = '<div onmouseover="evil()">+79991234567</div>'
        result = prepare_html_for_telegram(malicious)
        assert "onmouseover" not in result
        assert "+79991234567" in result

    def test_fio_with_html_entities_handled(self) -> None:
        malicious = "&#60;script&#62;"
        result = prepare_html_for_telegram(malicious)
        assert result is not None

    def test_email_with_markdown_link_converted(self) -> None:
        text = "[test](http://evil.com)"
        result = prepare_html_for_telegram(text)
        assert 'href="http://evil.com"' in result

    def test_normal_fio_passes_unchanged(self) -> None:
        normal = "Иванов Иван Иванович"
        result = prepare_html_for_telegram(normal)
        assert result == normal

    def test_normal_email_passes_unchanged(self) -> None:
        normal = "user@example.com"
        result = prepare_html_for_telegram(normal)
        assert result == normal

    def test_empty_text_returns_empty(self) -> None:
        assert prepare_html_for_telegram("") == ""

    def test_none_text_returns_empty(self) -> None:
        assert prepare_html_for_telegram(None) == ""


class TestValidateCallbackDecorator:
    def test_decorator_blocks_dangerous_callback(self) -> None:
        @validate_callback
        async def dummy_handler(update: Any, context: Any) -> str:
            return "handled"

        mock_update = MagicMock()
        mock_update.callback_query = MagicMock()
        mock_update.callback_query.data = "<script>alert(1)</script>"
        mock_update.callback_query.answer = AsyncMock()

        import asyncio
        result = asyncio.run(dummy_handler(mock_update, MagicMock()))
        assert result is None
        mock_update.callback_query.answer.assert_awaited_once()

    def test_decorator_passes_valid_callback(self) -> None:
        @validate_callback
        async def dummy_handler(update: Any, context: Any) -> str:
            return "handled"

        mock_update = MagicMock()
        mock_update.callback_query = MagicMock()
        mock_update.callback_query.data = "prod_sel_123"
        mock_update.callback_query.answer = AsyncMock()

        import asyncio
        result = asyncio.run(dummy_handler(mock_update, MagicMock()))
        assert result == "handled"

    def test_decorator_no_callback_query(self) -> None:
        @validate_callback
        async def dummy_handler(update: Any, context: Any) -> str:
            return "handled"

        mock_update = MagicMock()
        mock_update.callback_query = None

        import asyncio
        result = asyncio.run(dummy_handler(mock_update, MagicMock()))
        assert result == "handled"
