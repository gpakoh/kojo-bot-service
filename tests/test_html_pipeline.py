"""Tests for unified HTML sanitize pipeline."""
from typing import Any

from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram


class TestHTMLPipeline:
    def test_removes_script_tag(self) -> Any:
        result = prepare_html_for_telegram("<script>alert(1)</script>Hello")
        assert "<script" not in result.lower()
        assert "Hello" in result

    def test_removes_onclick(self) -> Any:
        result = prepare_html_for_telegram('<div onclick="evil()">Click</div>')
        assert "onclick" not in result.lower()

    def test_preserves_allowed_tags(self) -> Any:
        result = prepare_html_for_telegram(
            "<b>Bold</b> <i>Italic</i> <a href='https://x.com'>Link</a>"
        )
        assert "<b>" in result
        assert "<i>" in result
        assert "<a href=" in result

    def test_removes_javascript_href(self) -> Any:
        result = prepare_html_for_telegram('<a href="javascript:alert(1)">X</a>')
        assert "javascript:" not in result.lower()

    def test_empty_string(self) -> Any:
        assert prepare_html_for_telegram("") == ""

    def test_none_string(self) -> Any:
        assert prepare_html_for_telegram(None) == ""
