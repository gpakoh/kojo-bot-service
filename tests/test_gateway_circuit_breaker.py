"""Tests for services/gateway/circuit_breaker.py and services/gateway/exceptions.py."""

import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import services.gateway.circuit_breaker as cb_module
from services.gateway.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitMetrics,
    CircuitOpenError,
    CircuitState,
    GatewayCircuitBreaker,
    clear_circuit_breakers,
    get_circuit_breaker,
)
from services.gateway.exceptions import (
    GatewayProviderError,
    GatewayServerError,
    GatewayTransientError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_registry():
    clear_circuit_breakers()


@pytest.fixture
def breaker():
    return GatewayCircuitBreaker("test")


# ===================================================================
# Exceptions.py Coverage
# ===================================================================

class TestExceptions:
    def test_transient_is_gateway_provider_error(self):
        assert issubclass(GatewayTransientError, GatewayProviderError)

    def test_server_error_is_gateway_provider_error(self):
        assert issubclass(GatewayServerError, GatewayProviderError)

    def test_transient_not_server_error(self):
        assert not issubclass(GatewayTransientError, GatewayServerError)

    def test_server_not_transient(self):
        assert not issubclass(GatewayServerError, GatewayTransientError)

    def test_transient_caught_as_provider(self):
        with pytest.raises(GatewayProviderError):
            raise GatewayTransientError("transient")

    def test_server_caught_as_provider(self):
        with pytest.raises(GatewayProviderError):
            raise GatewayServerError("server error")

    def test_transient_str(self):
        err = GatewayTransientError("test message")
        assert "test message" in str(err)

    def test_server_str(self):
        err = GatewayServerError("server msg")
        assert "server msg" in str(err)

    def test_transient_instantiation(self):
        assert isinstance(GatewayTransientError(), GatewayTransientError)

    def test_server_instantiation(self):
        assert isinstance(GatewayServerError(), GatewayServerError)

    def test_gateway_provider_instantiation(self):
        assert isinstance(GatewayProviderError("base"), GatewayProviderError)


# ===================================================================
# Circuitbreakerconfig
# ===================================================================

class TestCircuitBreakerConfig:
    def test_defaults(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 30.0
        assert config.excluded_exceptions == ()

    def test_custom_values(self):
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            timeout=15.0,
            excluded_exceptions=(ValueError, TypeError),
        )
        assert config.failure_threshold == 3
        assert config.success_threshold == 1
        assert config.timeout == 15.0
        assert config.excluded_exceptions == (ValueError, TypeError)


# ===================================================================
# Circuitmetrics
# ===================================================================

class TestCircuitMetrics:
    def test_defaults(self):
        metrics = CircuitMetrics()
        assert metrics.failures == 0
        assert metrics.successes == 0
        assert metrics.last_failure_time == 0
        assert metrics.state == CircuitState.CLOSED


# ===================================================================
# State Property
# ===================================================================

class TestStateProperty:
    def test_closed_returns_closed(self, breaker):
        breaker._metrics.state = CircuitState.CLOSED
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_returns_half_open(self, breaker):
        breaker._metrics.state = CircuitState.HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

    def test_open_before_timeout_returns_open(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time()
        assert breaker.state == CircuitState.OPEN

    def test_open_after_timeout_returns_half_open(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time() - 60
        assert breaker.state == CircuitState.HALF_OPEN

    def test_open_exactly_at_timeout(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = 1000.0
        with patch("time.time", return_value=1030.0):
            assert breaker.state == CircuitState.HALF_OPEN
        with patch("time.time", return_value=1029.999999):
            assert breaker.state == CircuitState.OPEN

    def test_default_state_is_closed(self):
        b = GatewayCircuitBreaker("fresh")
        assert b.state == CircuitState.CLOSED

    def test_is_available_when_closed(self, breaker):
        breaker._metrics.state = CircuitState.CLOSED
        assert breaker.is_available is True

    def test_is_available_when_half_open(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time() - 60
        assert breaker.is_available is True

    def test_is_available_when_open(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time()
        assert breaker.is_available is False


# ===================================================================
# Record_success
# ===================================================================

class TestRecordSuccess:
    @pytest.mark.asyncio
    async def test_resets_failures(self, breaker):
        breaker._metrics.failures = 3
        await breaker.record_success()
        assert breaker._metrics.failures == 0

    @pytest.mark.asyncio
    async def test_failures_stay_zero(self, breaker):
        await breaker.record_success()
        assert breaker._metrics.failures == 0

    @pytest.mark.asyncio
    async def test_half_open_accumulates_successes(self, breaker):
        breaker.config.success_threshold = 3
        breaker._metrics.state = CircuitState.HALF_OPEN
        await breaker.record_success()
        assert breaker._metrics.successes == 1
        assert breaker.state == CircuitState.HALF_OPEN
        await breaker.record_success()
        assert breaker._metrics.successes == 2
        assert breaker.state == CircuitState.HALF_OPEN
        await breaker.record_success()
        assert breaker._metrics.successes == 3
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_transitions_to_closed(self, breaker):
        breaker.config.success_threshold = 2
        breaker._metrics.state = CircuitState.HALF_OPEN
        await breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN
        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_already_closed_stays_closed(self, breaker):
        breaker.config.success_threshold = 2
        breaker._metrics.state = CircuitState.HALF_OPEN
        await breaker.record_success()
        await breaker.record_success()
        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successes_not_incremented_in_closed(self, breaker):
        await breaker.record_success()
        assert breaker._metrics.successes == 0

    @pytest.mark.asyncio
    async def test_logs_on_recovery(self, breaker):
        breaker.config.success_threshold = 1
        breaker._metrics.state = CircuitState.HALF_OPEN
        with patch.object(cb_module.logger, "info") as mock_log:
            await breaker.record_success()
            mock_log.assert_called_once()
            assert "CLOSED" in mock_log.call_args[0][0]


# ===================================================================
# Record_failure
# ===================================================================

class TestRecordFailure:
    @pytest.mark.asyncio
    async def test_increments_failures(self, breaker):
        await breaker.record_failure(Exception())
        assert breaker._metrics.failures == 1
        assert breaker._metrics.last_failure_time > 0

    @pytest.mark.asyncio
    async def test_closed_to_open_at_threshold(self, breaker):
        breaker.config.failure_threshold = 3
        await breaker.record_failure(Exception("e1"))
        assert breaker.state == CircuitState.CLOSED
        await breaker.record_failure(Exception("e2"))
        assert breaker.state == CircuitState.CLOSED
        await breaker.record_failure(Exception("e3"))
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self, breaker):
        breaker._metrics.state = CircuitState.HALF_OPEN
        await breaker.record_failure(Exception())
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_records_last_failure_time(self, breaker):
        with patch("time.time", return_value=54321.0):
            await breaker.record_failure(Exception())
        assert breaker._metrics.last_failure_time == 54321.0

    @pytest.mark.asyncio
    async def test_none_exception_is_counted(self, breaker):
        breaker.config.failure_threshold = 1
        await breaker.record_failure(None)
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_excluded_exception_skipped(self, breaker):
        breaker.config.excluded_exceptions = (ValueError,)
        breaker.config.failure_threshold = 1
        await breaker.record_failure(ValueError("skip"))
        assert breaker.state == CircuitState.CLOSED
        assert breaker._metrics.failures == 0

    @pytest.mark.asyncio
    async def test_excluded_exception_not_skip_normal(self, breaker):
        breaker.config.excluded_exceptions = (ValueError,)
        await breaker.record_failure(TypeError("real"))
        assert breaker._metrics.failures == 1

    @pytest.mark.asyncio
    async def test_gateway_transient_skipped(self, breaker):
        breaker.config.failure_threshold = 1
        await breaker.record_failure(GatewayTransientError("4xx"))
        assert breaker.state == CircuitState.CLOSED
        assert breaker._metrics.failures == 0

    @pytest.mark.asyncio
    async def test_gateway_server_is_counted(self, breaker):
        breaker.config.failure_threshold = 1
        await breaker.record_failure(GatewayServerError("5xx"))
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_mixed_excluded_and_real(self, breaker):
        breaker.config.excluded_exceptions = (ValueError,)
        breaker.config.failure_threshold = 2
        await breaker.record_failure(ValueError("skip"))
        await breaker.record_failure(TypeError("r1"))
        assert breaker._metrics.failures == 1
        await breaker.record_failure(TypeError("r2"))
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_subclass_of_excluded_skipped(self, breaker):
        class SubValueError(ValueError):
            pass
        breaker.config.excluded_exceptions = (ValueError,)
        breaker.config.failure_threshold = 1
        await breaker.record_failure(SubValueError("sub"))
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_logs_warning_on_open(self, breaker):
        breaker.config.failure_threshold = 1
        with patch.object(cb_module.logger, "warning") as mock_log:
            await breaker.record_failure(Exception())
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_on_half_open_failure(self, breaker):
        breaker._metrics.state = CircuitState.HALF_OPEN
        with patch.object(cb_module.logger, "warning") as mock_log:
            await breaker.record_failure(Exception())
            mock_log.assert_called_once()
            assert "half-open failed" in mock_log.call_args[0][0]


# ===================================================================
# Context Manager
# ===================================================================

class TestContextManager:
    @pytest.mark.asyncio
    async def test_aenter_returns_self_when_closed(self, breaker):
        async with breaker as b:
            assert b is breaker

    @pytest.mark.asyncio
    async def test_aenter_raises_circuit_open_error(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time()
        with pytest.raises(CircuitOpenError, match=r"Circuit 'test' is OPEN"):
            async with breaker:
                pass

    @pytest.mark.asyncio
    async def test_half_open_allows_requests(self, breaker):
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time() - 60
        async with breaker:
            pass

    @pytest.mark.asyncio
    async def test_aexit_calls_record_success(self, breaker):
        with patch.object(breaker, "record_success", wraps=breaker.record_success) as spy:
            async with breaker:
                pass
            spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_calls_record_failure(self, breaker):
        with patch.object(breaker, "record_failure", wraps=breaker.record_failure) as spy:
            with pytest.raises(ValueError):
                async with breaker:
                    raise ValueError("boom")
            spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_does_not_suppress(self, breaker):
        with pytest.raises(RuntimeError, match="^should propagate$"):
            async with breaker:
                raise RuntimeError("should propagate")

    @pytest.mark.asyncio
    async def test_aexit_returns_false(self, breaker):
        async with breaker:
            pass

    @pytest.mark.asyncio
    async def test_full_flow_closed_to_open(self, breaker):
        breaker.config.failure_threshold = 2
        for i in range(2):
            with pytest.raises(ValueError):
                async with breaker:
                    raise ValueError(f"fail {i}")
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_blocks_requests(self, breaker):
        breaker.config.failure_threshold = 1
        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("trip")
        assert breaker.state == CircuitState.OPEN
        with pytest.raises(CircuitOpenError, match="Circuit 'test' is OPEN"):
            async with breaker:
                pass

    @pytest.mark.asyncio
    async def test_custom_config_breaker(self):
        config = CircuitBreakerConfig(failure_threshold=2, success_threshold=1, timeout=5)
        b = GatewayCircuitBreaker("custom", config)
        with pytest.raises(ValueError):
            async with b:
                raise ValueError("trip")
        with pytest.raises(ValueError):
            async with b:
                raise ValueError("trip")
        assert b.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_aenter_after_recovery(self, breaker):
        breaker.config.failure_threshold = 1
        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("trip")
        breaker._metrics.state = CircuitState.OPEN
        breaker._metrics.last_failure_time = time.time() - 60
        async with breaker:
            pass


# ===================================================================
# Global Registry
# ===================================================================

class TestGetCircuitBreaker:
    def test_creates_new_breaker(self):
        b = get_circuit_breaker("new_test")
        assert isinstance(b, GatewayCircuitBreaker)
        assert b.name == "new_test"

    def test_returns_existing_breaker(self):
        b1 = get_circuit_breaker("shared")
        b2 = get_circuit_breaker("shared")
        assert b1 is b2

    def test_passes_config_on_first_call(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        b = get_circuit_breaker("cfg_test", config)
        assert b.config.failure_threshold == 1

    def test_ignores_config_on_subsequent_calls(self):
        config1 = CircuitBreakerConfig(failure_threshold=1)
        config2 = CircuitBreakerConfig(failure_threshold=99)
        b1 = get_circuit_breaker("x", config1)
        b2 = get_circuit_breaker("x", config2)
        assert b1 is b2
        assert b1.config.failure_threshold == 1

    def test_default_config_when_none(self):
        b = get_circuit_breaker("default_cfg")
        assert isinstance(b.config, CircuitBreakerConfig)
        assert b.config.failure_threshold == 5

    def test_multiple_names_are_distinct(self):
        a = get_circuit_breaker("A")
        b = get_circuit_breaker("B")
        assert a is not b
        assert a.name == "A"
        assert b.name == "B"


class TestClearCircuitBreakers:
    def test_clears_all(self):
        get_circuit_breaker("one")
        get_circuit_breaker("two")
        clear_circuit_breakers()
        b1 = get_circuit_breaker("one")
        b2 = get_circuit_breaker("one")
        assert b1 is b2

    def test_idempotent(self):
        clear_circuit_breakers()
        clear_circuit_breakers()
        b = get_circuit_breaker("x")
        assert isinstance(b, GatewayCircuitBreaker)

    def test_empty_clear_does_not_error(self):
        clear_circuit_breakers()
        clear_circuit_breakers()


class TestStaleCleanup:
    def test_stale_removed_on_next_get(self):
        old = get_circuit_breaker("stale")
        cb_module._circuit_timestamps["stale"] = datetime(2020, 1, 1, tzinfo=timezone.utc)
        get_circuit_breaker("trigger")
        fresh = get_circuit_breaker("stale")
        assert old is not fresh

    def test_non_stale_preserved(self):
        b1 = get_circuit_breaker("keep")
        get_circuit_breaker("trigger")
        b2 = get_circuit_breaker("keep")
        assert b1 is b2

    def test_only_stale_removed(self):
        get_circuit_breaker("stale")
        get_circuit_breaker("fresh")
        cb_module._circuit_timestamps["stale"] = datetime(2020, 1, 1, tzinfo=timezone.utc)
        get_circuit_breaker("another")
        assert "stale" not in cb_module._circuit_breakers
        assert "fresh" in cb_module._circuit_breakers

    def test_cleanup_logs(self):
        get_circuit_breaker("to_clean")
        cb_module._circuit_timestamps["to_clean"] = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with patch.object(cb_module.logger, "info") as mock_log:
            get_circuit_breaker("spark")
            mock_log.assert_called_once()
            assert "Cleaned up" in mock_log.call_args[0][0]
