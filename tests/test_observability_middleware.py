"""Integration tests for ObservabilityMiddleware."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update

from tg_bot.infrastructure.observability_middleware import ObservabilityMiddleware


class TestObservabilityMiddleware:
    @pytest.fixture
    def mw(self) -> ObservabilityMiddleware:
        return ObservabilityMiddleware()

    @pytest.fixture
    def mock_update(self) -> Any:
        u = MagicMock(spec=Update)
        u.effective_user = MagicMock()
        u.effective_user.id = 123
        u.effective_chat = MagicMock()
        u.effective_chat.id = 456
        u.message = None
        u.callback_query = MagicMock()
        u.callback_query.data = "menu_main"
        u.inline_query = None
        u.chosen_inline_result = None
        return u

    @pytest.mark.asyncio
    async def test_calls_next_handler(self, mw, mock_update) -> Any:
        next_handler = AsyncMock(return_value="result")
        context = MagicMock()
        context.bot_data = {}

        with patch("tg_bot.infrastructure.observability_middleware.record_request"):
            with patch("tg_bot.infrastructure.observability_middleware.record_request_duration"):
                result = await mw(mock_update, context, next_handler)

        assert result == "result"
        next_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_records_success(self, mw, mock_update) -> Any:
        next_handler = AsyncMock(return_value="ok")
        context = MagicMock()
        context.bot_data = {}

        with patch("tg_bot.infrastructure.observability_middleware.record_request") as mock_record:
            with patch("tg_bot.infrastructure.observability_middleware.record_request_duration"):
                await mw(mock_update, context, next_handler)

        mock_record.assert_called_once()
        call_args = mock_record.call_args
        assert call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_records_error(self, mw, mock_update) -> Any:
        next_handler = AsyncMock(side_effect=RuntimeError("boom"))
        context = MagicMock()
        context.bot_data = {}

        with patch("tg_bot.infrastructure.observability_middleware.record_request") as mock_record:
            with patch("tg_bot.infrastructure.observability_middleware.record_request_duration"):
                with pytest.raises(RuntimeError):
                    await mw(mock_update, context, next_handler)

        mock_record.assert_called_once()
        call_args = mock_record.call_args
        assert call_args[0][1] == "error"

    def test_get_handler_name_command(self, mw) -> Any:
        u = MagicMock()
        u.message = MagicMock()
        u.message.text = "/start"
        u.callback_query = None
        assert mw._get_handler_name(u, MagicMock()) == "command_start"

    def test_get_handler_name_callback(self, mw, mock_update) -> Any:
        assert mw._get_handler_name(mock_update, MagicMock()) == "callback"

    def test_get_handler_name_message(self, mw) -> Any:
        u = MagicMock()
        u.message = MagicMock()
        u.message.text = "hello"
        u.callback_query = None
        assert mw._get_handler_name(u, MagicMock()) == "message"
