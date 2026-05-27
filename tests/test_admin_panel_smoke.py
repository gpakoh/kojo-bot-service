"""Smoke tests for admin_panel.py handlers (imports and guard clauses)."""
import ast
from pathlib import Path
from typing import Any

import pytest

HANDLERS_DIR = Path(__file__).resolve().parent.parent / "tg_bot" / "handlers"
ADMIN_PANEL_PY = HANDLERS_DIR / "admin_panel.py"


class TestAdminPanelImports:
    def test_core_handlers_import(self) -> Any:
        from tg_bot.handlers.admin_panel import (
            handle_order_action,
            handle_user_action,
            panel_start,
            show_orders_menu,
            show_settings_menu,
            show_users_menu,
        )
        assert callable(panel_start)
        assert callable(show_users_menu)
        assert callable(show_settings_menu)
        assert callable(show_orders_menu)
        assert callable(handle_user_action)
        assert callable(handle_order_action)

    def test_communication_handlers_import(self) -> Any:
        from tg_bot.handlers.admin_panel import (
            handle_thread_action,
            show_communication_center,
            show_thread_view,
        )
        assert callable(show_communication_center)
        assert callable(show_thread_view)
        assert callable(handle_thread_action)

    def test_mgmt_handlers_import(self) -> Any:
        from tg_bot.handlers.admin_panel import (
            show_courier_mgmt,
            show_logo_mgmt,
            show_pickup_mgmt,
            show_proxy_mgmt,
            sync_products_button_action,
        )
        assert callable(show_logo_mgmt)
        assert callable(show_pickup_mgmt)
        assert callable(show_courier_mgmt)
        assert callable(show_proxy_mgmt)
        assert callable(sync_products_button_action)


class TestAdminPanelGuardClauses:
    GUARDED_HANDLERS = {
        "panel_start": ["effective_user is None"],
        "show_order_details": ["effective_user is None", "query is None"],
        "show_orders_menu": ["query is None"],
        "show_users_menu": ["query is None"],
        "handle_user_action": ["query is None"],
        "handle_order_action": ["query is None"],
    }

    @pytest.fixture(scope="class")
    def tree(self) -> ast.Module:
        return ast.parse(ADMIN_PANEL_PY.read_text(encoding="utf-8"))

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
