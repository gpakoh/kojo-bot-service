"""Smoke tests for infrastructure core files."""


class TestDatabaseImports:
    def test_database_manager_import(self) -> None:
        from tg_bot.infrastructure.database import DatabaseManager
        assert DatabaseManager is not None

    def test_database_class_import(self) -> None:
        from tg_bot.infrastructure.database import Database, DatabaseError
        assert Database is not None
        assert DatabaseError is not None

    def test_transaction_context(self) -> None:
        from tg_bot.infrastructure.database import DatabaseManager
        assert hasattr(DatabaseManager, 'transaction')

    def test_init_extensions_import(self) -> None:
        from tg_bot.infrastructure.database import init_db_extensions
        assert callable(init_db_extensions)


class TestHealthImports:
    def test_health_check_class_import(self) -> None:
        from tg_bot.infrastructure.health import HealthCheck
        assert HealthCheck is not None

    def test_get_health_check_import(self) -> None:
        from tg_bot.infrastructure.health import get_health_check
        assert callable(get_health_check)

    def test_health_app_import(self) -> None:
        from tg_bot.infrastructure.health_server import create_health_app
        assert callable(create_health_app)

    def test_health_handlers_import(self) -> None:
        from tg_bot.infrastructure.health_server import health_handler, metrics_handler, ready_handler
        assert callable(health_handler)
        assert callable(ready_handler)
        assert callable(metrics_handler)

    def test_start_health_server_import(self) -> None:
        from tg_bot.infrastructure.health_server import start_health_server
        assert callable(start_health_server)


class TestMetricsImports:
    def test_metrics_registry(self) -> None:
        from tg_bot.infrastructure.metrics import REGISTRY, kojo_order_value_sum, kojo_orders_total
        assert REGISTRY is not None
        assert kojo_orders_total is not None
        assert kojo_order_value_sum is not None

    def test_observe_latency_decorator(self) -> None:
        from tg_bot.infrastructure.metrics import observe_latency
        assert callable(observe_latency)

    def test_all_metrics_exist(self) -> None:
        from tg_bot.infrastructure.metrics import (
            kojo_active_users,
            kojo_db_query_duration_seconds,
            kojo_llm_latency_seconds,
            kojo_proxy_failover_count,
        )
        assert kojo_llm_latency_seconds is not None
        assert kojo_proxy_failover_count is not None
        assert kojo_db_query_duration_seconds is not None
        assert kojo_active_users is not None
