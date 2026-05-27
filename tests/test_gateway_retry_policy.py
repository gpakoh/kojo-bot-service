"""Comprehensive tests for services/gateway/retry_policy.py."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.gateway.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenError,
    GatewayCircuitBreaker,
)
from services.gateway.retry_policy import RetryConfig, RetryPolicy, retry_with_policy


class TestRetryConfig:
    """RetryConfig dataclass defaults and custom initialisation."""

    def test_default_values(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_attempts == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 30.0
        assert cfg.exponential_base == 2.0
        assert cfg.jitter is True
        assert httpx.TimeoutException in cfg.retry_on_exceptions
        assert httpx.ConnectError in cfg.retry_on_exceptions
        assert httpx.NetworkError in cfg.retry_on_exceptions
        assert httpx.RemoteProtocolError in cfg.retry_on_exceptions
        assert cfg.retry_on_status_codes == (500, 502, 503, 504, 429)

    def test_custom_values(self) -> None:
        cfg = RetryConfig(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            exponential_base=3.0,
            jitter=False,
            retry_on_exceptions=(ValueError,),
            retry_on_status_codes=(503,),
        )
        assert cfg.max_attempts == 5
        assert cfg.base_delay == 0.5
        assert cfg.max_delay == 10.0
        assert cfg.exponential_base == 3.0
        assert cfg.jitter is False
        assert cfg.retry_on_exceptions == (ValueError,)
        assert cfg.retry_on_status_codes == (503,)


class TestRetryPolicyInit:
    """RetryPolicy initialisation paths."""

    def test_default_config(self) -> None:
        policy = RetryPolicy()
        assert policy.config.max_attempts == 3

    def test_custom_config(self) -> None:
        cfg = RetryConfig(max_attempts=5)
        policy = RetryPolicy(cfg)
        assert policy.config.max_attempts == 5

    def test_none_config_falls_back_to_default(self) -> None:
        policy = RetryPolicy(None)
        assert policy.config.max_attempts == 3


class TestCalculateDelay:
    """Exponential backoff with and without jitter."""

    def test_without_jitter_exact_values(self) -> None:
        policy = RetryPolicy(RetryConfig(jitter=False, base_delay=1.0, exponential_base=2.0))
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 4.0
        assert policy.calculate_delay(3) == 8.0
        assert policy.calculate_delay(4) == 16.0

    def test_without_jitter_max_delay_clamping(self) -> None:
        policy = RetryPolicy(RetryConfig(jitter=False, base_delay=10.0, max_delay=15.0, exponential_base=2.0))
        assert policy.calculate_delay(0) == 10.0
        assert policy.calculate_delay(1) == 15.0
        # 10*2^2=40, Clamped To 15
        assert policy.calculate_delay(2) == 15.0

    def test_with_jitter_within_range(self) -> None:
        policy = RetryPolicy(RetryConfig(jitter=True, base_delay=2.0, exponential_base=1.0, max_delay=100.0))
        # Base=2, No Exponential Growth, Jitter=0.5-1.5 → Range 1.0-3.0
        for _ in range(50):
            d = policy.calculate_delay(0)
            assert 1.0 <= d <= 3.0, f"Delay {d} out of expected range"

    def test_with_jitter_uses_random(self) -> None:
        with patch("random.random", return_value=0.5):
            policy = RetryPolicy(RetryConfig(jitter=True, base_delay=2.0, exponential_base=1.0, max_delay=100.0))
            delay = policy.calculate_delay(0)
            # 2.0 * (0.5 + 0.5) = 2.0
            assert delay == 2.0


class TestShouldRetry:
    """Retry decision logic for exceptions and status codes."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy()

    def test_circuit_open_error_never_retried(self) -> None:
        assert self.policy.should_retry(CircuitOpenError("open")) is False

    def test_circuit_open_error_takes_priority_over_status(self) -> None:
        assert self.policy.should_retry(CircuitOpenError("open"), status_code=500) is False

    def test_retryable_status_code_500(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=500) is True

    def test_retryable_status_code_502(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=502) is True

    def test_retryable_status_code_503(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=503) is True

    def test_retryable_status_code_504(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=504) is True

    def test_retryable_status_code_429(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=429) is True

    def test_non_retryable_status_code(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=200) is False
        assert self.policy.should_retry(RuntimeError("x"), status_code=404) is False
        assert self.policy.should_retry(RuntimeError("x"), status_code=400) is False

    def test_retryable_exception_httpx_timeout(self) -> None:
        assert self.policy.should_retry(httpx.TimeoutException("t")) is True

    def test_retryable_exception_connect_error(self) -> None:
        assert self.policy.should_retry(httpx.ConnectError("c")) is True

    def test_retryable_exception_network_error(self) -> None:
        assert self.policy.should_retry(httpx.NetworkError("n")) is True

    def test_retryable_exception_remote_protocol_error(self) -> None:
        assert self.policy.should_retry(httpx.RemoteProtocolError("r")) is True

    def test_non_retryable_exception(self) -> None:
        assert self.policy.should_retry(ValueError("bad")) is False
        assert self.policy.should_retry(KeyError("k")) is False
        assert self.policy.should_retry(RuntimeError("r")) is False

    def test_none_status_and_retryable_exception(self) -> None:
        assert self.policy.should_retry(httpx.TimeoutException("t"), status_code=None) is True

    def test_none_status_and_non_retryable_exception(self) -> None:
        assert self.policy.should_retry(RuntimeError("r"), status_code=None) is False

    def test_custom_retry_on_exceptions(self) -> None:
        policy = RetryPolicy(RetryConfig(retry_on_exceptions=(ValueError,)))
        assert policy.should_retry(ValueError("v")) is True
        assert policy.should_retry(httpx.TimeoutException("t")) is False

    def test_empty_retry_on_status_codes(self) -> None:
        policy = RetryPolicy(RetryConfig(retry_on_status_codes=()))
        assert policy.should_retry(RuntimeError("x"), status_code=500) is False

    def test_empty_retry_on_exceptions(self) -> None:
        policy = RetryPolicy(RetryConfig(retry_on_exceptions=()))
        assert policy.should_retry(httpx.TimeoutException("t")) is False

    def test_httpx_response_not_an_exception_status_check(self) -> None:
        assert self.policy.should_retry(RuntimeError("x"), status_code=503) is True
        assert self.policy.should_retry(RuntimeError("x"), status_code=200) is False


