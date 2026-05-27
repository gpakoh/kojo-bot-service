# Tests For Utils/logging_setup.py
import json as json_lib
import logging
import sys
from typing import Any

from utils.logging_setup import REDACT_PATTERNS, RedactingFormatter


class TestRedactingFormatter:
    def _make_record(self, message: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=message, args=(), exc_info=None
        )

    def test_url_credentials_redacted(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('Connecting to postgresql://user:secret123@host.com/db')
        result = formatter.format(record)
        assert 'secret123' not in result
        assert 'user:[REDACTED]@host.com' in result

    def test_password_pattern_redacted(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('Auth failed: password="mysecretpass"')
        result = formatter.format(record)
        assert 'mysecretpass' not in result
        assert '[REDACTED]' in result

    def test_token_pattern_redacted(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('token=abc123xyz789')
        result = formatter.format(record)
        assert 'abc123xyz789' not in result
        assert '[REDACTED]' in result

    def test_api_key_pattern_redacted(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('api_key=sk_test_123456789')
        result = formatter.format(record)
        assert 'sk_test_123456789' not in result
        assert '[REDACTED]' in result

    def test_bot_token_pattern_redacted(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('bot_token=123456:ABC-DEF')
        result = formatter.format(record)
        assert '123456:ABC-DEF' not in result
        assert '[REDACTED]' in result

    def test_empty_message(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('Normal message without secrets')
        result = formatter.format(record)
        assert result == 'Normal message without secrets'

    def test_multiple_credentials_in_url(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('postgres://user:pass@host1.com postgres://user2:pass2@host2.com')
        result = formatter.format(record)
        assert 'user:[REDACTED]@host1.com' in result
        assert 'user2:[REDACTED]@host2.com' in result
        assert result.count('[REDACTED]') == 2

    def test_case_insensitive_password(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('PASSWORD="UpperCasePass123"')
        result = formatter.format(record)
        assert 'UpperCasePass123' not in result
        assert '[REDACTED]' in result

    def test_secret_seed_pattern_redacted(self) -> Any:
        formatter = RedactingFormatter('%(message)s')
        record = self._make_record('paykeeper_secret_seed=abc_secret_seed_xyz')
        result = formatter.format(record)
        assert 'abc_secret_seed_xyz' not in result
        assert '[REDACTED]' in result


class TestRedactPatterns:
    def test_patterns_are_compiled(self) -> Any:
        assert len(REDACT_PATTERNS) > 0
        for pattern, replacement in REDACT_PATTERNS:
            assert hasattr(pattern, 'search') or hasattr(pattern, 'sub')
            assert isinstance(replacement, str)

    def test_url_credential_pattern(self) -> Any:
        pattern = REDACT_PATTERNS[0][0]
        text = 'postgresql://user:secret@host.com'
        result = pattern.sub(REDACT_PATTERNS[0][1], text)
        assert 'secret' not in result
        assert 'user:[REDACTED]@host.com' in result


class TestJSONFormatter:
    def _make_record(self, message: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=message, args=(), exc_info=None
        )

    def test_json_output_structure(self) -> None:
        formatter = RedactingFormatter(json_mode=True)
        record = self._make_record("Test message")
        result = formatter.format(record)
        parsed = json_lib.loads(result)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed
        assert "logger" in parsed

    def test_json_redacts_secrets(self) -> None:
        formatter = RedactingFormatter(json_mode=True)
        record = self._make_record("token=secret123")
        result = formatter.format(record)
        parsed = json_lib.loads(result)
        assert "secret123" not in parsed["message"]
        assert "[REDACTED]" in parsed["message"]

    def test_json_includes_exception(self) -> None:
        formatter = RedactingFormatter(json_mode=True)
        try:
            raise ValueError("test error")
        except ValueError:
            record = self._make_record("error occurred")
            record.exc_info = sys.exc_info()

        result = formatter.format(record)
        parsed = json_lib.loads(result)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
