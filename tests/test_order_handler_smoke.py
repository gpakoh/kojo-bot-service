"""Smoke tests for order.py handlers (imports and guard clauses)."""
import ast
from pathlib import Path
from typing import Any

import pytest

HANDLERS_DIR = Path(__file__).resolve().parent.parent / "tg_bot" / "handlers"
ORDER_PY = HANDLERS_DIR / "order.py"


class TestOrderHandlerImports:
    def test_order_handler_imports(self) -> Any:
        from tg_bot.handlers.order import (
            add_to_cart,
            change_quantity,
            handle_order_restore,
            handle_repeat_order,
            show_categories,
            show_product_list,
            start_user_order,
        )
        assert callable(handle_order_restore)
        assert callable(handle_repeat_order)
        assert callable(start_user_order)
        assert callable(show_categories)
        assert callable(show_product_list)
        assert callable(change_quantity)
        assert callable(add_to_cart)

    def test_wrapper_functions_import(self) -> Any:
        from tg_bot.handlers.order import (
            _finalize_order_and_pay,
            _get_and_cache_all_products,
            _persist_order,
            _send_order_success_message,
            send_order_menu_message,
        )
        assert callable(_get_and_cache_all_products)
        assert callable(send_order_menu_message)
        assert callable(_persist_order)
        assert callable(_finalize_order_and_pay)
        assert callable(_send_order_success_message)


class TestOrderHandlerGuardClauses:
    """Structural checks via AST — verify guard clauses exist in key handlers."""

    # Maps Function Name → List Of Variable/keyword Patterns Expected In Guards
    GUARDED_HANDLERS = {
        "start_user_order": ["effective_user is None"],
        "start_staff_order": ["effective_user is None"],
        "show_categories": ["effective_user is None"],
        "show_product_list": ["effective_user is None"],
        "change_quantity": ["query is None", "effective_user is None"],
        "add_to_cart": ["query is None", "effective_user is None"],
        "handle_order_restore": ["query is None"],
        "handle_repeat_order": ["query is None", "effective_user is None"],
    }

    @pytest.fixture(scope="class")
    def tree(self) -> ast.Module:
        return ast.parse(ORDER_PY.read_text(encoding="utf-8"))

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
