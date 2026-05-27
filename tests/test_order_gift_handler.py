"""Unit tests for tg_bot/handlers/order_gift.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Message, Update
from telegram.ext import ConversationHandler

from tg_bot.handlers.order_gift import (
    handle_ai_gift_retry,
    handle_gift_choice,
    handle_gift_comment,
    handle_gift_skip,
    process_ai_gift_request,
    prompt_gift_choice,
    select_ai_gift_option,
    start_ai_gift_help,
)
from tg_bot.keyboards import CB_GIFT_AS_PRESENT, CB_GIFT_FOR_ME


def _make_cq(data: str) -> MagicMock:
    cq = MagicMock(spec=CallbackQuery)
    cq.data = data
    cq.answer = AsyncMock()
    cq.edit_message_text = AsyncMock(return_value=MagicMock(spec=Message, message_id=200))
    cq.message = MagicMock()
    cq.message.message_id = 100
    cq.message.delete = AsyncMock()
    return cq


async def _finalize_fn(update, context, **kwargs) -> int:
    return 77


async def _show_cart_fn(update, context) -> int:
    return 99


CB_GIFT_BACK = "gift_back"
CB_PREFIX_AI_GIFT_SELECT = "ai_gift_sel_"
AWAITING_GIFT_COMMENT = 7
AWAITING_GIFT_AI_DATA = 10
ASKING_GIFT = 6


class TestPromptGiftChoice:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await prompt_gift_choice(update, mock_context, _show_cart_fn, ASKING_GIFT)
        assert result == ASKING_GIFT

    @pytest.mark.asyncio
    async def test_guard_effective_chat_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        update.effective_chat = None
        result = await prompt_gift_choice(update, mock_context, _show_cart_fn, ASKING_GIFT)
        assert result == ASKING_GIFT

    @pytest.mark.asyncio
    async def test_missing_delivery_data_shows_cart(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("test")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data = {"user_service": MagicMock()}
        mock_context.user_data = {}

        result = await prompt_gift_choice(update, mock_context, _show_cart_fn, ASKING_GIFT)
        assert result == 99

    @pytest.mark.asyncio
    async def test_with_delivery_data_edits_message(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("test")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        update.effective_chat = MagicMock(id=123)
        mock_context.bot_data = {"user_service": MagicMock()}
        mock_context.user_data = {}
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        mock_context.bot_data["user_service"] = user_svc

        result = await prompt_gift_choice(
            update, mock_context, _show_cart_fn, ASKING_GIFT, delivery_data={"delivery_type": "courier"}
        )
        assert result == ASKING_GIFT
        cq.edit_message_text.assert_awaited_once()
        assert "Почти готово" in cq.edit_message_text.call_args[0][0]


class TestHandleGiftChoice:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await handle_gift_choice(
            update, mock_context, _finalize_fn, CB_GIFT_FOR_ME, CB_GIFT_AS_PRESENT, AWAITING_GIFT_COMMENT
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        update.callback_query = None
        result = await handle_gift_choice(
            update, mock_context, _finalize_fn, CB_GIFT_FOR_ME, CB_GIFT_AS_PRESENT, AWAITING_GIFT_COMMENT
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_missing_delivery_data_ends(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_GIFT_FOR_ME}:extra")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.user_data = {}

        result = await handle_gift_choice(
            update, mock_context, _finalize_fn, CB_GIFT_FOR_ME, CB_GIFT_AS_PRESENT, AWAITING_GIFT_COMMENT
        )
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_for_me_finalizes_order(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_GIFT_FOR_ME}:extra")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.user_data = {"temp_delivery_data": {"delivery_type": "courier"}}

        result = await handle_gift_choice(
            update, mock_context, _finalize_fn, CB_GIFT_FOR_ME, CB_GIFT_AS_PRESENT, AWAITING_GIFT_COMMENT
        )
        assert result == 77

    @pytest.mark.asyncio
    async def test_as_gift_prompts_for_comment(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_GIFT_AS_PRESENT}:extra")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.user_data = {"temp_delivery_data": {"delivery_type": "courier"}}

        result = await handle_gift_choice(
            update, mock_context, _finalize_fn, CB_GIFT_FOR_ME, CB_GIFT_AS_PRESENT, AWAITING_GIFT_COMMENT
        )
        assert result == AWAITING_GIFT_COMMENT
        cq.edit_message_text.assert_awaited_once()
        assert "подарок" in cq.edit_message_text.call_args[0][0]


class TestHandleGiftComment:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await handle_gift_comment(update, mock_context, _finalize_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_guard_message_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        update.message = None
        result = await handle_gift_comment(update, mock_context, _finalize_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_guard_message_text_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        msg = MagicMock(spec=Message)
        msg.text = None
        update.message = msg
        result = await handle_gift_comment(update, mock_context, _finalize_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_saves_comment_and_finalizes(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        msg = MagicMock(spec=Message)
        msg.text = "С днём рождения!"
        msg.message_id = 999
        msg.delete = AsyncMock()
        update.message = msg
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        user_svc.get_user = AsyncMock(return_value=None)
        mock_context.bot_data = {"user_service": user_svc}
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=500))
        mock_context.user_data = {"temp_delivery_data": {"delivery_type": "courier"}}

        result = await handle_gift_comment(update, mock_context, _finalize_fn)
        assert result == 77

    @pytest.mark.asyncio
    async def test_skip_sets_comment_to_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        msg = MagicMock(spec=Message)
        msg.text = "/skip"
        msg.message_id = 999
        msg.delete = AsyncMock()
        update.message = msg
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        user_svc.get_user = AsyncMock(return_value=None)
        mock_context.bot_data = {"user_service": user_svc}
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=500))
        mock_context.user_data = {"temp_delivery_data": {"delivery_type": "courier"}}

        result = await handle_gift_comment(update, mock_context, _finalize_fn)
        assert result == 77


class TestHandleGiftSkip:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await handle_gift_skip(update, mock_context, _finalize_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        update.callback_query = None
        result = await handle_gift_skip(update, mock_context, _finalize_fn)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_skip_with_delivery_data_finalizes(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("gift_skip")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.user_data = {"temp_delivery_data": {"delivery_type": "courier"}}

        result = await handle_gift_skip(update, mock_context, _finalize_fn)
        assert result == 77

    @pytest.mark.asyncio
    async def test_skip_without_delivery_data_shows_error(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("gift_skip")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.user_data = {}

        result = await handle_gift_skip(update, mock_context, _finalize_fn)
        assert result == ConversationHandler.END
        cq.edit_message_text.assert_awaited_once_with("Ошибка сессии.")


class TestStartAiGiftHelp:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await start_ai_gift_help(update, mock_context, CB_GIFT_BACK, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_guard_message_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = MagicMock(spec=CallbackQuery)
        cq.answer = AsyncMock()
        cq.data = "test"
        cq.message = None
        update.callback_query = cq
        result = await start_ai_gift_help(update, mock_context, CB_GIFT_BACK, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_shows_ai_help_message(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("test")
        update.callback_query = cq
        mock_context.user_data = {}
        result = await start_ai_gift_help(update, mock_context, CB_GIFT_BACK, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA
        cq.edit_message_text.assert_awaited_once()
        assert "Мастерская" in cq.edit_message_text.call_args[0][0]


class TestProcessAiGiftRequest:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await process_ai_gift_request(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_guard_message_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        update.message = None
        result = await process_ai_gift_request(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_guard_message_text_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        msg = MagicMock(spec=Message)
        msg.text = None
        update.message = msg
        result = await process_ai_gift_request(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_ai_service_returns_options(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        msg = MagicMock(spec=Message)
        msg.text = "Для подруги"
        msg.message_id = 999
        msg.delete = AsyncMock()
        update.message = msg
        ai_service = MagicMock()
        ai_service.get_ai_gift_greetings = AsyncMock(return_value=["Вариант 1", "Вариант 2"])
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        user_svc.get_user = AsyncMock(return_value=None)
        mock_context.bot_data = {
            "ai_comm_service": ai_service,
            "user_service": user_svc,
        }
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=status_msg)
        mock_context.user_data = {}

        result = await process_ai_gift_request(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA
        status_msg.edit_text.assert_awaited_once()
        assert "Вариант" in status_msg.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_ai_service_returns_empty_shows_fallback(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        msg = MagicMock(spec=Message)
        msg.text = "Для подруги"
        msg.message_id = 999
        msg.delete = AsyncMock()
        update.message = msg
        ai_service = MagicMock()
        ai_service.get_ai_gift_greetings = AsyncMock(return_value=[])
        user_svc = MagicMock()
        user_svc.save_registration_message_id = AsyncMock()
        user_svc.get_user = AsyncMock(return_value=None)
        mock_context.bot_data = {
            "ai_comm_service": ai_service,
            "user_service": user_svc,
        }
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        mock_context.bot.send_message = AsyncMock(return_value=status_msg)
        mock_context.user_data = {}

        result = await process_ai_gift_request(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA
        status_msg.edit_text.assert_awaited_once()
        assert "не может помочь" in status_msg.edit_text.call_args[0][0]


class TestSelectAiGiftOption:
    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.callback_query = None
        result = await select_ai_gift_option(
            update, mock_context, _finalize_fn, CB_PREFIX_AI_GIFT_SELECT, AWAITING_GIFT_COMMENT
        )
        assert result == AWAITING_GIFT_COMMENT

    @pytest.mark.asyncio
    async def test_guard_query_data_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = MagicMock(spec=CallbackQuery)
        cq.data = None
        update.callback_query = cq
        result = await select_ai_gift_option(
            update, mock_context, _finalize_fn, CB_PREFIX_AI_GIFT_SELECT, AWAITING_GIFT_COMMENT
        )
        assert result == AWAITING_GIFT_COMMENT

    @pytest.mark.asyncio
    async def test_selects_option_and_finalizes(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_AI_GIFT_SELECT}0")
        update.callback_query = cq
        mock_context.user_data = {
            "ai_gift_options": ["Поздравляю!", "Счастья!"],
            "temp_delivery_data": {"delivery_type": "courier"},
        }

        result = await select_ai_gift_option(
            update, mock_context, _finalize_fn, CB_PREFIX_AI_GIFT_SELECT, AWAITING_GIFT_COMMENT
        )
        assert result == 77

    @pytest.mark.asyncio
    async def test_index_out_of_range_shows_error(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_AI_GIFT_SELECT}5")
        update.callback_query = cq
        mock_context.user_data = {
            "ai_gift_options": ["Поздравляю!"],
            "temp_delivery_data": {"delivery_type": "courier"},
        }

        result = await select_ai_gift_option(
            update, mock_context, _finalize_fn, CB_PREFIX_AI_GIFT_SELECT, AWAITING_GIFT_COMMENT
        )
        assert result == AWAITING_GIFT_COMMENT
        cq.answer.assert_called_once_with("Ошибка выбора варианта.", show_alert=True)

    @pytest.mark.asyncio
    async def test_missing_delivery_data_shows_error(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq(f"{CB_PREFIX_AI_GIFT_SELECT}0")
        update.callback_query = cq
        mock_context.user_data = {
            "ai_gift_options": ["Поздравляю!"],
        }

        result = await select_ai_gift_option(
            update, mock_context, _finalize_fn, CB_PREFIX_AI_GIFT_SELECT, AWAITING_GIFT_COMMENT
        )
        assert result == AWAITING_GIFT_COMMENT
        cq.answer.assert_called_once_with("Ошибка сессии.", show_alert=True)


class TestHandleAiGiftRetry:
    @pytest.mark.asyncio
    async def test_guard_effective_user_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = None
        result = await handle_ai_gift_retry(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_guard_query_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        update.callback_query = None
        result = await handle_ai_gift_retry(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_guard_message_none(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(id=123)
        cq = MagicMock(spec=CallbackQuery)
        cq.answer = AsyncMock()
        cq.data = "test"
        cq.message = None
        update.callback_query = cq
        result = await handle_ai_gift_retry(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA

    @pytest.mark.asyncio
    async def test_shows_retry_message(self, mock_context: MagicMock) -> None:
        update = MagicMock(spec=Update)
        cq = _make_cq("test")
        update.callback_query = cq
        update.effective_user = MagicMock(id=123)
        mock_context.user_data = {}

        result = await handle_ai_gift_retry(update, mock_context, CB_GIFT_AS_PRESENT, AWAITING_GIFT_AI_DATA)
        assert result == AWAITING_GIFT_AI_DATA
        cq.edit_message_text.assert_awaited_once()
        assert "попробуем" in cq.edit_message_text.call_args[0][0]
