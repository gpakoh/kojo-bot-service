"""
Prometheus metrics registry and helpers.
"""
import time
from functools import wraps
from typing import Any, Callable, TypeVar

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Summary

REGISTRY = CollectorRegistry()

# §6.2 Metrics From Manifest
kojo_orders_total = Counter(
    "kojo_orders_total",
    "Total orders by status",
    ["status", "tenant_id"],
    registry=REGISTRY,
)

kojo_order_value_sum = Histogram(
    "kojo_order_value_sum",
    "Order total amount distribution",
    buckets=[100, 250, 500, 1000, 2500, 5000, 10000],
    registry=REGISTRY,
)

kojo_llm_latency_seconds = Histogram(
    "kojo_llm_latency_seconds",
    "LLM/Gateway request latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)

kojo_proxy_failover_count = Counter(
    "kojo_proxy_failover_count",
    "Proxy failover events",
    ["bot_id"],
    registry=REGISTRY,
)

kojo_db_query_duration_seconds = Summary(
    "kojo_db_query_duration_seconds",
    "DB query execution time",
    registry=REGISTRY,
)

kojo_active_users = Gauge(
    "kojo_active_users",
    "Currently active users in bot",
    ["tenant_id"],
    registry=REGISTRY,
)


F = TypeVar("F", bound=Callable[..., Any])


def observe_latency(metric: Histogram) -> Callable[[F], F]:
    """Decorator to observe function execution time.

    Exports to Prometheus with metric name (e.g., kojo_llm_latency_seconds).
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                metric.observe(time.perf_counter() - start)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                metric.observe(time.perf_counter() - start)

        # Return Appropriate Wrapper Based On Function Type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]
    return decorator
