"""Unit tests for tg_bot/handlers/order_product_view.py."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update

from tg_bot.handlers.order_product_view import show_gallery_view, show_product_view


@pytest.fixture
def setup_ctx(mock_context, mock_product_service, mock_cart_service):
    mock_context.bot_data['product_service'] = mock_product_service
    mock_context.bot_data['cart_service'] = mock_cart_service
    mock_context.bot_data['favorite_service'] = MagicMock()
    mock_context.bot_data['favorite_service'].is_favorite = AsyncMock(return_value=False)
    mock_context.bot_data['user_service'] = MagicMock()
    mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
    return mock_context


class TestShowProductView:
    @pytest.mark.asyncio
    async def test_guard_query_none_and_product_id_none(self, setup_ctx, mock_user):
        """query is None and product_id is None -> ValueError caught -> shows_products_state."""
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = None
        result = await show_product_view(
            update, setup_ctx,
            show_product_list_fn=AsyncMock(return_value=42),
            handle_gallery_selection_fn=AsyncMock(),
            showing_products_state=42,
            viewing_product_state=99,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_product_not_found_returns_to_list(self, setup_ctx, mock_user):
        """product_service returns None -> calls show_product_list_fn."""
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = None
        setup_ctx.bot_data['product_service'].get_product_by_id = AsyncMock(return_value=None)
        show_list = AsyncMock(return_value=42)
        result = await show_product_view(
            update, setup_ctx,
            show_product_list_fn=show_list,
            handle_gallery_selection_fn=AsyncMock(),
            showing_products_state=42,
            viewing_product_state=99,
            product_id=999,
            category='test',
        )
        show_list.assert_awaited_once()
        assert result == 42

    @pytest.mark.asyncio
    async def test_shows_product_with_callback_data(self, setup_ctx, mock_user, mock_cart_service):
        """Parses product_id from callback data, shows product card."""
        cq = MagicMock()
        cq.data = "prod_sel_42_coffee"
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        cq.message = MagicMock()
        cq.message.photo = None
        cq.message.reply_markup = MagicMock()
        cq.message.reply_markup.inline_keyboard = []
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.effective_chat = MagicMock()
        update.effective_chat.id = 111
        update.callback_query = cq
        product = MagicMock()
        product.id = 42
        product.images = []
        product.name = "Test Coffee"
        product.variants = []
        product.short_description = "A test coffee"
        product.full_description = "Nice coffee with chocolate notes"
        product.chapters = []
        product.search_variants = ""
        setup_ctx.bot_data['product_service'].get_product_by_id = AsyncMock(return_value=product)
        setup_ctx.bot_data['cart_service'] = mock_cart_service
        result = await show_product_view(
            update, setup_ctx,
            show_product_list_fn=AsyncMock(),
            handle_gallery_selection_fn=AsyncMock(),
            showing_products_state=42,
            viewing_product_state=99,
        )
        cq.answer.assert_awaited_once()
        assert result == 99

    @pytest.mark.asyncio
    async def test_gallery_selecting_redirects(self, setup_ctx, mock_user):
        """user_data gallery_selecting -> handle_gallery_selection_fn is called."""
        cq = MagicMock()
        cq.data = "prod_sel_42_coffee"
        cq.answer = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        setup_ctx.user_data['gallery_selecting'] = True
        gallery_fn = AsyncMock(return_value=99)
        result = await show_product_view(
            update, setup_ctx,
            show_product_list_fn=AsyncMock(),
            handle_gallery_selection_fn=gallery_fn,
            showing_products_state=42,
            viewing_product_state=99,
        )
        gallery_fn.assert_awaited_once()
        assert result == 99


class TestShowGalleryView:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, setup_ctx):
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await show_gallery_view(update, setup_ctx, show_product_list_fn=AsyncMock(), showing_products_state=42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_no_gallery_state_falls_back_to_product_list(self, setup_ctx, mock_user):
        """No gallery_product_ids in user_data -> calls show_product_list_fn."""
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.effective_chat = MagicMock()
        update.effective_chat.id = 111
        update.callback_query = None
        show_list = AsyncMock(return_value=42)
        result = await show_gallery_view(update, setup_ctx, show_product_list_fn=show_list, showing_products_state=42)
        show_list.assert_awaited_once()
        assert result == 42

    @pytest.mark.asyncio
    async def test_with_gallery_state_renders_media(self, setup_ctx, mock_user, mock_cart_service):
        """Has gallery_product_ids -> renders gallery media."""
        product = MagicMock()
        product.id = 1
        product.name = "Gallery Coffee"
        product.images = []
        product.variants = []
        product.short_description = "Nice"
        product.full_description = "Great coffee"
        setup_ctx.bot_data['cart_service'] = mock_cart_service
        setup_ctx.bot_data['product_service'].get_product_by_id = AsyncMock(return_value=product)
        setup_ctx.bot_data['favorite_service'].is_favorite = AsyncMock(return_value=False)
        setup_ctx.user_data['gallery_product_ids'] = [1]
        setup_ctx.user_data['gallery_index'] = 0
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.effective_chat = MagicMock()
        update.effective_chat.id = 111
        update.callback_query = None
        result = await show_gallery_view(update, setup_ctx, show_product_list_fn=AsyncMock(), showing_products_state=42)
        assert result == 42
