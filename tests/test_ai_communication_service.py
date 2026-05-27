# Tests For Ai_communication_service.py
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.ai_communication_service import (
    AICommunicationService,
)
from tg_bot.bot_services.ai_communication_service import (
    sanitize_for_llm_prompt as _sanitize_user_input,
)
from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram

MAX_INPUT_LENGTH = 2000


class TestSanitizeInput:
    def test_blocks_script_start(self) -> Any:
        """Script tag start should be blocked."""
        result = _sanitize_user_input("<script>alert(1)</script>")
        assert "[BLOCKED]" in result
        assert "<script" not in result

    def test_blocks_onclick_start(self) -> Any:
        """Onclick start should be blocked."""
        result = _sanitize_user_input('onclick="evil()"')
        assert "[BLOCKED]" in result
        assert "onclick" not in result

    def test_preserves_brackets(self) -> Any:
        """Brackets should be preserved (not removed like before)."""
        result = _sanitize_user_input("Test [injection] attempt")
        assert '[' in result
        assert ']' in result

    def test_preserves_braces(self) -> Any:
        """Braces should be preserved."""
        result = _sanitize_user_input("{name} and {desc}")
        assert '{' in result
        assert '}' in result

    def test_preserves_pipe(self) -> Any:
        """Pipe should be preserved."""
        result = _sanitize_user_input("coffee | grep secret")
        assert '|' in result

    def test_preserves_backslash(self) -> Any:
        """Backslash should be preserved."""
        result = _sanitize_user_input("test\\nvalue")
        assert '\\' in result

    def test_truncates_long_input(self) -> Any:
        long_text = "a" * 500
        result = _sanitize_user_input(long_text)
        assert len(result) <= MAX_INPUT_LENGTH

    def test_preserves_valid_chars(self) -> Any:
        result = _sanitize_user_input("Кофе Эфиопия Иргачеффе - натуральный")
        assert "Кофе" in result
        assert "Эфиопия" in result

    def test_handles_empty_string(self) -> Any:
        result = _sanitize_user_input("")
        assert result == ""

    def test_handles_none(self) -> Any:
        result = _sanitize_user_input(None)
        assert result == ""

    def test_custom_max_length(self) -> Any:
        result = _sanitize_user_input("a" * 100, max_length=50)
        assert len(result) <= 50


