"""Smoke tests for brew, gift, product view handlers."""
from typing import Any

from tg_bot.handlers.order_brew import (
    display_brewing_guide,
    get_brew_method_label,
    prepare_recipe_content,
    save_recipe_action,
    show_brewing_guide,
    show_brewing_methods_choice,
)
from tg_bot.handlers.order_gift import (
    handle_gift_choice,
    handle_gift_comment,
    handle_gift_skip,
    prompt_gift_choice,
    select_ai_gift_option,
)
from tg_bot.handlers.order_product_view import (
    handle_clear_product_action,
    handle_gallery_nav,
    handle_set_quantity_preset,
    show_product_view,
)


class TestBrewImports:
    def test_brew_handlers_import(self) -> Any:
        assert callable(show_brewing_methods_choice)
        assert callable(get_brew_method_label)
        assert callable(prepare_recipe_content)
        assert callable(display_brewing_guide)
        assert callable(show_brewing_guide)
        assert callable(save_recipe_action)


class TestGiftImports:
    def test_gift_handlers_import(self) -> Any:
        assert callable(prompt_gift_choice)
        assert callable(handle_gift_skip)
        assert callable(handle_gift_choice)
        assert callable(handle_gift_comment)
        assert callable(select_ai_gift_option)


class TestProductViewImports:
    def test_product_view_import(self) -> Any:
        assert callable(show_product_view)
        assert callable(handle_gallery_nav)
        assert callable(handle_set_quantity_preset)
        assert callable(handle_clear_product_action)
