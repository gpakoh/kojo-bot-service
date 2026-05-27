import json
import logging

from tg_bot.infrastructure.alerting import TelegramAlertHandler
from tg_bot.infrastructure.correlation import clear_correlation_id, get_correlation_id, set_correlation_id
from tg_bot.infrastructure.metrics import kojo_orders_total, kojo_proxy_failover_count


class TestCorrelationIntegration:
    def test_correlation_flows_through_context(self) -> None:
        set_correlation_id("test-abc-123")
        assert get_correlation_id() == "test-abc-123"
        clear_correlation_id()
        assert get_correlation_id() == "unknown"


class TestMetricsIntegration:
    def test_order_metric_increments(self) -> None:
        before = kojo_orders_total.labels(status="Принят", tenant_id="default")._value.get()
        kojo_orders_total.labels(status="Принят", tenant_id="default").inc()
        assert kojo_orders_total.labels(status="Принят", tenant_id="default")._value.get() == before + 1

    def test_proxy_failover_metric(self) -> None:
        before = kojo_proxy_failover_count.labels(bot_id="kojo")._value.get()
        kojo_proxy_failover_count.labels(bot_id="kojo").inc()
        assert kojo_proxy_failover_count.labels(bot_id="kojo")._value.get() == before + 1


class TestJSONLogging:
    def test_json_formatter_structure(self) -> None:
        from utils.logging_setup import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="hello %(user)s", args=({"user": "world"},),
            exc_info=None,
        )
        # Set Correlation_id
        record.correlation_id = "cid-123"  # type: ignore[attr-defined]

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert "message" in parsed
        assert parsed["correlation_id"] == "cid-123"
        assert "timestamp" in parsed


class TestAlerting:
    def test_alert_handler_skips_without_app(self) -> None:
        handler = TelegramAlertHandler("token", "123")
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=1,
            msg="boom", args=(), exc_info=None,
        )
        # Should Not Raise Even Without App
        handler.emit(record)
