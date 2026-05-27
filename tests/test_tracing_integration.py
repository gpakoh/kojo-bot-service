"""Integration tests for correlation ID propagation."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.infrastructure.correlation import clear_correlation_id, get_correlation_id, set_correlation_id
from tg_bot.infrastructure.observability_middleware import ObservabilityMiddleware


class TestTracingPropagation:
    @pytest.fixture
    def mw(self) -> ObservabilityMiddleware:
        return ObservabilityMiddleware()

    @pytest.mark.asyncio
    async def test_middleware_sets_correlation_id(self, mw: ObservabilityMiddleware) -> Any:
        clear_correlation_id()
        assert get_correlation_id() == "unknown"

        mock_update = MagicMock()
        mock_update.effective_user = MagicMock()
        mock_update.effective_user.id = 123
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 456
        mock_update.callback_query = None
        mock_update.message = MagicMock()
        mock_update.message.text = "hello"

        context = MagicMock()
        context.user_data = {}

        next_handler = AsyncMock(return_value="ok")

        with patch("tg_bot.infrastructure.observability_middleware.logger"):
            await mw(mock_update, context, next_handler)

        assert get_correlation_id() != "unknown"
        assert get_correlation_id().startswith("req-")
        assert context.user_data["_correlation_id"] == get_correlation_id()

    @pytest.mark.asyncio
    async def test_middleware_preserves_existing_correlation_id(self, mw: ObservabilityMiddleware) -> Any:
        set_correlation_id("existing-123")

        mock_update = MagicMock()
        mock_update.effective_user = MagicMock()
        mock_update.effective_user.id = 123
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 456
        mock_update.callback_query = None
        mock_update.message = MagicMock()
        mock_update.message.text = "hello"

        context = MagicMock()
        context.user_data = {}

        next_handler = AsyncMock(return_value="ok")

        with patch("tg_bot.infrastructure.observability_middleware.logger"):
            await mw(mock_update, context, next_handler)

        assert get_correlation_id() == "existing-123"
        assert context.user_data["_correlation_id"] == "existing-123"

    @pytest.mark.asyncio
    async def test_middleware_stores_correlation_id_in_user_data(self, mw: ObservabilityMiddleware) -> Any:
        clear_correlation_id()

        mock_update = MagicMock()
        mock_update.effective_user = MagicMock()
        mock_update.effective_user.id = 789
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = 101
        mock_update.callback_query = None
        mock_update.message = MagicMock()
        mock_update.message.text = "/start"

        context = MagicMock()
        context.user_data = {}

        next_handler = AsyncMock(return_value="ok")

        with patch("tg_bot.infrastructure.observability_middleware.logger"):
            await mw(mock_update, context, next_handler)

        assert "_correlation_id" in context.user_data
        assert len(context.user_data["_correlation_id"]) > 0
