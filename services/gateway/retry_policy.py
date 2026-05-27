# Services/gateway/retry_policy.py
"""
Retry Policies for External Service Calls.

Provides configurable retry logic with exponential backoff.
"""
import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar, cast

import httpx

from services.gateway.circuit_breaker import CircuitOpenError, GatewayCircuitBreaker

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True

    # Which Exceptions To Retry On
    retry_on_exceptions: tuple[type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    )

    # Which HTTP Status Codes To Retry On
    retry_on_status_codes: tuple[int, ...] = (500, 502, 503, 504, 429)


class RetryPolicy:
    """
    Retry policy with exponential backoff.

    Usage:
        policy = RetryPolicy(max_attempts=3, base_delay=1.0)
        result = await policy.execute(my_async_function, arg1, arg2)
    """

    def __init__(self, config: Optional[RetryConfig] = None) -> None:
        self.config = config or RetryConfig()

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = min(
            self.config.base_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )

        if self.config.jitter:
            import random
            delay *= (0.5 + random.random())  # 50-150% of calculated delay

        return delay

    def should_retry(self, exception: Exception, status_code: Optional[int] = None) -> bool:
        """Determine if we should retry based on exception/status code."""
        # Never Retry On Circuitopenerror - Fail Fast
        if isinstance(exception, CircuitOpenError):
            return False

        # Check Status Code First
        if status_code and status_code in self.config.retry_on_status_codes:
            return True

        # Then Check Exception Type
        return isinstance(exception, self.config.retry_on_exceptions)

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object
    ) -> T:
        """
        Execute function with retry logic.

        Args:
            func: Async function to execute
            *args, **kwargs: Arguments to pass to function

        Returns:
            Result of function call

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.config.max_attempts):
            try:
                result = await func(*args, **kwargs)

                # Check For Retryable Status Codes On Responses
                if isinstance(result, httpx.Response):
                    if result.status_code in self.config.retry_on_status_codes:
                        logger.warning(
                            f"Retryable status {result.status_code}, "
                            f"attempt {attempt + 1}/{self.config.max_attempts}"
                        )
                        # On Last Attempt, Return The Response Instead Of Retrying
                        if attempt >= self.config.max_attempts - 1:
                            return cast(T, result)
                        # Apply Delay Before Retry
                        delay = self.calculate_delay(attempt)
                        await asyncio.sleep(delay)
                        continue

                return result

            except asyncio.CancelledError:
                raise
            except Exception as e:
                if isinstance(e, CircuitOpenError):
                    raise
                last_exception = e

                if not self.should_retry(e):
                    logger.debug(f"Non-retryable exception: {type(e).__name__}")
                    raise

                if attempt < self.config.max_attempts - 1:
                    delay = self.calculate_delay(attempt)
                    logger.warning(
                        f"Retryable error: {type(e).__name__}:{e}. "
                        f"Retrying in {delay:.2f}s (attempt {attempt + 1}/{self.config.max_attempts})"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.config.max_attempts} attempts failed")

        if last_exception:
            raise last_exception
        raise RuntimeError("Retry policy exhausted with no exception")


def retry_with_policy(
    config: Optional[RetryConfig] = None,
    circuit_breaker: Optional[GatewayCircuitBreaker] = None
) -> Callable[..., Callable[..., Awaitable[T]]]:
    """
    Decorator for adding retry logic to async functions.

    Usage:
        @retry_with_policy(RetryConfig(max_attempts=3))
        async def call_external_api():
            ...
    """
    policy = RetryPolicy(config)

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args: object, **kwargs: object) -> T:
            async def execute_with_breaker() -> T:
                return await policy.execute(func, *args, **kwargs)

            if circuit_breaker:
                async with circuit_breaker:
                    return await execute_with_breaker()
            return await execute_with_breaker()

        return wrapper

    return decorator


__all__ = [
    'RetryPolicy',
    'RetryConfig',
    'retry_with_policy',
]
