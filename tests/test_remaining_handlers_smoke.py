"""Smoke tests for remaining handler files: info, common, ui_helpers, search_sort."""



class TestInfoHandler:
    def test_info_conversation_exists(self) -> None:
        from tg_bot.handlers.info import info_conversation
        assert info_conversation is not None

    def test_info_conversation_type(self) -> None:
        from telegram.ext import ConversationHandler

        from tg_bot.handlers.info import info_conversation
        assert isinstance(info_conversation, ConversationHandler)


class TestCommonHandler:
    def test_clean_response_exists(self) -> None:
        from tg_bot.handlers.common import clean_response
        assert callable(clean_response)

    def test_cleanup_previous_menu_exists(self) -> None:
        from tg_bot.handlers.common import cleanup_previous_menu
        assert callable(cleanup_previous_menu)

    def test_safe_delete_message_exists(self) -> None:
        from tg_bot.handlers.common import safe_delete_message
        assert callable(safe_delete_message)

    def test_handle_stale_callback_exists(self) -> None:
        from tg_bot.handlers.common import handle_stale_callback
        assert callable(handle_stale_callback)

    def test_clean_response_works(self) -> None:
        from tg_bot.handlers.common import clean_response
        assert clean_response("  hello  ") == "hello"
        assert clean_response("  ") == ""


class TestOrderUiHelpers:
    def test_truncate_caption_exists(self) -> None:
        from tg_bot.handlers.order_ui_helpers import truncate_caption
        assert callable(truncate_caption)

    def test_show_full_description_exists(self) -> None:
        from tg_bot.handlers.order_ui_helpers import show_full_description
        assert callable(show_full_description)

    def test_exit_functions_exist(self) -> None:
        from tg_bot.handlers.order_ui_helpers import done, exit_to_panel, exit_to_user_main_menu
        assert callable(done)
        assert callable(exit_to_panel)
        assert callable(exit_to_user_main_menu)

    def test_truncate_caption_short(self) -> None:
        from tg_bot.handlers.order_ui_helpers import truncate_caption
        result, truncated = truncate_caption("Short text")
        assert result == "Short text"
        assert truncated is False

    def test_truncate_caption_long(self) -> None:
        from tg_bot.handlers.order_ui_helpers import truncate_caption
        long_text = "word " * 500
        result, truncated = truncate_caption(long_text, limit=100)
        assert truncated is True
        assert len(result) <= 100 + 4  # limit + "..."

    def test_truncate_caption_paragraph(self) -> None:
        from tg_bot.handlers.order_ui_helpers import truncate_caption
        text = "Long paragraph.\n\nAnother paragraph.\n\nAnd another."
        result, truncated = truncate_caption(text, limit=30)
        assert truncated is True


class TestSearchSort:
    def test_toggle_view_exists(self) -> None:
        from tg_bot.handlers.order_search_sort import toggle_view
        assert callable(toggle_view)

    def test_show_sort_menu_exists(self) -> None:
        from tg_bot.handlers.order_search_sort import show_sort_menu
        assert callable(show_sort_menu)

    def test_search_functions_exist(self) -> None:
        from tg_bot.handlers.order_search_sort import (
            ask_search_query,
            handle_semantic_search,
            process_search,
        )
        assert callable(ask_search_query)
        assert callable(process_search)
        assert callable(handle_semantic_search)
