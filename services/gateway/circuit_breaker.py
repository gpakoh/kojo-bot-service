# Services/gateway/circuit_breaker.py
"""
Circuit Breaker Implementation for External Service Calls.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests fail fast
- HALF_OPEN: Testing if service is restored
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from services.gateway.exceptions import GatewayTransientError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0
    excluded_exceptions: tuple[type[BaseException], ...] = ()


@dataclass
class CircuitMetrics:
    """Metrics for circuit breaker."""
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0
    state: CircuitState = CircuitState.CLOSED


class GatewayCircuitBreaker:
    """
    Circuit breaker for external service calls.

    Usage:
        breaker = GatewayCircuitBreaker("quart")

        try:
            async with breaker:
                return await call_external_service()
        except CircuitOpenError:
            return fallback_value
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._metrics = CircuitMetrics()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._metrics.state == CircuitState.OPEN:
            # Check If Timeout Has Elapsed To Transition To Half-open
            if time.time() - self._metrics.last_failure_time >= self.config.timeout:
                return CircuitState.HALF_OPEN
        return self._metrics.state

    @property
    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self._metrics.failures = 0

            if self.state == CircuitState.HALF_OPEN:
                self._metrics.successes += 1
                if self._metrics.successes >= self.config.success_threshold:
                    self._metrics.state = CircuitState.CLOSED
                    logger.info(f"✅ Circuit '{self.name}' CLOSED (recovered)")

    async def record_failure(self, exception: BaseException | None) -> None:
        """Record a failed call."""
        # Skip Excluded Exceptions (transient Errors Like 4xx)
        if isinstance(exception, self.config.excluded_exceptions):
            return

        # Skip Gatewaytransienterror (4xx Client Errors, Not Server Failures)
        if isinstance(exception, GatewayTransientError):
            logger.debug("Transient error excluded from circuit breaker: %s", exception)
            return

        async with self._lock:
            self._metrics.failures += 1
            self._metrics.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self._metrics.state = CircuitState.OPEN
                logger.warning(f"❌ Circuit '{self.name}' OPEN (half-open failed)")
            elif self._metrics.failures >= self.config.failure_threshold:
                self._metrics.state = CircuitState.OPEN
                logger.warning(f"❌ Circuit '{self.name}' OPEN after {self._metrics.failures} failures")

    async def __aenter__(self) -> "GatewayCircuitBreaker":
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit '{self.name}' is OPEN")
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object | None) -> bool:  # noqa: E501
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure(exc_val)
        return False  # Don't suppress exceptions


class CircuitOpenError(Exception):
    """Raised when circuit is open and no fallback is provided."""
    pass


# Global Circuit Breakers Registry With TTL
_circuit_breakers: dict[str, GatewayCircuitBreaker] = {}
_circuit_timestamps: dict[str, datetime] = {}
_CIRCUIT_TTL_SECONDS = 3600


def _cleanup_stale_circuits() -> None:
    """Remove circuit breakers not accessed for >1 hour."""
    now = datetime.now(timezone.utc)
    stale = [
        name for name, ts in _circuit_timestamps.items()
        if (now - ts).total_seconds() > _CIRCUIT_TTL_SECONDS
    ]
    for name in stale:
        _circuit_breakers.pop(name, None)
        _circuit_timestamps.pop(name, None)
        logger.info(f"🧹 [CircuitBreaker] Cleaned up stale: {name}")


def get_circuit_breaker(
    name: str, config: Optional[CircuitBreakerConfig] = None
) -> GatewayCircuitBreaker:
    """Get or create a circuit breaker by name.

    Args:
        name: Unique name for the circuit breaker
        config: Optional config with failure_threshold, timeout, excluded_exceptions
    """
    _cleanup_stale_circuits()
    if name not in _circuit_breakers:
        _circuit_breakers[name] = GatewayCircuitBreaker(name, config)
    _circuit_timestamps[name] = datetime.now(timezone.utc)
    return _circuit_breakers[name]


def clear_circuit_breakers() -> None:
    """Clear all circuit breakers (for testing)."""
    _circuit_breakers.clear()


__all__ = [
    'GatewayCircuitBreaker',
    'CircuitBreakerConfig',
    'CircuitMetrics',
    'CircuitState',
    'CircuitOpenError',
    'get_circuit_breaker',
    'clear_circuit_breakers',
]
