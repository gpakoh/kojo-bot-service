"""Smoke tests for handler imports and signatures."""
from typing import Any


class TestHandlerImports:
    def test_registration_handlers_import(self) -> Any:
        from tg_bot.handlers.registration import received_fio, start
        assert callable(start)
        assert callable(received_fio)

    def test_order_handlers_import(self) -> Any:
        from tg_bot.handlers.order import handle_cart_edit_action, start_user_order
        assert callable(start_user_order)
        assert callable(handle_cart_edit_action)

    def test_admin_handlers_import(self) -> Any:
        from tg_bot.handlers.admin_panel import handle_user_action, toggle_auto_approve
        assert callable(handle_user_action)
        assert callable(toggle_auto_approve)

    def test_ai_chat_handler_import(self) -> Any:
        from tg_bot.handlers.ai_chat import handle_router_ask_ai, start_ai_chat
        assert callable(handle_router_ask_ai)
        assert callable(start_ai_chat)
