# Utils/logging_setup.py
import contextvars
import json
import logging
import re
import sys
import threading
import time
from typing import Any

REDACT_PATTERNS = [
    # URL With Credentials
    (re.compile(r'://([^:/@\s]+):([^\s@]+)@'), r'://\1:[REDACTED]@'),
    # Key=value Patterns
    (re.compile(r'(password=["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(token=["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(api[_-]?key=["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(secret[_-]?seed=["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(bottoken=["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(bot[_-]?token=["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1[REDACTED]\3'),
    # JSON Patterns: "key": "value" Or "key":value
    (re.compile(r'"(?:api[_-]?key|token|password|secret)"\s*:\s*"([^"]+)"', re.IGNORECASE), r'"\1":"[REDACTED]"'),
    (re.compile(r'"(?:api[_-]?key|token|password|secret)"\s*:\s*([^",\s}]+)', re.IGNORECASE), r'"\1":[REDACTED]'),
]


class JSONFormatter(logging.Formatter):
    """Structured JSON logs for journald/Loki/ELK ingestion."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Format timestamp as ISO 8601."""
        import datetime
        return datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Inject Correlation_id If Present
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id

        # Inject Exception Info
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Extra Fields From Record
        for key in ("user_id", "bot_id", "order_id", "duration_ms"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        return json.dumps(log_obj, ensure_ascii=False, default=str)


class RedactingFormatter(logging.Formatter):
    """Formatter с redaction секретов и опциональным JSON-выводом (§6.1, §2.1)."""

    def __init__(self, fmt: str | None = None, json_mode: bool = False) -> None:
        super().__init__(fmt)
        self.json_mode = json_mode

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        if not self.json_mode:
            original_message = super().format(record)
            return self._redact_secrets(original_message)

        # JSON Structured Log
        import json
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact_secrets(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id

        if record.exc_info:
            log_obj["exception"] = self._redact_secrets(self.formatException(record.exc_info))

        for key in ("user_id", "bot_id", "order_id", "duration_ms"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        return json.dumps(log_obj, ensure_ascii=False, default=str)

    def _redact_secrets(self, text: str) -> str:
        result = text
        for pattern, replacement in REDACT_PATTERNS:
            result = pattern.sub(replacement, result)
        return result


session_id_var = contextvars.ContextVar('session_id', default='SYSTEM')


class SessionIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = session_id_var.get()
        return True


def setup_logging(log_level: str = "INFO", json_format: bool = True) -> None:
    """Configure root logger."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove Existing Handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        formatter = RedactingFormatter(json_mode=True)
    else:
        formatter = RedactingFormatter(
            "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            json_mode=False,
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Add Correlation Filter
    from tg_bot.infrastructure.correlation import CorrelationIdFilter
    handler.addFilter(CorrelationIdFilter())

    logging.info("Logging configured", extra={"format": "json" if json_format else "text"})


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()

formatter = RedactingFormatter('%(asctime)s - [%(session_id)s] - %(name)s - %(levelname)s - %(message)s')
formatter.converter = time.localtime

handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addFilter(SessionIdFilter())

UNKNOWN_QUESTION_LOGGERS: dict[str, Any] = {}
UNKNOWN_QUESTION_LOGGERS_LOCK = threading.Lock()
