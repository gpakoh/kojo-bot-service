"""Smoke tests for favorites, user panel, staff handlers."""



class TestFavoritesImports:
    def test_show_favorites_menu_import(self) -> None:
        from tg_bot.handlers.favorites import show_favorites_menu
        assert callable(show_favorites_menu)

    def test_show_favorite_products_import(self) -> None:
        from tg_bot.handlers.favorites import show_favorite_products
        assert callable(show_favorite_products)

    def test_toggle_favorite_import(self) -> None:
        from tg_bot.handlers.favorites import toggle_favorite_in_card
        assert callable(toggle_favorite_in_card)

    def test_undo_and_remove_import(self) -> None:
        from tg_bot.handlers.favorites import remove_favorite_item, undo_remove_favorite
        assert callable(undo_remove_favorite)
        assert callable(remove_favorite_item)


class TestUserPanelImports:
    def test_show_my_orders_import(self) -> None:
        from tg_bot.handlers.user_panel import show_my_order_details, show_my_orders
        assert callable(show_my_orders)
        assert callable(show_my_order_details)

    def test_user_settings_import(self) -> None:
        from tg_bot.handlers.user_panel import show_user_addresses_list, show_user_settings
        assert callable(show_user_settings)
        assert callable(show_user_addresses_list)

    def test_support_handlers_import(self) -> None:
        from tg_bot.handlers.user_panel import (
            handle_support_routing,
            prompt_user_for_message,
            show_user_thread_history,
        )
        assert callable(handle_support_routing)
        assert callable(show_user_thread_history)
        assert callable(prompt_user_for_message)

    def test_order_rating_import(self) -> None:
        from tg_bot.handlers.user_panel import set_order_rating, start_order_rating
        assert callable(start_order_rating)
        assert callable(set_order_rating)

    def test_logout_import(self) -> None:
        from tg_bot.handlers.user_panel import handle_logout_action, show_logout_options
        assert callable(show_logout_options)
        assert callable(handle_logout_action)


class TestStaffImports:
    def test_show_active_orders_import(self) -> None:
        from tg_bot.handlers.staff import show_active_orders_shortcut
        assert callable(show_active_orders_shortcut)

    def test_stats_and_profile_import(self) -> None:
        from tg_bot.handlers.staff import show_my_profile, show_stats
        assert callable(show_stats)
        assert callable(show_my_profile)

    def test_manual_sync_import(self) -> None:
        from tg_bot.handlers.staff import trigger_manual_sync
        assert callable(trigger_manual_sync)


class TestHelpersImports:
    def test_panel_internal_helpers(self) -> None:
        from tg_bot.handlers.user_panel import (
            _get_delivery_block,
            _get_payment_status_html,
            _get_rating_block,
        )
        assert callable(_get_payment_status_html)
        assert callable(_get_delivery_block)
        assert callable(_get_rating_block)

    def test_favorites_internal_helpers(self) -> None:
        from tg_bot.handlers.favorites import _get_fav_data
        assert callable(_get_fav_data)


class TestConversationHandlersExist:
    def test_support_handler_exists(self) -> None:
        from tg_bot.handlers.user_panel import user_support_handler
        assert user_support_handler is not None

    def test_cancellation_handler_exists(self) -> None:
        from tg_bot.handlers.user_panel import cancellation_handler
        assert cancellation_handler is not None

    def test_order_comment_handler_exists(self) -> None:
        from tg_bot.handlers.user_panel import order_comment_handler
        assert order_comment_handler is not None

    def test_rename_address_handler_exists(self) -> None:
        from tg_bot.handlers.user_panel import rename_address_handler
        assert rename_address_handler is not None
