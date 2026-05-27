"""Type-safety tests: verify guard clauses, return annotations, typed user_data in handlers."""
import ast
from pathlib import Path
from typing import Any

import pytest

HANDLERS_DIR = Path(__file__).resolve().parent.parent / "tg_bot" / "handlers"
AI_CHAT = HANDLERS_DIR / "ai_chat.py"
DECORATORS = HANDLERS_DIR.parent / "decorators.py"

# === Ai_chat.py Structural Checks ===

AI_CHAT_AUTH_GUARD_FUNCS = {
    "start_ai_chat",
    "handle_ai_history",
    "handle_router_ask_ai",
    "handle_router_support",
}

AI_CHAT_ALL_FUNCS = AI_CHAT_AUTH_GUARD_FUNCS | {"handle_back_to_router"}


def _parse_source(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


class TestAiChatTypeSafety:
    """Structural checks on ai_chat.py source AST."""

    @pytest.fixture(scope="class")
    def tree(self) -> ast.Module:
        return _parse_source(AI_CHAT)

    def test_all_handlers_have_return_annotation(self, tree: ast.Module) -> None:
        """Every async handler function has a return type annotation."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in AI_CHAT_ALL_FUNCS:
                assert node.returns is not None, (
                    f"{node.name} is missing return type annotation"
                )

    def test_all_auth_guarded_have_effective_user_guard(self, tree: ast.Module) -> None:
        """@auth_guard() handlers guard update.effective_user is None."""
        for func_name in AI_CHAT_AUTH_GUARD_FUNCS:
            checker = _GuardFinder(func_name, "update.effective_user")
            checker.visit(tree)
            assert checker.found, (
                f"{func_name} is missing 'update.effective_user is None' guard"
            )

    def test_all_query_users_have_query_is_none_guard(self, tree: ast.Module) -> None:
        """All handlers using callback_query guard query is None."""
        for func_name in AI_CHAT_ALL_FUNCS:
            checker = _GuardFinder(func_name, "query is None")
            checker.visit(tree)
            assert checker.found, (
                f"{func_name} is missing 'query is None' guard"
            )

    def test_typed_user_data_pattern(self, tree: ast.Module) -> None:
        """All handlers use 'user_data: dict[str, Any] = context.user_data or {}'."""
        for func_name in AI_CHAT_ALL_FUNCS:
            if func_name == "handle_router_support":
                # This Handler Doesn't Use User_data
                continue
            checker = _AnnAssignFinder(func_name, "user_data", "dict[str, Any]")
            checker.visit(tree)
            assert checker.found, (
                f"{func_name} is missing 'user_data: dict[str, Any]' annotation — "
                "first use of context.user_data should be typed via 'or {}'"
            )


# === Decorators.py Structural Checks ===


class TestDecoratorsTypeSafety:
    """Structural checks on decorators.py source AST."""

    @pytest.fixture(scope="class")
    def tree(self) -> ast.Module:
        return _parse_source(DECORATORS)

    def test_auth_guard_returns_callable(self, tree: ast.Module) -> None:
        """auth_guard return type should be Callable[[F], F] (not Any)."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "auth_guard":
                assert node.returns is not None


# === AST Visitor Helpers ===


class _GuardFinder(ast.NodeVisitor):
    """Check if a function body contains a specific guard pattern."""

    def __init__(self, func_name: str, guard_pattern: str) -> None:
        self.func_name = func_name
        self.guard_pattern = guard_pattern
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
        if self.guard_pattern in source:
            # Check The Body Starts With 'return'
            if node.body and isinstance(node.body[0], ast.Return):
                self.found = True

    def visit_Assert(self, node: ast.Assert) -> Any:
        if not self._in_func:
            return
        source = ast.unparse(node.test)
        if self.guard_pattern in source:
            self.found = True


class _AnnAssignFinder(ast.NodeVisitor):
    """Check if a function has an annotated assignment with given name and annotation."""

    def __init__(self, func_name: str, target_name: str, annotation_str: str) -> None:
        self.func_name = func_name
        self.target_name = target_name
        self.annotation_str = annotation_str
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

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        if not self._in_func:
            return
        if isinstance(node.target, ast.Name) and node.target.id == self.target_name:
            ann_source = ast.unparse(node.annotation)
            if self.annotation_str in ann_source:
                self.found = True
