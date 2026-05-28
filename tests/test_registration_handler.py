"""Unit tests for tg_bot/handlers/registration.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from tg_bot.handlers.registration import (
    AWAITING_EMAIL,
    AWAITING_FIO,
    AWAITING_PHONE,
    cancel_registration,
    handle_approval_callback,
    invalid_phone_input,
    received_email,
    received_fio,
    received_phone,
    registration_handler,
    start,
)
from tg_bot.models import UserStatus


class TestStart:
    @pytest.mark.asyncio
    async def test_guard_when_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await start(mock_update, mock_context)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_deep_link_redirects(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["settings_service"] = AsyncMock()
        mock_context.args = ["p42"]
        mock_context.bot_data["user_service"].get_user = AsyncMock(
            return_value=MagicMock(status=UserStatus.APPROVED)
        )
        with patch(
            "tg_bot.handlers.registration._check_start_redirections",
            new_callable=AsyncMock,
        ) as mock_redirect:
            mock_redirect.return_value = 999
            result = await start(mock_update, mock_context)
            assert result == 999

    @pytest.mark.asyncio
    async def test_new_user_gets_welcome(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["settings_service"] = AsyncMock()
        mock_context.bot_data["user_service"].get_user = AsyncMock(return_value=None)
        mock_context.bot_data["settings_service"].get_setting = AsyncMock(
            side_effect=lambda key, default=None: {
                "registration_logo": None,
                "registration_logo_type": "photo",
                "registration_welcome_text": "Welcome!",
            }.get(key, default)
        )
        mock_context.bot.send_message = AsyncMock(
            side_effect=[
                MagicMock(message_id=1),
                MagicMock(message_id=2),
            ]
        )
        result = await start(mock_update, mock_context)
        assert result == ConversationHandler.END


class TestReceivedFio:
    @pytest.mark.asyncio
    async def test_guard_when_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await received_fio(mock_update, mock_context)
        assert result == AWAITING_FIO

    @pytest.mark.asyncio
    async def test_guard_when_message_is_none(self, mock_update, mock_context):
        mock_update.message = None
        result = await received_fio(mock_update, mock_context)
        assert result == AWAITING_FIO

    @pytest.mark.asyncio
    async def test_invalid_fio_shows_error(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["user_service"].save_registration_message_id = AsyncMock()
        mock_context.user_data = {}
        mock_update.message = MagicMock()
        mock_update.message.text = "Ivan123"
        mock_update.message.message_id = 10
        mock_update.message.delete = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=5))
        result = await received_fio(mock_update, mock_context)
        assert result == AWAITING_FIO
        mock_context.bot.send_message.assert_awaited_once()
        text = mock_context.bot.send_message.call_args[0][1]
        assert "ФИО" in text

    @pytest.mark.asyncio
    async def test_valid_fio_saves_and_proceeds(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["user_service"].save_registration_message_id = AsyncMock()
        mock_context.user_data = {"placeholder": True}
        mock_context.user_data["fio"] = None
        mock_update.message = MagicMock()
        mock_update.message.text = "иванов иван иванович"
        mock_update.message.message_id = 10
        mock_update.message.delete = AsyncMock()
        mock_context.bot.send_message = AsyncMock(
            return_value=MagicMock(message_id=20)
        )
        result = await received_fio(mock_update, mock_context)
        assert result == AWAITING_EMAIL
        assert mock_context.user_data["fio"] == "Иванов Иван Иванович"
        assert mock_context.user_data.get("prompt_msg_id") == 20
        mock_context.bot.send_message.assert_awaited_once()


class TestReceivedEmail:
    @pytest.mark.asyncio
    async def test_guard_when_effective_user_none(self, mock_update, mock_context):
        mock_update.effective_user = None
        result = await received_email(mock_update, mock_context)
        assert result == AWAITING_EMAIL

    @pytest.mark.asyncio
    async def test_invalid_email_shows_error(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["user_service"].save_registration_message_id = AsyncMock()
        mock_context.user_data = {}
        mock_update.message = MagicMock()
        mock_update.message.text = "not-an-email"
        mock_update.message.delete = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=5))
        result = await received_email(mock_update, mock_context)
        assert result == AWAITING_EMAIL
        mock_context.bot.send_message.assert_awaited_once()
        text = mock_context.bot.send_message.call_args[0][1]
        assert "Email" in text

    @pytest.mark.asyncio
    async def test_valid_email_saves_and_proceeds(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["user_service"].save_registration_message_id = AsyncMock()
        mock_context.user_data = {"placeholder": True}
        mock_update.message = MagicMock()
        mock_update.message.text = "test@example.com"
        mock_update.message.delete = AsyncMock()
        mock_context.bot.send_message = AsyncMock(
            return_value=MagicMock(message_id=30)
        )
        with patch(
            "tg_bot.handlers.registration.get_contact_keyboard"
        ) as mock_kb:
            mock_kb.return_value = MagicMock()
            result = await received_email(mock_update, mock_context)
            assert result == AWAITING_PHONE
            assert mock_context.user_data.get("email") == "test@example.com"


class TestReceivedPhone:
    @pytest.mark.asyncio
    async def test_valid_contact_approved(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["settings_service"] = AsyncMock()
        mock_context.bot_data["settings_service"].get_setting = AsyncMock(
            return_value="true"
        )
        new_user = MagicMock(status=UserStatus.APPROVED)
        mock_context.bot_data["user_service"].register_new_user = AsyncMock(
            return_value=new_user
        )
        mock_context.user_data = {
            "fio": "Test User",
            "email": "test@test.com",
            "prompt_msg_id": 1,
        }
        contact = MagicMock()
        contact.phone_number = "+79991112233"
        mock_update.message = MagicMock()
        mock_update.message.contact = contact
        mock_update.message.message_id = 50
        mock_update.message.delete = AsyncMock()
        with patch(
            "tg_bot.handlers.registration.show_main_menu_from_welcome",
            new_callable=AsyncMock,
        ) as mock_mm:
            mock_mm.return_value = ConversationHandler.END
            result = await received_phone(mock_update, mock_context)
            assert result == ConversationHandler.END
            mock_context.bot_data["user_service"].register_new_user.assert_awaited_once_with(
                123456, "Test User", "+79991112233", "test@test.com", True
            )

    @pytest.mark.asyncio
    async def test_invalid_contact_calls_invalid_phone(self, mock_update, mock_context):
        mock_context.bot_data = {
            "user_service": AsyncMock(),
            "settings_service": AsyncMock(),
        }
        mock_update.message = MagicMock()
        mock_update.message.contact = None
        with patch(
            "tg_bot.handlers.registration.invalid_phone_input",
            new_callable=AsyncMock,
        ) as mock_invalid:
            mock_invalid.return_value = AWAITING_PHONE
            result = await received_phone(mock_update, mock_context)
            assert result == AWAITING_PHONE


class TestCancelRegistration:
    @pytest.mark.asyncio
    async def test_clears_user_data_returns_end(self, mock_update, mock_context):
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 123456
        mock_context.user_data = {"fio": "some", "email": "test@test.com"}
        mock_context.bot_data["cart_service"] = AsyncMock()
        mock_context.bot_data["cart_service"].clear_cart = AsyncMock()
        result = await cancel_registration(mock_update, mock_context)
        assert result == ConversationHandler.END
        assert mock_context.user_data == {}
        mock_context.bot_data["cart_service"].clear_cart.assert_awaited_once_with(
            123456
        )
        mock_context.bot.send_message.assert_awaited_once()


class TestHandleApprovalCallback:
    @pytest.mark.asyncio
    async def test_guard_when_query_is_none(self, mock_update, mock_context):
        mock_update.callback_query = None
        result = await handle_approval_callback(mock_update, mock_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_approves_user(self, mock_update, mock_context):
        mock_update.effective_user.full_name = "Moderator"
        cq = MagicMock()
        cq.data = "approve_789"
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        mock_update.callback_query = cq
        mock_user_svc = MagicMock()
        mock_user_svc.get_user = AsyncMock(
            return_value=MagicMock(
                telegram_id=789,
                registration_message_id=100,
            )
        )
        approved_user = MagicMock()
        approved_user.fio = "Test User"
        mock_user_svc.approve_user = AsyncMock(return_value=approved_user)
        mock_context.bot_data["user_service"] = mock_user_svc
        mock_context.bot.edit_message_text = AsyncMock()
        await handle_approval_callback(mock_update, mock_context)
        cq.answer.assert_awaited_once()
        cq.edit_message_text.assert_awaited_once()
        text = cq.edit_message_text.call_args.kwargs["text"]
        assert "одобрен" in text or "одобрен" in text

    @pytest.mark.asyncio
    async def test_declines_user(self, mock_update, mock_context):
        mock_update.effective_user.full_name = "Moderator"
        cq = MagicMock()
        cq.data = "decline_789"
        cq.answer = AsyncMock()
        cq.edit_message_text = AsyncMock()
        mock_update.callback_query = cq
        mock_user_svc = MagicMock()
        mock_user_svc.get_user = AsyncMock(return_value=None)
        declined_user = MagicMock()
        declined_user.fio = "Test User"
        mock_user_svc.decline_user = AsyncMock(return_value=declined_user)
        mock_context.bot_data["user_service"] = mock_user_svc
        await handle_approval_callback(mock_update, mock_context)
        cq.answer.assert_awaited_once()
        cq.edit_message_text.assert_awaited_once()
        text = cq.edit_message_text.call_args.kwargs["text"]
        assert "отклонен" in text or "отклонена" in text


class TestInvalidPhoneInput:
    @pytest.mark.asyncio
    async def test_sends_error_returns_awaiting_phone(self, mock_update, mock_context):
        mock_context.bot_data["user_service"] = AsyncMock()
        mock_context.bot_data["user_service"].save_registration_message_id = AsyncMock()
        mock_context.user_data = {}
        mock_update.message = MagicMock()
        mock_update.message.delete = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=7))
        with patch(
            "tg_bot.handlers.registration.get_contact_keyboard"
        ) as mock_kb:
            mock_kb.return_value = MagicMock()
            result = await invalid_phone_input(mock_update, mock_context)
            assert result == AWAITING_PHONE
            mock_context.bot.send_message.assert_awaited_once()
            text = mock_context.bot.send_message.call_args.kwargs["text"]
            assert "контакт" in text.lower() or "контактом" in text


class TestRegistrationHandlerInstance:
    def test_is_conversation_handler(self):
        assert isinstance(registration_handler, ConversationHandler)

    def test_has_entry_points(self):
        assert len(registration_handler.entry_points) > 0

    def test_has_states(self):
        assert AWAITING_FIO in registration_handler.states
        assert AWAITING_EMAIL in registration_handler.states

    def test_has_fallbacks(self):
        assert len(registration_handler.fallbacks) > 0
