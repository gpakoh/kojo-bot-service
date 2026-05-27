"""Unit tests for tg_bot/handlers/order_search_sort.py."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update

from tg_bot.handlers.order_search_sort import (
    apply_sort,
    handle_semantic_search,
    show_sort_menu,
    toggle_view,
)


@pytest.fixture
def setup_ctx(mock_context):
    mock_context.bot_data['user_service'] = MagicMock()
    mock_context.bot_data['user_service'].save_registration_message_id = AsyncMock()
    return mock_context


class TestToggleView:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, setup_ctx, mock_user):
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = None
        result = await toggle_view(update, setup_ctx, show_sort_menu_fn=AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = None
        cq.answer = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await toggle_view(update, setup_ctx, show_sort_menu_fn=AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, setup_ctx):
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = MagicMock()
        result = await toggle_view(update, setup_ctx, show_sort_menu_fn=AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_toggles_view_and_calls_show_sort_menu(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = "toggle_view_grid"
        cq.answer = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        show_sort = AsyncMock()
        await toggle_view(update, setup_ctx, show_sort_menu_fn=show_sort)
        cq.answer.assert_awaited_once()
        show_sort.assert_awaited_once()


class TestShowSortMenu:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, setup_ctx, mock_user):
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = None
        result = await show_sort_menu(update, setup_ctx, showing_products_state=42)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = None
        cq.message = MagicMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await show_sort_menu(update, setup_ctx, showing_products_state=42)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_message_none(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = "some_data"
        cq.message = None
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await show_sort_menu(update, setup_ctx, showing_products_state=42)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, setup_ctx):
        cq = MagicMock()
        cq.data = "some_data"
        cq.message = MagicMock()
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await show_sort_menu(update, setup_ctx, showing_products_state=42)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_photo_edits_message(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = "open_sort_menu"
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        cq.message = MagicMock()
        cq.message.photo = None
        cq.message.chat_id = 123
        cq.message.message_id = 100
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await show_sort_menu(update, setup_ctx, showing_products_state=42)
        assert result == 42
        cq.edit_message_text.assert_awaited_once()


class TestApplySort:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, setup_ctx, mock_user):
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = None
        result = await apply_sort(update, setup_ctx, show_sort_menu_fn=AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = None
        cq.answer = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        result = await apply_sort(update, setup_ctx, show_sort_menu_fn=AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, setup_ctx):
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = MagicMock()
        result = await apply_sort(update, setup_ctx, show_sort_menu_fn=AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_applies_sort_and_calls_show_sort_menu(self, setup_ctx, mock_user):
        cq = MagicMock()
        cq.data = "set_sort_price_asc"
        cq.answer = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = mock_user
        update.callback_query = cq
        show_sort = AsyncMock()
        result = await apply_sort(update, setup_ctx, show_sort_menu_fn=show_sort)
        assert result is not None
        cq.answer.assert_awaited_once()
        show_sort.assert_awaited_once()


class TestHandleSemanticSearch:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, setup_ctx):
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.callback_query = None
        result = await handle_semantic_search(
            update, setup_ctx,
            show_categories_fn=AsyncMock(), show_product_list_fn=AsyncMock(),
            showing_categories_state=42, awaiting_search_state=99,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, setup_ctx):
        cq = MagicMock()
        cq.data = None
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.callback_query = cq
        result = await handle_semantic_search(
            update, setup_ctx,
            show_categories_fn=AsyncMock(), show_product_list_fn=AsyncMock(),
            showing_categories_state=42, awaiting_search_state=99,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_guard_query_message_none(self, setup_ctx):
        cq = MagicMock()
        cq.data = "search_semantic_start"
        cq.message = None
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.callback_query = cq
        result = await handle_semantic_search(
            update, setup_ctx,
            show_categories_fn=AsyncMock(), show_product_list_fn=AsyncMock(),
            showing_categories_state=42, awaiting_search_state=99,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, setup_ctx):
        cq = MagicMock()
        cq.data = "search_semantic_start"
        cq.message = MagicMock()
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = cq
        result = await handle_semantic_search(
            update, setup_ctx,
            show_categories_fn=AsyncMock(), show_product_list_fn=AsyncMock(),
            showing_categories_state=42, awaiting_search_state=99,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_no_failed_query_shows_categories(self, setup_ctx):
        cq = MagicMock()
        cq.data = "search_semantic_start"
        cq.answer = AsyncMock()
        cq.message = MagicMock()
        cq.message.chat_id = 123
        cq.edit_message_text = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.callback_query = cq
        show_cat = AsyncMock(return_value=42)
        result = await handle_semantic_search(
            update, setup_ctx,
            show_categories_fn=show_cat, show_product_list_fn=AsyncMock(),
            showing_categories_state=42, awaiting_search_state=99,
        )
        show_cat.assert_awaited_once()
        assert result == 42
