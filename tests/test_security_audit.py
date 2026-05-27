"""Security audit tests: verify no print(), raw os.environ in handlers."""
import ast
from pathlib import Path
from typing import Any

import pytest

HANDLERS_DIR = Path("tg_bot/handlers")


class TestNoPrintInHandlers:
    def test_handlers_no_print_calls(self) -> Any:
        """Verify all handler files use logger, not print()."""
        violations = []

        for py_file in sorted(HANDLERS_DIR.rglob("*.py")):
            content = py_file.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "print":
                        violations.append(f"{py_file}:{node.lineno}")

        assert not violations, f"print() found in handlers: {violations}"

    def test_test_db_schema_no_print(self) -> Any:
        """Verify test_db_schema.py uses logger, not print()."""
        path = Path("tg_bot/test_db_schema.py")
        content = path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    pytest.fail(f"print() found in {path}:{node.lineno}")


class TestNoRawEnvironForSecrets:
    def test_no_plaintext_secrets_in_source(self) -> Any:
        """Verify no BOT_TOKEN = '...' hardcoded in source."""
        tg_bot_dir = Path("tg_bot")
        violations = []

        for py_file in tg_bot_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            if 'BOT_TOKEN' in content and '=' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'BOT_TOKEN' in line and '=' in line and "'" in line:
                        violations.append(f"{py_file}:{i+1}")

        assert not violations, f"Potential hardcoded secrets: {violations}"

    def test_no_secrets_via_os_environ_in_handlers(self) -> Any:
        """Verify handlers don't read secret-like keys via os.environ (use SecretsLoader)."""
        secret_hints = ["BOT_TOKEN", "TOKEN", "SECRET", "PASSWORD"]
        handlers_dir = Path("tg_bot/handlers")
        violations = []

        for py_file in handlers_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'os.environ' in line:
                    for hint in secret_hints:
                        if hint in line.upper():
                            violations.append(f"{py_file}:{i+1}")

        assert not violations, f"Possible secrets via raw os.environ in handlers: {violations}"


class TestNoTodoInEventHandlers:
    def test_no_todo_in_order_event_handler(self) -> Any:
        """Verify TODO/FIXME removed from order_event_handler.py."""
        path = Path("tg_bot/application/event_handlers/order_event_handler.py")
        content = path.read_text()
        lines = content.split('\n')
        violations = [
            f"{path}:{i+1}" for i, line in enumerate(lines)
            if 'TODO' in line or 'FIXME' in line
        ]
        assert not violations, f"TODO/FIXME found: {violations}"

    def test_no_todo_in_admin_panel(self) -> Any:
        """Verify TODO/FIXME removed from admin_panel.py handlers."""
        path = Path("tg_bot/handlers/admin_panel.py")
        content = path.read_text()
        lines = content.split('\n')
        violations = [
            f"{path}:{i+1}" for i, line in enumerate(lines)
            if ('TODO' in line or 'FIXME' in line) and 'NOTE:' not in line
        ]
        assert not violations, f"TODO/FIXME found: {violations}"
