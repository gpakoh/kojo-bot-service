from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.callback_validator import validate_callback, validate_callback_data


class TestCallbackValidator:
    def test_valid_simple(self) -> Any:
        assert validate_callback_data("menu:main") == "menu:main"

    def test_valid_complex(self) -> Any:
        assert validate_callback_data("order_123=confirm,page=2") == "order_123=confirm,page=2"

    def test_empty_returns_empty(self) -> Any:
        assert validate_callback_data("") == ""

    def test_none_returns_empty(self) -> Any:
        assert validate_callback_data(None) == ""

    def test_too_long_raises(self) -> Any:
        long_str = "a" * 65
        with pytest.raises(ValueError, match="exceeds"):
            validate_callback_data(long_str)

    def test_script_tag_raises(self) -> Any:
        with pytest.raises(ValueError, match="invalid characters"):
            validate_callback_data("menu<script>")

    def test_javascript_raises(self) -> Any:
        with pytest.raises(ValueError, match="invalid characters"):
            validate_callback_data("url=javascript:alert(1)")

    def test_invalid_chars_raises(self) -> Any:
        with pytest.raises(ValueError, match="invalid characters"):
            validate_callback_data("menu+main")

    def test_unicode_bytes_counted(self) -> Any:
        # 30 Cyrillic Chars = 60 Bytes, 31 = 62 Bytes, 32 = 64 Bytes, 33 = 66 Bytes > 64
        with pytest.raises(ValueError, match="exceeds"):
            validate_callback_data("а" * 33)

    def test_decorator_blocks_invalid(self) -> Any:
        @validate_callback
        async def handler(update: Any, context: Any) -> str:
            return "handled"

        mock_update = MagicMock()
        mock_update.callback_query = MagicMock()
        mock_update.callback_query.data = "<script>alert(1)</script>"
        mock_update.callback_query.answer = AsyncMock()

        import asyncio
        result = asyncio.run(handler(mock_update, MagicMock()))
        assert result is None  # Blocked
        mock_update.callback_query.answer.assert_awaited_once()

    def test_decorator_passes_valid(self) -> Any:
        @validate_callback
        async def handler(update: Any, context: Any) -> str:
            return "handled"

        mock_update = MagicMock()
        mock_update.callback_query = MagicMock()
        mock_update.callback_query.data = "menu:main"

        import asyncio
        result = asyncio.run(handler(mock_update, MagicMock()))
        assert result == "handled"
