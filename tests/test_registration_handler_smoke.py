"""Smoke tests for registration.py handlers (imports and guard clauses)."""
import ast
from pathlib import Path
from typing import Any

import pytest

HANDLERS_DIR = Path(__file__).resolve().parent.parent / "tg_bot" / "handlers"
REGISTRATION_PY = HANDLERS_DIR / "registration.py"


class TestRegistrationHandlerImports:
    def test_core_handler_imports(self) -> Any:
        from tg_bot.handlers.registration import (
            cancel_registration,
            received_email,
            received_fio,
            received_phone,
            start,
            start_fio_step,
        )
        assert callable(start)
        assert callable(start_fio_step)
        assert callable(received_fio)
        assert callable(received_email)
        assert callable(received_phone)
        assert callable(cancel_registration)

    def test_ui_handler_imports(self) -> Any:
        from tg_bot.handlers.registration import (
            handle_approval_callback,
            invalid_phone_input,
            show_main_menu_from_welcome,
            show_staff_main_menu,
            show_unauthorized_gate,
        )
        assert callable(handle_approval_callback)
        assert callable(invalid_phone_input)
        assert callable(show_main_menu_from_welcome)
        assert callable(show_staff_main_menu)
        assert callable(show_unauthorized_gate)

    def test_internal_function_imports(self) -> Any:
        from tg_bot.handlers.registration import (
            _check_start_redirections,
            _handle_deep_link,
            _handle_staff_entry,
            _send_welcome_ui,
        )
        assert callable(_check_start_redirections)
        assert callable(_handle_deep_link)
        assert callable(_handle_staff_entry)
        assert callable(_send_welcome_ui)

    def test_conversation_handler_import(self) -> Any:
        from tg_bot.handlers.registration import (
            AWAITING_EMAIL,
            AWAITING_FIO,
            AWAITING_PHONE,
            registration_handler,
        )
        assert AWAITING_EMAIL == 1
        assert AWAITING_FIO == 0
        assert AWAITING_PHONE == 2
        assert registration_handler.name == "registration_conversation"


class TestRegistrationHandlerGuardClauses:
    """Structural checks via AST — verify guard clauses exist in key handlers."""

    GUARDED_HANDLERS = {
        "start": ["effective_user is None"],
        "start_fio_step": ["effective_user is None"],
        "received_fio": ["effective_user is None", "update.message is None"],
        "received_email": ["effective_user is None", "update.message is None"],
        "received_phone": ["effective_user is None"],
        "cancel_registration": ["effective_user is None"],
        "handle_approval_callback": ["query is None", "effective_user is None"],
        "show_unauthorized_gate": ["effective_user is None"],
        "show_main_menu_from_welcome": ["effective_user is None"],
        "show_staff_main_menu": ["effective_user is None"],
        "invalid_phone_input": ["effective_user is None"],
        "_handle_deep_link": ["effective_user is None"],
        "_check_start_redirections": ["effective_user is None"],
    }

    @pytest.fixture(scope="class")
    def tree(self) -> ast.Module:
        return ast.parse(REGISTRATION_PY.read_text(encoding="utf-8"))

    def test_guard_clauses_present(self, tree: ast.Module) -> None:
        for func_name, expected_guards in self.GUARDED_HANDLERS.items():
            for guard in expected_guards:
                checker = _GuardFinder(func_name, guard)
                checker.visit(tree)
                assert checker.found, (
                    f"{func_name} missing guard for '{guard}'"
                )


class _GuardFinder(ast.NodeVisitor):
    def __init__(self, func_name: str, guard_keyword: str) -> None:
        self.func_name = func_name
        self.guard_keyword = guard_keyword
        self.found = False
        self._in_func = False

    def _enter_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> Any:
        if node.name == self.func_name:
            self._in_func = True
            self.generic_visit(node)
            self._in_func = False
            return
        if not self._in_func:
            self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        return self._enter_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        return self._enter_func(node)

    def visit_If(self, node: ast.If) -> Any:
        if not self._in_func:
            return
        source = ast.unparse(node.test)
        if self.guard_keyword in source:
            if node.body and isinstance(node.body[0], ast.Return):
                self.found = True

    def visit_Assert(self, node: ast.Assert) -> Any:
        if not self._in_func:
            return
        source = ast.unparse(node.test)
        if self.guard_keyword in source:
            self.found = True
