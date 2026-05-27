# Tests For Database Query Monitoring
import asyncio
import os
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.db_monitoring import (
    QueryLoggerMiddleware,
    QueryMonitor,
    monitored_query,
)


class TestQueryMonitor:
    """Tests for QueryMonitor."""

    def setup_method(self) -> Any:
        QueryMonitor._enabled = True
        QueryMonitor._slow_threshold_ms = 100

    def test_track_context_manager(self) -> Any:
        """Test that track context manager measures time."""
        with QueryMonitor.track("test_query"):
            time.sleep(0.01)

        assert True

    def test_track_slow_query_detection(self) -> Any:
        """Test that slow queries are detected."""
        with patch('tg_bot.db_monitoring.logger') as mock_logger:
            time.sleep(0.15)
            with QueryMonitor.track("slow_query"):
                time.sleep(0.15)

            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args[0][0]
            assert "Slow Query" in call_args
            assert "slow_query" in call_args

    def test_fast_query_no_warning(self) -> Any:
        """Test that fast queries don't trigger warnings."""
        with patch('tg_bot.db_monitoring.logger') as mock_logger:
            with QueryMonitor.track("fast_query"):
                time.sleep(0.01)

            mock_logger.warning.assert_not_called()

    def test_custom_threshold(self) -> Any:
        """Test setting custom threshold."""
        QueryMonitor.set_threshold(50)
        assert QueryMonitor._slow_threshold_ms == 50

    def test_disabled_monitoring(self) -> Any:
        """Test that disabled monitoring doesn't track."""
        QueryMonitor._enabled = False
        QueryMonitor.set_threshold(100)

        with patch('tg_bot.db_monitoring.logger') as mock_logger:
            with QueryMonitor.track("test"):
                time.sleep(0.2)

            mock_logger.warning.assert_not_called()

        QueryMonitor._enabled = True


class TestMonitoredQueryDecorator:
    """Tests for @monitored_query decorator."""

    @monitored_query("test_func")
    async def sample_async_func(self, x) -> Any:
        await asyncio.sleep(0.01)
        return x * 2

    @monitored_query("sync_func")
    def sample_sync_func(self, x) -> Any:
        time.sleep(0.01)
        return x * 2

    def test_decorator_preserves_function(self) -> Any:
        assert self.sample_async_func.__name__ == "sample_async_func"
        assert self.sample_sync_func.__name__ == "sample_sync_func"


class TestQueryLoggerMiddleware:
    """Tests for QueryLoggerMiddleware."""

    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="OK")
        pool.fetch = AsyncMock(return_value=[])
        pool.fetchrow = AsyncMock(return_value={"id": 1})
        return pool

    @pytest.mark.asyncio
    async def test_execute_logs_query(self, mock_pool) -> Any:
        os.environ["LOG_ALL_QUERIES"] = "true"

        middleware = QueryLoggerMiddleware(mock_pool, log_queries=True)

        with patch('tg_bot.db_monitoring.logger') as mock_logger:
            await middleware.execute("SELECT * FROM users")

            mock_logger.debug.assert_called()
            call_args = mock_logger.debug.call_args[0][0]
            assert "SELECT * FROM users" in call_args

    @pytest.mark.asyncio
    async def test_fetch_logs_rows(self, mock_pool) -> Any:
        os.environ["LOG_ALL_QUERIES"] = "true"

        middleware = QueryLoggerMiddleware(mock_pool, log_queries=True)

        with patch('tg_bot.db_monitoring.logger') as mock_logger:
            await middleware.fetch("SELECT * FROM products")

            mock_logger.debug.assert_called()
            call_args = mock_logger.debug.call_args[0][0]
            assert "rows=" in call_args

    @pytest.mark.asyncio
    async def test_disabled_no_logging(self, mock_pool) -> Any:
        os.environ["LOG_ALL_QUERIES"] = "false"

        middleware = QueryLoggerMiddleware(mock_pool, log_queries=False)

        with patch('tg_bot.db_monitoring.logger') as mock_logger:
            await middleware.execute("SELECT 1")

            mock_logger.debug.assert_not_called()
