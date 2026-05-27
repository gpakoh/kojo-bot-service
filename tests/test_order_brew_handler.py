"""Unit tests for tg_bot/handlers/order_brew.py."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update

from tg_bot.handlers.order_brew import (
    get_brew_method_label,
    save_recipe_action,
    show_brewing_guide,
    show_brewing_methods_choice,
)


class TestShowBrewingMethodsChoice:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await show_brewing_methods_choice(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(),
            brew_guide_callback="brew_",
            viewing_product_state=42,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = None
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await show_brewing_methods_choice(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(),
            brew_guide_callback="brew_",
            viewing_product_state=42,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_product_not_found(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "brew_123"
        cq.answer = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await show_brewing_methods_choice(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(return_value=None),
            brew_guide_callback="brew_",
            viewing_product_state=42,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_shows_brewing_methods(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "brew_123"
        cq.answer = AsyncMock()
        cq.edit_message_caption = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        product = MagicMock()
        product.name = "Эфиопия"
        product.chapters = ["coffee"]
        product.full_description = "test"
        result = await show_brewing_methods_choice(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(return_value=product),
            brew_guide_callback="brew_",
            viewing_product_state=42,
        )
        assert result == 42
        cq.edit_message_caption.assert_awaited_once()


class TestGetBrewMethodLabel:
    def test_espresso_label(self):
        assert get_brew_method_label("espresso") == "Эспрессо"

    def test_aeropress_label(self):
        assert get_brew_method_label("aeropress") == "Аэропресс"

    def test_v60_label(self):
        assert get_brew_method_label("v60") == "V60 (Воронка)"

    def test_unknown_returns_default(self):
        assert get_brew_method_label("unknown") == "Классический способ"


class TestShowBrewingGuide:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await show_brewing_guide(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(),
            get_brew_method_label_fn=MagicMock(),
            prepare_recipe_content_fn=AsyncMock(),
            display_brewing_guide_fn=AsyncMock(),
            brew_method_select_callback="bm_",
            prefix_select_product_callback="prod_",
            viewing_product_state=42,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = None
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await show_brewing_guide(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(),
            get_brew_method_label_fn=MagicMock(),
            prepare_recipe_content_fn=AsyncMock(),
            display_brewing_guide_fn=AsyncMock(),
            brew_method_select_callback="bm_",
            prefix_select_product_callback="prod_",
            viewing_product_state=42,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context):
        cq = MagicMock()
        cq.data = "bm_123_espresso"
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await show_brewing_guide(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(),
            get_brew_method_label_fn=MagicMock(),
            prepare_recipe_content_fn=AsyncMock(),
            display_brewing_guide_fn=AsyncMock(),
            brew_method_select_callback="bm_",
            prefix_select_product_callback="prod_",
            viewing_product_state=42,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_successful_flow(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "bm_1_espresso"
        cq.answer = AsyncMock()
        cq.edit_message_caption = AsyncMock()
        cq.edit_message_reply_markup = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        product = MagicMock()
        product.name = "Test"
        product.chapters = ["coffee"]
        product.full_description = "test"
        mock_context.bot_data['favorite_service'] = MagicMock()
        mock_context.bot_data['favorite_service'].is_recipe_saved = AsyncMock(return_value=False)

        display_fn = AsyncMock()
        result = await show_brewing_guide(
            update, mock_context,
            get_product_for_view_fn=AsyncMock(return_value=product),
            get_brew_method_label_fn=MagicMock(return_value="Эспрессо"),
            prepare_recipe_content_fn=AsyncMock(return_value="recipe text"),
            display_brewing_guide_fn=display_fn,
            brew_method_select_callback="bm_",
            prefix_select_product_callback="prod_",
            viewing_product_state=42,
        )
        assert result == 42
        cq.answer.assert_awaited_once()
        display_fn.assert_awaited_once()


class TestSaveRecipeAction:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        await save_recipe_action(update, mock_context, recipe_save_callback="save_")

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = None
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        await save_recipe_action(update, mock_context, recipe_save_callback="save_")

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context):
        cq = MagicMock()
        cq.data = "save_1"
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        await save_recipe_action(update, mock_context, recipe_save_callback="save_")

    @pytest.mark.asyncio
    async def test_no_recipe_data_shows_alert(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "save_1"
        cq.answer = AsyncMock()
        cq.edit_message_reply_markup = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        mock_context.user_data = {}
        await save_recipe_action(update, mock_context, recipe_save_callback="save_")
        cq.answer.assert_awaited_once_with(
            "⚠️ Ошибка: данные рецепта устарели. Попробуйте сгенерировать заново.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_saves_recipe_successfully(self, mock_user, mock_context):
        cq = MagicMock()
        cq.data = "save_1"
        cq.answer = AsyncMock()
        cq.edit_message_reply_markup = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        mock_context.user_data = {'last_generated_recipe': 'some recipe'}
        mock_context.bot_data['favorite_service'] = MagicMock()
        mock_context.bot_data['favorite_service'].save_recipe = AsyncMock()
        await save_recipe_action(update, mock_context, recipe_save_callback="save_")
        mock_context.bot_data['favorite_service'].save_recipe.assert_awaited_once_with(
            mock_user.id, 1, 'some recipe'
        )
        cq.answer.assert_awaited()
