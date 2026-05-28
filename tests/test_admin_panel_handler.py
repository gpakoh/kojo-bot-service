"""Unit tests for tg_bot/handlers/admin_panel.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Message, Update

from tg_bot.domain.order import OrderStatus as DomainOrderStatus
from tg_bot.handlers.admin_panel import (
    admin_exit_to_main_menu,
    handle_user_action,
    panel_start,
    show_communication_center,
    show_courier_mgmt,
    show_logo_mgmt,
    show_order_details,
    show_order_list_by_status,
    show_orders_menu,
    show_pickup_mgmt,
    show_proxy_mgmt,
    show_settings_menu,
    show_user_details,
    show_users_menu,
    sync_products_button_action,
    toggle_auto_approve,
)
from tg_bot.models import UserRole, UserStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cq():
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "test_data"
    cq.answer = AsyncMock()
    cq.edit_message_text = AsyncMock()
    cq.edit_message_reply_markup = AsyncMock()
    cq.message = MagicMock()
    cq.message.message_id = 100
    cq.message.delete = AsyncMock()
    cq.message.chat_id = 123456
    cq.message.photo = None
    cq.message.video = None
    cq.message.animation = None
    return cq


@pytest.fixture
def admin_user_db():
    u = MagicMock()
    u.status = UserStatus.APPROVED
    u.role = UserRole.ADMIN
    u.telegram_id = 123456
    u.fio = "Admin User"
    u.phone = "+79000000000"
    u.email = "admin@test.com"
    u.registration_message_id = None
    u.id = 1
    u.created_at = None
    return u


@pytest.fixture
def admin_context(mock_context, admin_user_db):
    user_service = AsyncMock()
    user_service.get_user = AsyncMock(return_value=admin_user_db)
    user_service.get_user_by_db_id = AsyncMock(return_value=admin_user_db)
    user_service.has_staff_privileges.return_value = True
    user_service.get_users_by_criteria = AsyncMock(return_value=[admin_user_db])
    user_service.update_user_status_by_db_id = AsyncMock()
    user_service.update_user_role = AsyncMock()
    user_service.logout_user = AsyncMock()
    user_service.save_registration_message_id = AsyncMock()

    order_service = AsyncMock()
    order_service.get_order_counts_by_status = AsyncMock(return_value={})
    order_service.get_orders_by_statuses = AsyncMock(return_value=[])
    order_service.get_full_order_details = AsyncMock(return_value=None)

    settings_service = AsyncMock()
    settings_service.get_setting = AsyncMock(side_effect=lambda key, default="false": {
        "auto_approve_new_users": "false",
        "courier_enabled": "false",
        "courier_cities": "[]",
        "pickup_points": "[]",
        "registration_logo": None,
        "registration_logo_type": "photo",
    }.get(key, default))
    settings_service.set_setting = AsyncMock()

    comms_service = AsyncMock()
    comms_service.get_all_threads_sorted = AsyncMock(return_value=[])
    comms_service.get_messages_for_thread = AsyncMock(return_value=[])
    comms_service.get_or_create_thread_by_id = AsyncMock(return_value=None)

    mock_context.bot_data["user_service"] = user_service
    mock_context.bot_data["order_service"] = order_service
    mock_context.bot_data["settings_service"] = settings_service
    mock_context.bot_data["communication_service"] = comms_service
    mock_context.bot_data["notification_service"] = AsyncMock()
    mock_context.bot_data["admin_ids"] = [123456]
    mock_context.bot_data["db_pool"] = MagicMock()

    mock_context.di = MagicMock()
    mock_context.di.get = MagicMock(return_value=user_service)

    return mock_context


@pytest.fixture
def admin_update(mock_update, mock_cq):
    mock_update.callback_query = mock_cq
    return mock_update


@pytest.fixture
def panel_update(mock_user, mock_cq):
    update = MagicMock(spec=Update)
    update.effective_user = mock_user
    update.message = MagicMock(spec=Message)
    update.message.message_id = 200
    update.message.delete = AsyncMock()
    update.message.photo = None
    update.message.video = None
    update.message.animation = None
    update.callback_query = mock_cq
    return update


# ---------------------------------------------------------------------------
# Panel_start
# ---------------------------------------------------------------------------

class TestPanelStart:
    @pytest.mark.asyncio
    async def test_guard_message_is_none(self, mock_update, admin_context):
        mock_update.message = None
        result = await panel_start(mock_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, panel_update, admin_context):
        panel_update.effective_user = None
        result = await panel_start(panel_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_admin_main_menu(self, panel_update, admin_context):
        comms = admin_context.bot_data["communication_service"]
        comms.get_all_threads_sorted = AsyncMock(return_value=[MagicMock(is_read=False)])

        await panel_start(panel_update, admin_context)

        panel_update.callback_query.answer.assert_awaited_once()
        panel_update.callback_query.edit_message_text.assert_awaited_once()
        text = panel_update.callback_query.edit_message_text.call_args[0][0]
        assert "Панель управления" in text or "Панель" in text


# ---------------------------------------------------------------------------
# Show_users_menu
# ---------------------------------------------------------------------------

class TestShowUsersMenu:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await show_users_menu(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_users_menu_with_counts(self, admin_update, admin_context):
        await show_users_menu(admin_update, admin_context)

        admin_update.callback_query.answer.assert_awaited_once()
        admin_update.callback_query.edit_message_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Show_user_details
# ---------------------------------------------------------------------------

class TestShowUserDetails:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await show_user_details(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await show_user_details(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_user_details_with_override(self, admin_update, admin_context):
        await show_user_details(admin_update, admin_context, user_id_override=1)

        admin_update.callback_query.answer.assert_awaited_once()
        admin_update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shows_user_details_from_callback(self, admin_update, admin_context):
        admin_update.callback_query.data = "admin_user_details_1_approved"

        await show_user_details(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_not_found(self, admin_update, admin_context):
        admin_context.bot_data["user_service"].get_user_by_db_id = AsyncMock(return_value=None)

        await show_user_details(admin_update, admin_context, user_id_override=999)

        admin_update.callback_query.edit_message_text.assert_awaited_once_with(
            "Ошибка: пользователь не найден."
        )


# ---------------------------------------------------------------------------
# Handle_user_action
# ---------------------------------------------------------------------------

class TestHandleUserAction:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await handle_user_action(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await handle_user_action(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_user(self, admin_update, admin_context):
        admin_update.callback_query.data = "admin_user_action_approve_1"
        user_service = admin_context.bot_data["user_service"]

        await handle_user_action(admin_update, admin_context)

        user_service.update_user_status_by_db_id.assert_awaited_once_with(1, UserStatus.APPROVED)
        assert admin_update.callback_query.answer.awaited

    @pytest.mark.asyncio
    async def test_block_user(self, admin_update, admin_context):
        non_admin = MagicMock()
        non_admin.telegram_id = 999999
        non_admin.fio = "Test User"
        non_admin.phone = "+79001111111"
        non_admin.email = "user@test.com"
        non_admin.status = UserStatus.APPROVED
        non_admin.role = UserRole.USER
        non_admin.registration_message_id = 42
        non_admin.id = 2

        admin_context.bot_data["user_service"].get_user_by_db_id = AsyncMock(return_value=non_admin)
        admin_update.callback_query.data = "admin_user_action_block_2"

        await handle_user_action(admin_update, admin_context)

        admin_context.bot_data["user_service"].update_user_status_by_db_id.assert_awaited_once_with(2, UserStatus.BLOCKED)

    @pytest.mark.asyncio
    async def test_protection_guard_blocks_admin_actions(self, admin_update, admin_context):
        """Non-approve action on admin_ids member should be blocked."""
        admin_update.callback_query.data = "admin_user_action_block_1"

        await handle_user_action(admin_update, admin_context)

        admin_context.bot_data["user_service"].update_user_status_by_db_id.assert_not_called()
        admin_update.callback_query.answer.assert_called_with(
            "🛑 Критическая защита: Действия над владельцем системы запрещены.",
            show_alert=True,
        )


# ---------------------------------------------------------------------------
# Show_settings_menu
# ---------------------------------------------------------------------------

class TestShowSettingsMenu:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await show_settings_menu(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, admin_update, admin_context):
        admin_update.effective_user = None
        result = await show_settings_menu(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_settings_menu(self, admin_update, admin_context):
        await show_settings_menu(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()
        text = admin_update.callback_query.edit_message_text.call_args[0][0]
        assert "Настройки" in text


# ---------------------------------------------------------------------------
# Toggle_auto_approve
# ---------------------------------------------------------------------------

class TestToggleAutoApprove:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await toggle_auto_approve(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_toggles_auto_approve_on(self, admin_update, admin_context):
        settings = admin_context.bot_data["settings_service"]
        settings.get_setting = AsyncMock(return_value="false")

        await toggle_auto_approve(admin_update, admin_context)

        settings.set_setting.assert_awaited_once_with("auto_approve_new_users", "true")
        admin_update.callback_query.edit_message_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_toggles_auto_approve_off(self, admin_update, admin_context):
        settings = admin_context.bot_data["settings_service"]
        settings.get_setting = AsyncMock(return_value="true")

        await toggle_auto_approve(admin_update, admin_context)

        settings.set_setting.assert_awaited_once_with("auto_approve_new_users", "false")
        admin_update.callback_query.edit_message_text.assert_awaited()


# ---------------------------------------------------------------------------
# Show_orders_menu
# ---------------------------------------------------------------------------

class TestShowOrdersMenu:
    @pytest.mark.asyncio
    async def test_shows_orders_menu(self, admin_update, admin_context):
        await show_orders_menu(admin_update, admin_context)

        admin_update.callback_query.answer.assert_awaited_once()
        admin_update.callback_query.edit_message_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Show_order_list_by_status
# ---------------------------------------------------------------------------

class TestShowOrderListByStatus:
    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await show_order_list_by_status(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_list_shows_alert(self, admin_update, admin_context):
        admin_update.callback_query.data = "admin_orders_status_PAID"

        await show_order_list_by_status(admin_update, admin_context)

        admin_update.callback_query.answer.assert_called_with(
            'Заказов в статусе «Оплачен» нет.',
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_shows_order_list(self, admin_update, admin_context):
        mock_order = MagicMock()
        mock_order.id = 44
        mock_order.status = DomainOrderStatus.PAID
        admin_context.bot_data["order_service"].get_orders_by_statuses = AsyncMock(
            return_value=[mock_order]
        )
        admin_update.callback_query.data = "admin_orders_status_PAID"

        await show_order_list_by_status(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()
        assert "Оплачен" in admin_update.callback_query.edit_message_text.call_args[0][0]


# ---------------------------------------------------------------------------
# Show_order_details
# ---------------------------------------------------------------------------

class TestShowOrderDetails:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, admin_update, admin_context):
        admin_update.effective_user = None
        result = await show_order_details(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await show_order_details(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_order_details_with_override(self, admin_update, admin_context):
        mock_details = MagicMock(), [MagicMock(product_id=1, quantity=2, price=500)]
        admin_context.bot_data["order_service"].get_full_order_details = AsyncMock(
            return_value=mock_details
        )
        await show_order_details(admin_update, admin_context, order_id_override=44)

        admin_update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_order_not_found(self, admin_update, admin_context):
        admin_context.bot_data["order_service"].get_full_order_details = AsyncMock(return_value=None)

        await show_order_details(admin_update, admin_context, order_id_override=999)

        admin_update.callback_query.edit_message_text.assert_awaited_once_with(
            "Ошибка: Заказ не найден."
        )


# ---------------------------------------------------------------------------
# Show_communication_center
# ---------------------------------------------------------------------------

class TestShowCommunicationCenter:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, admin_update, admin_context):
        admin_update.callback_query = None
        result = await show_communication_center(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_communication_center(self, admin_update, admin_context):
        await show_communication_center(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_threads(self, admin_update, admin_context):
        await show_communication_center(admin_update, admin_context)

        text = admin_update.callback_query.edit_message_text.call_args[0][0]
        assert "пока нет" in text


# ---------------------------------------------------------------------------
# Show_courier_mgmt
# ---------------------------------------------------------------------------

class TestShowCourierMgmt:
    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await show_courier_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_courier_mgmt(self, admin_update, admin_context):
        await show_courier_mgmt(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()
        text = admin_update.callback_query.edit_message_text.call_args[0][0]
        assert "курьер" in text.lower()


# ---------------------------------------------------------------------------
# Show_pickup_mgmt
# ---------------------------------------------------------------------------

class TestShowPickupMgmt:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, admin_update, admin_context):
        admin_update.effective_user = None
        result = await show_pickup_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await show_pickup_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_pickup_mgmt(self, admin_update, admin_context):
        await show_pickup_mgmt(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()
        text = admin_update.callback_query.edit_message_text.call_args[0][0]
        assert "самовывоз" in text.lower()


# ---------------------------------------------------------------------------
# Sync_products_button_action
# ---------------------------------------------------------------------------

class TestSyncProductsButtonAction:
    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await sync_products_button_action(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_sync_success(self, admin_update, admin_context):
        admin_context.bot_data["db_pool"] = MagicMock()

        with patch(
            "tg_bot.handlers.admin_panel.sync_service.sync_products",
            new_callable=AsyncMock,
        ) as mock_sync:
            await sync_products_button_action(admin_update, admin_context)

            mock_sync.assert_awaited_once()
            admin_update.callback_query.edit_message_text.assert_awaited()
            text = admin_update.callback_query.edit_message_text.call_args[0][0]
            assert "успешно" in text.lower()


# ---------------------------------------------------------------------------
# Admin_exit_to_main_menu
# ---------------------------------------------------------------------------

class TestAdminExitToMainMenu:
    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await admin_exit_to_main_menu(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_exits_to_main_menu(self, admin_update, admin_context):
        with patch(
            "tg_bot.handlers.registration.show_main_menu_from_welcome",
            new_callable=AsyncMock,
        ) as mock_menu:
            result = await admin_exit_to_main_menu(admin_update, admin_context)

            mock_menu.assert_awaited_once()
            assert result == -1  # ConversationHandler.END


# ---------------------------------------------------------------------------
# Show_logo_mgmt
# ---------------------------------------------------------------------------

class TestShowLogoMgmt:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, admin_update, admin_context):
        admin_update.effective_user = None
        result = await show_logo_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await show_logo_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_logo_mgmt_no_logo(self, admin_update, admin_context):
        await show_logo_mgmt(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shows_logo_mgmt_with_logo(self, admin_update, admin_context):
        admin_context.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=1))
        admin_context.bot_data["settings_service"].get_setting = AsyncMock(
            side_effect=lambda key, default="false": {
                "registration_logo": "AgADBAADFak0G8mzSUg",
                "registration_logo_type": "photo",
            }.get(key, default)
        )

        await show_logo_mgmt(admin_update, admin_context)

        admin_context.bot.send_photo.assert_awaited_once()


# ---------------------------------------------------------------------------
# Show_proxy_mgmt
# ---------------------------------------------------------------------------

class TestShowProxyMgmt:
    @pytest.mark.asyncio
    async def test_guard_effective_chat_none(self, admin_update, admin_context):
        admin_update.effective_chat = None
        result = await show_proxy_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, admin_update, admin_context):
        admin_update.callback_query.data = None
        result = await show_proxy_mgmt(admin_update, admin_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_shows_proxy_mgmt(self, admin_update, admin_context):
        admin_update.effective_chat = MagicMock()
        admin_update.effective_chat.id = 123456

        with (
            patch("tg_bot.infrastructure.secrets_loader.SecretsLoader.get", return_value="http://proxy:8080"),
            patch("tg_bot.handlers.admin_panel._read_config_proxy_flag", return_value=True),
        ):
            await show_proxy_mgmt(admin_update, admin_context)

        admin_update.callback_query.edit_message_text.assert_awaited_once()
        text = admin_update.callback_query.edit_message_text.call_args[0][0]
        assert "proxy" in text.lower()