class TestAICommunicationService:
    @pytest.fixture
    def service(self) -> "AICommunicationService":
        return AICommunicationService(
            quart_url="http://test.local",
            bot_id="test_bot",
        )

    def test_prepare_html_removes_script_tag(self, service) -> Any:
        result = prepare_html_for_telegram("<script>alert('xss')</script>Hello <b>World</b>")
        assert '<script>' not in result
        assert '<script' not in result
        assert '<b>World</b>' in result

    def test_prepare_html_removes_iframe(self, service) -> Any:
        result = prepare_html_for_telegram("<iframe src='https://evil.com'></iframe>Safe text")
        assert '<iframe' not in result
        assert 'Safe text' in result

    def test_prepare_html_removes_javascript_href(self, service) -> Any:
        result = prepare_html_for_telegram("<a href='javascript:alert(1)'>Click me</a>")
        assert 'javascript:' not in result

    def test_prepare_html_preserves_valid_href(self, service) -> Any:
        result = prepare_html_for_telegram("<a href='https://example.com'>Link</a>")
        assert 'href="https://example.com"' in result
        assert '<a' in result

    def test_prepare_html_removes_img_tag(self, service) -> Any:
        result = prepare_html_for_telegram("<img src='x' onerror='alert(1)'>Text")
        assert '<img' not in result
        assert 'onerror' not in result

    def test_prepare_html_preserves_bold(self, service) -> Any:
        result = prepare_html_for_telegram("Hello **World**!")
        assert '<b>World</b>' in result

    def test_prepare_html_converts_markdown_links(self, service) -> Any:
        result = prepare_html_for_telegram("[Click here](https://example.com)")
        assert '<a href="https://example.com">' in result
        assert 'Click here' in result

    def test_prepare_html_removes_style_tag(self, service) -> Any:
        result = prepare_html_for_telegram("<style>body{color:red}</style>Content")
        assert '<style' not in result
        assert '</style>' not in result

    def test_prepare_html_removes_onclick(self, service) -> Any:
        result = prepare_html_for_telegram("<div onclick='evil()'>Click</div>")
        assert 'onclick' not in result
        assert 'evil' not in result

    def test_prepare_html_empty_string(self, service) -> Any:
        result = prepare_html_for_telegram("")
        assert result == ""

    def test_prepare_html_none(self, service) -> Any:
        result = prepare_html_for_telegram(None)
        assert result == ""

    def test_prepare_html_removes_svg(self, service) -> Any:
        result = prepare_html_for_telegram("<svg onload='alert(1)'>Content</svg>")
        assert '<svg' not in result

    def test_prepare_html_preserves_code_tag(self, service) -> Any:
        result = prepare_html_for_telegram("<code>print('hello')</code>")
        assert '<code>' in result

    def test_prepare_html_removes_form_tag(self, service) -> Any:
        result = prepare_html_for_telegram("<form action='evil.com'><input name='x'></form>")
        assert '<form' not in result

    def test_prepare_html_multiple_attacks(self, service) -> Any:
        malicious = (
            "<script>alert(1)</script>"
            "<iframe src='evil.com'></iframe>"
            "<a href='javascript:alert(2)'>X</a>"
            "<img src=x onerror=alert(3)>"
            "Safe **bold** text"
        )
        result = prepare_html_for_telegram(malicious)
        assert '<script>' not in result
        assert '<iframe' not in result
        assert 'javascript:' not in result
        assert '<img' not in result
        assert '<b>bold</b>' in result

    def test_prepare_html_strips_markdown_code_blocks(self, service) -> Any:
        result = prepare_html_for_telegram("```html\n<strong>Test</strong>\n```")
        assert '```' not in result
        assert '<strong>Test</strong>' in result

    def test_prepare_html_removes_list_markers(self, service) -> Any:
        result = prepare_html_for_telegram("- Item 1\n- Item 2\n1. Item 3")
        assert '- Item' not in result
        assert '1. Item' not in result

    def test_prepare_html_removes_data_url(self, service) -> Any:
        result = prepare_html_for_telegram("<a href='data:text/html,<script>alert(1)</script>'>Click</a>")
        assert 'data:' not in result

    def test_prepare_html_removes_vbscript_url(self, service) -> Any:
        result = prepare_html_for_telegram("<a href='vbscript:msgbox(1)'>Click</a>")
        assert 'vbscript:' not in result

    def test_prepare_html_removes_onload_event(self, service) -> Any:
        result = prepare_html_for_telegram("<body onload='evil()'>Content</body>")
        assert 'onload' not in result
        assert 'evil' not in result

    def test_prepare_html_removes_onerror_event(self, service) -> Any:
        result = prepare_html_for_telegram("<img src='x' onerror='alert(1)'>Text")
        assert 'onerror' not in result

    def test_prepare_html_removes_onmouseover_event(self, service) -> Any:
        result = prepare_html_for_telegram("<span onmouseover='evil()'>Hover</span>")
        assert 'onmouseover' not in result

    def test_prepare_html_strips_invalid_href_values(self, service) -> Any:
        result = prepare_html_for_telegram("<a href='//evil.com'>Link</a><a href='/local'>Local</a>")
        assert 'href="//evil.com"' not in result
        assert 'href="/local"' in result

    def test_prepare_html_removes_meta_refresh(self, service) -> Any:
        result = prepare_html_for_telegram("<meta http-equiv='refresh' content='0;url=evil.com'>")
        assert 'refresh' not in result

    def test_prepare_html_removes_base_tag(self, service) -> Any:
        result = prepare_html_for_telegram("<base href='https://evil.com/'>")
        assert '<base' not in result

    @pytest.mark.parametrize("payload,forbidden", [
        ("<svg onload=alert(1)>", "onload"),
        ("<svg onload=alert(1)></svg>", "onload"),
        ("<svg/onload/onerror=alert(1)>", "onload"),
        ("<body onload=evil()>", "onload"),
        ("<img src=x onerror=alert(1)>", "onerror"),
        ("<img/onerror/alert(1)>", "onerror"),
        ("<input onfocus=alert(1) autofocus>", "onfocus"),
        ("<marquee onstart=alert(1)>", "onstart"),
        ("<textarea autofocus onfocus=alert(1)>", "onfocus"),
        ("<select onfocus=alert(1) autofocus>", "onfocus"),
        ("<keygen autofocus onfocus=alert(1)>", "onfocus"),
        ("<video><source onerror=alert(1)>", "onerror"),
        ("<audio src=x onerror=alert(1)>", "onerror"),
        ("<object data=x onerror=alert(1)>", "onerror"),
        ("<embed src=x onerror=alert(1)>", "onerror"),
        ("<a href='data:text/html,<script>alert(1)</script>'>X</a>", "data:"),
        ("<a href='data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=='>X</a>", "data:"),
        ("<a href='data:,alert(1)'>X</a>", "data:"),
        ("<form action='data:text/html,<script>alert(1)</script>'>", "data:"),
        ("<iframe src='data:text/html,<script>alert(1)</script>'>", "data:"),
        ("<link rel=stylesheet href='data:text/css,body{color:red}'>", "data:"),
    ])
    def test_prepare_html_xss_vectors(self, service, payload, forbidden) -> Any:
        result = prepare_html_for_telegram(payload)
        assert forbidden not in result.lower(), f"Failed to sanitize: {payload}"

    @pytest.mark.asyncio
    async def test_get_ai_answer_falls_back_to_quart_uses_middleware(self, service) -> Any:
        """When LLM client fails, service should use RequestMiddleware.post for fallback."""

        mock_middleware = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"answer": "Test response"})
        mock_middleware.post = AsyncMock(return_value=mock_response)

        service._http_middleware = mock_middleware

        mock_llm_client = MagicMock()
        mock_llm_client.chat_json = AsyncMock(return_value=None)
        service._llm_client = mock_llm_client

        result = await service.get_ai_answer(123, "test topic", "testuser")

        assert result == {"answer": "Test response"}
        mock_middleware.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_quart_calls_middleware(self, service) -> Any:
        """_fallback_to_quart should call RequestMiddleware.post."""

        mock_middleware = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"answer": "Fallback response"})
        mock_middleware.post = AsyncMock(return_value=mock_response)

        service._http_middleware = mock_middleware

        result = await service._fallback_to_quart(123, "test topic", "testuser")

        assert result == {"answer": "Fallback response"}
        mock_middleware.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_semantic_retrieval_calls_middleware(self, service) -> Any:
        """get_semantic_retrieval should call RequestMiddleware.post."""

        mock_middleware = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"context": ["### Товар: Test Product ###\nDescription"]})
        mock_middleware.post = AsyncMock(return_value=mock_response)

        service._http_middleware = mock_middleware

        result = await service.get_semantic_retrieval("coffee")

        assert "Test Product" in result
        mock_middleware.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_retrieval_returns_empty_on_missing_middleware(self, service) -> Any:
        """get_semantic_retrieval should return empty list when middleware is missing (error caught)."""
        service._http_middleware = None

        result = await service.get_semantic_retrieval("test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_ai_answer_handles_indexing(self, service) -> Any:

        mock_middleware = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_middleware.post = AsyncMock(return_value=mock_response)

        service._http_middleware = mock_middleware

        mock_llm_client = MagicMock()
        mock_llm_client.chat_json = AsyncMock(return_value=None)
        service._llm_client = mock_llm_client

        result = await service.get_ai_answer(123, "test topic", "testuser")
        assert result["status"] == "indexing"
