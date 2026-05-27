"""Unit tests for tg_bot/handlers/favorites.py."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Update

from tg_bot.handlers.favorites import (
    STATE_HOME,
    remove_favorite_item,
    show_favorite_products,
    show_favorites_menu,
    toggle_favorite_in_card,
    toggle_notification,
    undo_remove_favorite,
)
from tg_bot.models import UserStatus


@pytest.fixture
def mock_cq() -> MagicMock:
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "action:42"
    cq.answer = AsyncMock()
    cq.edit_message_text = AsyncMock()
    cq.edit_message_reply_markup = AsyncMock()
    cq.message = MagicMock()
    cq.message.message_id = 100
    cq.message.photo = None
    cq.message.document = None
    return cq


@pytest.fixture
def mock_approved_user():
    user = MagicMock()
    user.id = 123456
    user.status = UserStatus.APPROVED
    return user


@pytest.fixture
def mock_user_service(mock_approved_user):
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=mock_approved_user)
    svc.save_registration_message_id = AsyncMock()
    return svc


@pytest.fixture
def mock_fav_service():
    svc = MagicMock()
    svc.get_user_favorites = AsyncMock(return_value=[])
    svc.get_favorites_count = AsyncMock(return_value=0)
    svc.get_saved_recipes = AsyncMock(return_value=[])
    svc.remove_favorite = AsyncMock()
    svc.add_favorite = AsyncMock()
    svc.toggle_favorite = AsyncMock()
    svc.get_notification_status = AsyncMock(return_value=False)
    svc.set_notification = AsyncMock()
    return svc


@pytest.fixture
def mock_product_service():
    svc = MagicMock()
    svc.get_product_by_id = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def mock_cart_service():
    svc = MagicMock()
    svc.get_cart = AsyncMock(return_value={})
    svc.add_item = AsyncMock()
    svc.remove_item = AsyncMock()
    svc.update_item = AsyncMock()
    return svc


def setup_guard(mock_update: MagicMock, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
    """Configure mocks so that the @auth_guard() decorator passes through."""
    mock_context.di = MagicMock()
    mock_context.di.get.return_value = mock_user_service


# ── Show_favorites_menu ─────────────────────────────────

class TestShowFavoritesMenu:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = None
        setup_guard(update, mock_context, mock_user_service)
        result = await show_favorites_menu(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_favorites(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
    ) -> None:
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['user_service'] = mock_user_service
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await show_favorites_menu(mock_update, mock_context)
        assert result == STATE_HOME

    @pytest.mark.asyncio
    async def test_with_favorites(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock,
    ) -> None:
        fav_svc = MagicMock()
        fav_svc.get_favorites_count = AsyncMock(return_value=3)
        fav_svc.get_saved_recipes = AsyncMock(return_value=[])
        mock_context.bot_data['favorite_service'] = fav_svc
        mock_context.bot_data['user_service'] = mock_user_service
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await show_favorites_menu(mock_update, mock_context)
        assert result == STATE_HOME

    @pytest.mark.asyncio
    async def test_with_callback_edits_message(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_cq: MagicMock,
    ) -> None:
        mock_update.callback_query = mock_cq
        fav_svc = MagicMock()
        fav_svc.get_favorites_count = AsyncMock(return_value=2)
        fav_svc.get_saved_recipes = AsyncMock(return_value=[])
        mock_context.bot_data['favorite_service'] = fav_svc
        mock_context.bot_data['user_service'] = mock_user_service
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await show_favorites_menu(mock_update, mock_context)
        assert result == STATE_HOME
        mock_cq.answer.assert_awaited_once()
        mock_cq.edit_message_text.assert_awaited_once()


# ── Show_favorite_products ──────────────────────────────

class TestShowFavoriteProducts:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.callback_query = None
        setup_guard(update, mock_context, mock_user_service)
        result = await show_favorite_products(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_favorites_shows_empty_message(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
    ) -> None:
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await show_favorite_products(mock_update, mock_context)
        assert result == STATE_HOME
        mock_context.bot.send_message.assert_awaited_once()
        call_text = mock_context.bot.send_message.await_args[0][1]
        assert "пуст" in call_text

    @pytest.mark.asyncio
    async def test_with_deleted_product(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
    ) -> None:
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        setup_guard(mock_update, mock_context, mock_user_service)
        deleted = MagicMock()
        deleted.id = 99
        result = await show_favorite_products(mock_update, mock_context, deleted_product=deleted)
        assert result == STATE_HOME


# ── Remove_favorite_item ────────────────────────────────

class TestRemoveFavoriteItem:
    @pytest.mark.asyncio
    async def test_guard_callback_query_none(self, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.effective_chat = MagicMock()
        update.effective_chat.id = 456
        update.callback_query = None
        setup_guard(update, mock_context, mock_user_service)
        result = await remove_favorite_item(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_removes_favorite(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_remove_42"
        mock_update.callback_query = mock_cq
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 456
        product = MagicMock()
        product.id = 42
        mock_product_service.get_product_by_id = AsyncMock(return_value=product)
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        mock_context.user_data = {'last_fav_list_msg_id': 200}
        mock_context.job_queue = MagicMock()
        mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
        mock_context.job_queue.run_repeating = MagicMock()
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await remove_favorite_item(mock_update, mock_context)
        assert result == STATE_HOME
        mock_fav_service.remove_favorite.assert_awaited_once_with(123456, 42)

    @pytest.mark.asyncio
    async def test_starts_undo_countdown(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_remove_7"
        mock_update.callback_query = mock_cq
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 456
        product = MagicMock()
        product.id = 7
        mock_product_service.get_product_by_id = AsyncMock(return_value=product)
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        mock_context.user_data = {'last_fav_list_msg_id': 200}
        mock_context.job_queue = MagicMock()
        mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
        mock_context.job_queue.run_repeating = MagicMock()
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await remove_favorite_item(mock_update, mock_context)
        assert result == STATE_HOME
        mock_context.job_queue.run_repeating.assert_called_once()


# ── Undo_remove_favorite ────────────────────────────────

class TestUndoRemoveFavorite:
    @pytest.mark.asyncio
    async def test_guard_callback_query_none(self, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.callback_query = None
        setup_guard(update, mock_context, mock_user_service)
        result = await undo_remove_favorite(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_restores_favorite_and_answers(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_undo_42"
        mock_update.callback_query = mock_cq
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        mock_context.job_queue = MagicMock()
        mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await undo_remove_favorite(mock_update, mock_context)
        assert result == STATE_HOME
        mock_fav_service.add_favorite.assert_awaited_once_with(123456, 42)
        mock_cq.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancels_existing_jobs(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_undo_42"
        mock_update.callback_query = mock_cq
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        existing_job = MagicMock()
        mock_context.job_queue = MagicMock()
        mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[existing_job])
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await undo_remove_favorite(mock_update, mock_context)
        assert result == STATE_HOME
        existing_job.schedule_removal.assert_called_once()


# ── Toggle_favorite_in_card ─────────────────────────────

class TestToggleFavoriteInCard:
    @pytest.mark.asyncio
    async def test_guard_callback_query_none(self, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.callback_query = None
        setup_guard(update, mock_context, mock_user_service)
        result = await toggle_favorite_in_card(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_toggles_favorite(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_toggle_42_espresso_nodet"
        mock_update.callback_query = mock_cq
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.user_data = {'view_mode': 'list'}
        setup_guard(mock_update, mock_context, mock_user_service)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr('tg_bot.handlers.order.show_product_view', AsyncMock(return_value=STATE_HOME))
            result = await toggle_favorite_in_card(mock_update, mock_context)
        assert result == STATE_HOME
        mock_fav_service.toggle_favorite.assert_awaited_once_with(123456, 42)
        mock_cq.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_toggle_in_gallery_mode(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_toggle_42_espresso_det"
        mock_update.callback_query = mock_cq
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.user_data = {'view_mode': 'gallery'}
        setup_guard(mock_update, mock_context, mock_user_service)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr('tg_bot.handlers.order.show_gallery_view', AsyncMock(return_value=STATE_HOME))
            result = await toggle_favorite_in_card(mock_update, mock_context)
        assert result == STATE_HOME
        mock_fav_service.toggle_favorite.assert_awaited_once_with(123456, 42)


# ── Toggle_notification ─────────────────────────────────

class TestToggleNotification:
    @pytest.mark.asyncio
    async def test_guard_callback_query_none(self, mock_context: MagicMock, mock_user_service: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.callback_query = None
        setup_guard(update, mock_context, mock_user_service)
        result = await toggle_notification(update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_toggles_notification_on(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_notify_42"
        mock_update.callback_query = mock_cq
        mock_fav_service.get_notification_status = AsyncMock(return_value=False)
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await toggle_notification(mock_update, mock_context)
        assert result == STATE_HOME
        mock_fav_service.set_notification.assert_awaited_once_with(123456, 42, True)

    @pytest.mark.asyncio
    async def test_toggles_notification_off(
        self, mock_update: MagicMock, mock_context: MagicMock,
        mock_user_service: MagicMock, mock_fav_service: MagicMock,
        mock_product_service: MagicMock, mock_cart_service: MagicMock,
        mock_cq: MagicMock,
    ) -> None:
        mock_cq.data = "fav_notify_42"
        mock_update.callback_query = mock_cq
        mock_fav_service.get_notification_status = AsyncMock(return_value=True)
        mock_context.bot_data['favorite_service'] = mock_fav_service
        mock_context.bot_data['product_service'] = mock_product_service
        mock_context.bot_data['cart_service'] = mock_cart_service
        setup_guard(mock_update, mock_context, mock_user_service)
        result = await toggle_notification(mock_update, mock_context)
        assert result == STATE_HOME
        mock_fav_service.set_notification.assert_awaited_once_with(123456, 42, False)