class TestExecute:
    """Main retry execution loop — success, retry, exhaustion, edge cases."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self) -> None:
        policy = RetryPolicy()
        func = AsyncMock(return_value="success")
        result = await policy.execute(func)
        assert result == "success"
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_and_eventually_succeeds(self) -> None:
        cfg = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=[httpx.TimeoutException("t"), httpx.TimeoutException("t"), "ok"])
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await policy.execute(func)
        assert result == "ok"
        assert func.await_count == 3
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self) -> None:
        cfg = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=httpx.TimeoutException("always fail"))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.TimeoutException, match="always fail"):
                await policy.execute(func)
        assert func.await_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_exception_raises_immediately(self) -> None:
        cfg = RetryConfig(max_attempts=3, retry_on_exceptions=(KeyError,))
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=ValueError("no retry"))
        with pytest.raises(ValueError, match="no retry"):
            await policy.execute(func)
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_retryable_exception_skips_sleep(self) -> None:
        cfg = RetryConfig(max_attempts=3, retry_on_exceptions=(KeyError,))
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=ValueError("skip"))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ValueError):
                await policy.execute(func)
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_open_error_raises_immediately(self) -> None:
        policy = RetryPolicy()
        func = AsyncMock(side_effect=CircuitOpenError("circuit open"))
        with pytest.raises(CircuitOpenError, match="circuit open"):
            await policy.execute(func)
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_response_with_retryable_status_retries(self) -> None:
        cfg = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 503
        func = AsyncMock(return_value=resp)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await policy.execute(func)
        assert result.status_code == 503
        assert func.await_count == 3

    @pytest.mark.asyncio
    async def test_response_retryable_status_then_success(self) -> None:
        cfg = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        resp_503 = MagicMock(spec=httpx.Response)
        resp_503.status_code = 503
        func = AsyncMock(side_effect=[resp_503, "success"])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await policy.execute(func)
        assert result == "success"
        assert func.await_count == 2

    @pytest.mark.asyncio
    async def test_retryable_status_on_last_attempt_returns_response(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        func = AsyncMock(return_value=resp)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await policy.execute(func)
        assert result.status_code == 429
        assert func.await_count == 2
        assert mock_sleep.await_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_response_status_returns_immediately(self) -> None:
        policy = RetryPolicy()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        func = AsyncMock(return_value=resp)
        result = await policy.execute(func)
        assert result.status_code == 200
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_max_attempts_one_exception_fails_immediately(self) -> None:
        cfg = RetryConfig(max_attempts=1, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=httpx.TimeoutException("fail"))
        with pytest.raises(httpx.TimeoutException):
            await policy.execute(func)
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_max_attempts_one_success(self) -> None:
        cfg = RetryConfig(max_attempts=1)
        policy = RetryPolicy(cfg)
        func = AsyncMock(return_value="ok")
        result = await policy.execute(func)
        assert result == "ok"
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_max_attempts_zero_raises_runtime_error(self) -> None:
        cfg = RetryConfig(max_attempts=0)
        policy = RetryPolicy(cfg)
        func = AsyncMock(return_value="unreachable")
        with pytest.raises(RuntimeError, match="Retry policy exhausted with no exception"):
            await policy.execute(func)
        func.assert_not_called()

    @pytest.mark.asyncio
    async def test_response_with_different_retryable_codes(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        for code in (500, 502, 504):
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = code
            func = AsyncMock(return_value=resp)
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await policy.execute(func)
            assert result.status_code == code

    @pytest.mark.asyncio
    async def test_retryable_exception_multiple_types(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        for exc in (httpx.ConnectError("c"), httpx.NetworkError("n"), httpx.RemoteProtocolError("r")):
            func = AsyncMock(side_effect=[exc, "recovered"])
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await policy.execute(func)
            assert result == "recovered"

    @pytest.mark.asyncio
    async def test_mixed_retryable_exception_and_response(self) -> None:
        cfg = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        resp_503 = MagicMock(spec=httpx.Response)
        resp_503.status_code = 503
        func = AsyncMock(side_effect=[httpx.TimeoutException("t"), resp_503, "final"])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await policy.execute(func)
        assert result == "final"
        assert func.await_count == 3


class TestExecuteLogging:
    """Logging inside execute — warning, error, debug calls."""

    @pytest.mark.asyncio
    async def test_warning_on_retryable_status_code(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        func = AsyncMock(return_value=resp)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("services.gateway.retry_policy.logger.warning") as mock_warn:
                await policy.execute(func)
        assert any("Retryable status" in str(c) for c in mock_warn.call_args_list)

    @pytest.mark.asyncio
    async def test_warning_on_retryable_exception(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=[httpx.TimeoutException("t"), "ok"])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("services.gateway.retry_policy.logger.warning") as mock_warn:
                await policy.execute(func)
        assert any("Retryable error" in str(c) for c in mock_warn.call_args_list)

    @pytest.mark.asyncio
    async def test_error_on_all_attempts_failed(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=httpx.TimeoutException("fail"))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("services.gateway.retry_policy.logger.error") as mock_err:
                with pytest.raises(httpx.TimeoutException):
                    await policy.execute(func)
        assert any("All 2 attempts failed" in str(c) for c in mock_err.call_args_list)

    @pytest.mark.asyncio
    async def test_debug_on_non_retryable_exception(self) -> None:
        cfg = RetryConfig(max_attempts=2, retry_on_exceptions=(KeyError,))
        policy = RetryPolicy(cfg)
        func = AsyncMock(side_effect=ValueError("no"))
        with patch("services.gateway.retry_policy.logger.debug") as mock_debug:
            with pytest.raises(ValueError):
                await policy.execute(func)
        assert any("Non-retryable exception" in str(c) for c in mock_debug.call_args_list)


class TestRetryWithPolicyDecorator:
    """retry_with_policy decorator with and without circuit breaker."""

    @pytest.mark.asyncio
    async def test_without_circuit_breaker(self) -> None:
        @retry_with_policy(config=RetryConfig(max_attempts=2, base_delay=0.01, jitter=False))
        async def target() -> str:
            return "ok"

        assert await target() == "ok"

    @pytest.mark.asyncio
    async def test_with_circuit_breaker_success(self) -> None:
        cb = GatewayCircuitBreaker("dec_cb", CircuitBreakerConfig(failure_threshold=10))

        @retry_with_policy(config=RetryConfig(max_attempts=2, base_delay=0.01, jitter=False), circuit_breaker=cb)
        async def target() -> str:
            return "ok"

        assert await target() == "ok"

    @pytest.mark.asyncio
    async def test_with_circuit_breaker_retries_on_failure(self) -> None:
        cb = GatewayCircuitBreaker("dec_retry", CircuitBreakerConfig(failure_threshold=10))
        call_count = 0

        @retry_with_policy(config=RetryConfig(max_attempts=3, base_delay=0.01, jitter=False), circuit_breaker=cb)
        async def target() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("timeout")
            return "recovered"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await target()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_raises_circuit_open_error(self) -> None:
        cb = GatewayCircuitBreaker("dec_open", CircuitBreakerConfig(failure_threshold=1))

        @retry_with_policy(config=RetryConfig(max_attempts=2, base_delay=0.01, jitter=False), circuit_breaker=cb)
        async def target() -> str:
            raise httpx.TimeoutException("fail")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.TimeoutException):
                await target()

        with pytest.raises(CircuitOpenError):
            await target()

    @pytest.mark.asyncio
    async def test_decorator_with_default_config(self) -> None:
        @retry_with_policy()
        async def target() -> str:
            return "default"

        assert await target() == "default"

    @pytest.mark.asyncio
    async def test_decorator_passes_args_and_kwargs(self) -> None:
        @retry_with_policy(config=RetryConfig(max_attempts=2, base_delay=0.01, jitter=False))
        async def target(a: int, b: str) -> str:
            return f"{a}:{b}"

        result = await target(42, "hello")
        assert result == "42:hello"

    @pytest.mark.asyncio
    async def test_decorator_with_exception_and_no_circuit_breaker(self) -> None:
        call_count = 0

        @retry_with_policy(config=RetryConfig(max_attempts=3, base_delay=0.01, jitter=False))
        async def target() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("t")
            return "ok"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await target()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_decorator_exhausts_retries(self) -> None:
        @retry_with_policy(config=RetryConfig(max_attempts=2, base_delay=0.01, jitter=False))
        async def target() -> str:
            raise httpx.TimeoutException("always")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.TimeoutException):
                await target()

    @pytest.mark.asyncio
    async def test_decorator_circuit_breaker_retry_count(self) -> None:
        cb = GatewayCircuitBreaker("dec_count", CircuitBreakerConfig(failure_threshold=10))
        call_count = 0

        @retry_with_policy(config=RetryConfig(max_attempts=4, base_delay=0.01, jitter=False), circuit_breaker=cb)
        async def target() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise httpx.TimeoutException("t")
            return "done"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await target()
        assert result == "done"
        assert call_count == 4


class TestExecuteArgsPassthrough:
    """Verify *args and **kwargs are forwarded correctly."""

    @pytest.mark.asyncio
    async def test_args_passed_to_func(self) -> None:
        policy = RetryPolicy()
        func = AsyncMock(return_value="ok")
        await policy.execute(func, 1, 2, 3)
        func.assert_awaited_once_with(1, 2, 3)

    @pytest.mark.asyncio
    async def test_kwargs_passed_to_func(self) -> None:
        policy = RetryPolicy()
        func = AsyncMock(return_value="ok")
        await policy.execute(func, a=1, b=2)
        func.assert_awaited_once_with(a=1, b=2)

    @pytest.mark.asyncio
    async def test_args_and_kwargs_passed(self) -> None:
        policy = RetryPolicy()
        func = AsyncMock(return_value="ok")
        await policy.execute(func, "x", "y", flag=True)
        func.assert_awaited_once_with("x", "y", flag=True)


class TestCancelledErrorPropagation:
    @pytest.mark.asyncio
    async def test_cancelled_error_does_not_get_retried(self) -> None:
        policy = RetryPolicy(config=RetryConfig(max_attempts=3, base_delay=0.01, jitter=False))
        func = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await policy.execute(func)
        func.assert_awaited_once()
