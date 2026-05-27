# Services/gateway/__init__.py
"""
API Gateway / BFF Client for external services (Quart, LLM, etc.)

Provides:
- Typed client with generated client pattern
- Circuit breaker for resilience
- Retry policies with exponential backoff
- Request/response logging
"""
from typing import Any, Optional

from .circuit_breaker import GatewayCircuitBreaker, get_circuit_breaker
from .client import GatewayClient, get_gateway_client
from .retry_policy import RetryPolicy, retry_with_policy

__all__ = [
    'GatewayClient',
    'get_gateway_client',
    'GatewayCircuitBreaker',
    'get_circuit_breaker',
    'RetryPolicy',
    'retry_with_policy',
]
