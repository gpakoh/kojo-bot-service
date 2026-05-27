"""Tests for correlation ID propagation."""
import logging

from tg_bot.infrastructure.correlation import (
    CorrelationIdFilter,
    clear_correlation_id,
    get_correlation_id,
    set_correlation_id,
)


def test_correlation_id_generation() -> None:
    cid = set_correlation_id()
    assert len(cid) == 8
    assert get_correlation_id() == cid


def test_correlation_id_manual() -> None:
    set_correlation_id("manual-123")
    assert get_correlation_id() == "manual-123"


def test_correlation_id_clear() -> None:
    set_correlation_id("abc")
    clear_correlation_id()
    assert get_correlation_id() == "unknown"


class TestCorrelationIdFilter:
    def test_injects_into_log_record(self) -> None:
        clear_correlation_id()
        flt = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        result = flt.filter(record)
        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == "unknown"

    def test_preserves_existing_trace_id(self) -> None:
        set_correlation_id("trace-abc")
        flt = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        flt.filter(record)
        assert record.correlation_id == "trace-abc"
        assert record.trace_id == "trace-abc"
