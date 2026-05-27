"""
Correlation ID (distributed tracing lite) for logs and HTTP headers.
"""
import uuid
from contextvars import ContextVar
from typing import Any, Optional

_CORRELATION_ID: ContextVar[str] = ContextVar("correlation_id", default="")


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set or generate correlation ID for current context."""
    new_id = cid or str(uuid.uuid4())[:8]
    _CORRELATION_ID.set(new_id)
    return new_id


def get_correlation_id() -> str:
    return _CORRELATION_ID.get() or "unknown"


def clear_correlation_id() -> None:
    _CORRELATION_ID.set("")


class CorrelationIdFilter:
    """Logging filter that injects correlation_id/trace_id into LogRecord."""
    def filter(self, record: Any) -> bool:
        record.correlation_id = get_correlation_id()
        record.trace_id = record.correlation_id  # Alias for OpenTelemetry compat
        return True
