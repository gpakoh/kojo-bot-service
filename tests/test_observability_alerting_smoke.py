"""Smoke tests for observability middleware, alerting, observability."""
from typing import Any


class TestObservabilityMiddlewareImports:
    def test_middleware_import(self) -> Any:
        from tg_bot.infrastructure.observability_middleware import (
            ObservabilityMiddleware,
        )
        assert ObservabilityMiddleware is not None

    def test_middleware_callable(self) -> Any:
        from tg_bot.infrastructure.observability_middleware import (
            ObservabilityMiddleware,
        )
        assert hasattr(ObservabilityMiddleware, "__call__")

    def test_metrics_endpoint_import(self) -> Any:
        from tg_bot.infrastructure.observability_middleware import (
            metrics_endpoint,
        )
        assert callable(metrics_endpoint)

    def test_health_endpoint_import(self) -> Any:
        from tg_bot.infrastructure.observability_middleware import (
            health_endpoint,
        )
        assert callable(health_endpoint)


class TestAlertingImports:
    def test_telegram_alert_handler_import(self) -> Any:
        from tg_bot.infrastructure.alerting import TelegramAlertHandler
        assert TelegramAlertHandler is not None

    def test_telegram_alert_handler_emit(self) -> Any:
        from tg_bot.infrastructure.alerting import TelegramAlertHandler
        assert hasattr(TelegramAlertHandler, "emit")

    def test_setup_alerting_import(self) -> Any:
        from tg_bot.infrastructure.alerting import setup_alerting
        assert callable(setup_alerting)


class TestObservabilityImports:
    def test_record_request_import(self) -> Any:
        from tg_bot.infrastructure.observability import record_request
        assert callable(record_request)

    def test_record_duration_import(self) -> Any:
        from tg_bot.infrastructure.observability import (
            record_request_duration,
        )
        assert callable(record_request_duration)

    def test_get_metrics_registry_import(self) -> Any:
        from tg_bot.infrastructure.observability import (
            get_metrics_registry,
        )
        assert callable(get_metrics_registry)

    def test_get_structured_logger_import(self) -> Any:
        from tg_bot.infrastructure.observability import (
            get_structured_logger,
        )
        assert callable(get_structured_logger)


class TestStructuredLogger:
    def test_structured_logger_creation(self) -> Any:
        from tg_bot.infrastructure.observability import (
            get_structured_logger,
        )
        logger = get_structured_logger("test")
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
