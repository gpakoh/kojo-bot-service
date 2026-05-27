"""Tests for services/gateway/retry_policy.py coverage gaps."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.gateway.circuit_breaker import CircuitBreakerConfig, GatewayCircuitBreaker
from services.gateway.retry_policy import RetryConfig, RetryPolicy, retry_with_policy


class TestRetryPolicyCoverage:
    """Close gaps in retry_policy.py (48% → target 80%+)."""

    def test_calculate_delay_no_jitter(self) -> None:
        cfg = RetryConfig(jitter=False, base_delay=1.0, exponential_base=2.0)
        policy = RetryPolicy(cfg)
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 4.0

    def test_should_retry_by_status_code(self) -> None:
        cfg = RetryConfig()
        policy = RetryPolicy(cfg)
        assert policy.should_retry(RuntimeError("any"), status_code=500) is True
        assert policy.should_retry(RuntimeError("any"), status_code=200) is False
        assert policy.should_retry(RuntimeError("any"), status_code=429) is True

    @pytest.mark.asyncio
    async def test_execute_retries_on_retryable_status_code(self) -> None:
        """Response with 503 should trigger retry even if no exception."""
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        policy = RetryPolicy(cfg)

        call_count = 0
        async def fake():
            nonlocal call_count
            call_count += 1
            # Return A Response With 503 Status - Should Trigger Retry
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 503
            return resp

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await policy.execute(fake)
        assert result.status_code == 503  # returns last response after retries exhausted
        assert call_count == 2  # 2 attempts

    @pytest.mark.asyncio
    async def test_execute_non_retryable_exception_raises_immediately(self) -> None:
        cfg = RetryConfig(max_attempts=3, retry_on_exceptions=(KeyError,))
        policy = RetryPolicy(cfg)

        async def fail():
            raise KeyError("not retryable")

        with pytest.raises(KeyError):
            await policy.execute(fail)

    @pytest.mark.asyncio
    async def test_retry_with_policy_decorator(self) -> None:
        cfg = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        cb = GatewayCircuitBreaker("dec_test", CircuitBreakerConfig(failure_threshold=10))

        @retry_with_policy(config=cfg, circuit_breaker=cb)
        async def target() -> str:
            return "ok"

        result = await target()
        assert result == "ok"
