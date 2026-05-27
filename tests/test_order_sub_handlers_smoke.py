"""Smoke tests for order sub-handlers (cart + delivery_checkout)."""
from typing import Any


class TestOrderCartImports:
    def test_cart_handlers_import(self) -> Any:
        from tg_bot.handlers.order_cart import (
            handle_cart_edit_action,
            handle_cart_interaction,
            handle_cart_preset_qty,
            handle_cart_undo,
            show_cart,
            show_cart_edit_mode,
        )
        assert callable(show_cart)
        assert callable(show_cart_edit_mode)
        assert callable(handle_cart_edit_action)
        assert callable(handle_cart_interaction)
        assert callable(handle_cart_preset_qty)
        assert callable(handle_cart_undo)

    def test_cart_helpers_import(self) -> Any:
        from tg_bot.handlers.order_cart import (
            cart_countdown_job,
            clear_cart_undo_job,
            get_cart_text_and_total,
            internal_cart_remove,
            show_cart_quantity_grid,
        )
        assert callable(get_cart_text_and_total)
        assert callable(cart_countdown_job)
        assert callable(clear_cart_undo_job)
        assert callable(internal_cart_remove)
        assert callable(show_cart_quantity_grid)


class TestDeliveryCheckoutImports:
    def test_core_handlers_import(self) -> None:
        from tg_bot.handlers.order_delivery_checkout import (
            choose_delivery_method,
            finalize_order_and_pay,
            handle_order_created_actions,
            handle_self_pickup,
            save_delivery_address_action,
        )
        assert callable(choose_delivery_method)
        assert callable(finalize_order_and_pay)
        assert callable(handle_order_created_actions)
        assert callable(handle_self_pickup)
        assert callable(save_delivery_address_action)

    def test_delivery_selection_import(self) -> None:
        from tg_bot.handlers.order_delivery_checkout import (
            check_webapp_choice,
            handle_cdek_selection,
            handle_courier_city_choice,
            handle_courier_selection,
            handle_pickup_point_choice,
            handle_webapp_data,
            handle_yandex_selection,
            use_saved_address,
        )
        assert callable(check_webapp_choice)
        assert callable(handle_cdek_selection)
        assert callable(handle_courier_city_choice)
        assert callable(handle_courier_selection)
        assert callable(handle_pickup_point_choice)
        assert callable(handle_webapp_data)
        assert callable(handle_yandex_selection)
        assert callable(use_saved_address)
