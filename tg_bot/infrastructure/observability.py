# Tg_bot/infrastructure/observability.py
"""
Observability Infrastructure: Metrics, Tracing, and Structured Logging.

Provides:
- Prometheus metrics (counters, histograms, gauges)
- OpenTelemetry distributed tracing
- Structured JSON logging
- Health check endpoints
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional

# === Prometheus Metrics ===
# Lazy Initialization To Avoid Import Errors If Prometheus Not Installed

_metrics_enabled = os.getenv("ENABLE_METRICS", "true").lower() == "true"
_tracing_enabled = os.getenv("ENABLE_TRACING", "true").lower() == "true"

# Define Metric Variables At Module Level
_request_count: Optional[Any] = None
_request_duration: Optional[Any] = None
_db_pool_size: Optional[Any] = None
_db_query_duration: Optional[Any] = None
_orders_total: Optional[Any] = None
_order_value: Optional[Any] = None
_proxy_requests: Optional[Any] = None
_proxy_failover: Optional[Any] = None
_ai_requests: Optional[Any] = None
_ai_latency: Optional[Any] = None
_python_gc_count: Optional[Any] = None
_memory_rss: Optional[Any] = None
_service_info: Optional[Any] = None
_registry: Optional[Any] = None


def _init_metrics() -> None:
    """Initialize Prometheus metrics (lazy)."""
    global _request_count, _request_duration, _db_pool_size, _db_query_duration
    global _orders_total, _order_value, _proxy_requests, _proxy_failover
    global _ai_requests, _ai_latency, _python_gc_count, _memory_rss
    global _service_info, _registry

    if not _metrics_enabled:
        return

    try:
        from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info

        _registry = CollectorRegistry()

        # Request Metrics
        _request_count = Counter(
            'bot_requests_total',
            'Total requests',
            ['handler', 'status', 'tenant'],
            registry=_registry
        )

        _request_duration = Histogram(
            'bot_request_duration_seconds',
            'Request duration',
            ['handler'],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=_registry
        )

        # Database Metrics
        _db_pool_size = Gauge(
            'bot_db_pool_size',
            'Database pool size',
            ['state'],  # min, max, free
            registry=_registry
        )

        _db_query_duration = Histogram(
            'bot_db_query_duration_seconds',
            'Database query duration',
            ['query_type'],
            registry=_registry
        )

        # Order Metrics
        _orders_total = Counter(
            'bot_orders_total',
            'Total orders',
            ['status', 'tenant'],
            registry=_registry
        )

        _order_value = Histogram(
            'bot_order_value',
            'Order value in rubles',
            ['tenant'],
            registry=_registry
        )

        # Proxy Metrics
        _proxy_requests = Counter(
            'bot_proxy_requests_total',
            'Proxy requests',
            ['proxy_name', 'status'],
            registry=_registry
        )

        _proxy_failover = Counter(
            'bot_proxy_failover_total',
            'Proxy failover events',
            ['proxy_name'],
            registry=_registry
        )

        # AI Metrics
        _ai_requests = Counter(
            'bot_ai_requests_total',
            'AI requests',
            ['endpoint', 'status'],
            registry=_registry
        )

        _ai_latency = Histogram(
            'bot_ai_latency_seconds',
            'AI request latency',
            ['endpoint'],
            registry=_registry
        )

        # Runtime Metrics
        _python_gc_count = Gauge(
            'bot_python_gc_count',
            'Python GC counts by generation',
            ['generation'],
            registry=_registry
        )

        _memory_rss = Gauge(
            'bot_memory_rss_bytes',
            'Resident set size memory',
            registry=_registry
        )

        # Service Info
        _service_info = Info(
            'bot_service',
            'Bot service information',
            registry=_registry
        )
        _service_info.info({
            'version': os.getenv('APP_VERSION', 'unknown'),
            'tenant': os.getenv('TENANT_BOT_ID', 'default'),
        })

    except ImportError:
        logging.warning("prometheus_client not installed, metrics disabled")


_init_metrics()


def get_metrics_registry() -> Any:
    """Get the Prometheus registry for /metrics endpoint."""
    global _registry
    return _registry


# === Opentelemetry Tracing ===

_tracer = None


def _init_tracing() -> Any:
    """Initialize OpenTelemetry tracing (lazy)."""
    global _tracer

    if not _tracing_enabled:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Create Resource With Service Info
        resource = Resource.create({
            "service.name": "telegram-bot",
            "service.version": os.getenv('APP_VERSION', 'unknown'),
            "tenant.id": os.getenv('TENANT_BOT_ID', 'default'),
        })

        provider = TracerProvider(resource=resource)

        # Jaeger Exporter (if Configured)
        jaeger_endpoint = os.getenv("JAEGER_ENDPOINT")
        if jaeger_endpoint:
            jaeger_exporter = JaegerExporter(
                agent_host_name=jaeger_endpoint.split(':')[0] if ':' in jaeger_endpoint else jaeger_endpoint,
                agent_port=int(jaeger_endpoint.split(':')[1]) if ':' in jaeger_endpoint else 6831,
            )
            provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(__name__)

        logging.info("✅ OpenTelemetry tracing initialized")

    except ImportError:
        logging.warning("opentelemetry not installed, tracing disabled")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logging.warning(f"Failed to initialize tracing: {e}")

    return _tracer


def get_tracer() -> Any:
    """Get the tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = _init_tracing()
    return _tracer


@asynccontextmanager
async def traced_async(name: str, attributes: Optional[Dict[str, Any]] = None) -> Any:
    """Context manager for async tracing."""
    tracer = get_tracer()

    if tracer is None:
        yield
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span


def traced_sync(name: str, attributes: Optional[Dict[str, Any]] = None) -> Callable[..., Any]:
    """Decorator for sync function tracing."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: object, **kwargs: object) -> Any:
            tracer = get_tracer()
            if tracer is None:
                return func(*args, **kwargs)

            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))
                return func(*args, **kwargs)

        return wrapper

    return decorator


# === Metrics Helpers ===

def record_request(handler: str, status: str, tenant: str = "default") -> None:
    """Record request count."""
    global _request_count
    if _metrics_enabled and _request_count is not None:
        _request_count.labels(
            handler=handler,
            status=status,
            tenant=tenant
        ).inc()


def record_request_duration(handler: str, duration: float) -> None:
    """Record request duration."""
    global _request_duration
    if _metrics_enabled and _request_duration is not None:
        _request_duration.labels(handler=handler).observe(duration)


def record_order_status(status: str, tenant: str = "default") -> None:
    """Record order creation."""
    global _orders_total
    if _metrics_enabled and _orders_total is not None:
        _orders_total.labels(status=status, tenant=tenant).inc()


def record_order_value(value: float, tenant: str = "default") -> None:
    """Record order value."""
    global _order_value
    if _metrics_enabled and _order_value is not None:
        _order_value.labels(tenant=tenant).observe(value)


def record_db_pool_state(state: str, count: int) -> None:
    """Record DB pool state."""
    global _db_pool_size
    if _metrics_enabled and _db_pool_size is not None:
        _db_pool_size.labels(state=state).set(count)


# === Structured Logging ===

class StructuredLogger:
    """
    JSON-structured logger for machine parsing.

    Usage:
        logger = StructuredLogger("my_module")
        logger.info("Request processed", extra={"user_id": 123, "duration_ms": 50})
    """

    def __init__(self, name: str, level: int = logging.INFO) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._tenant = os.getenv('TENANT_BOT_ID', 'default')

    def _log(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> None:
        """Log with structured data."""
        extra = extra or {}

        # Standard Fields
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": logging.getLevelName(level),
            "logger": self._logger.name,
            "message": message,
            "tenant": self._tenant,
            **extra,
        }

        # Add Extra Fields
        if extra:
            log_data["extra"] = extra

        # Log As JSON
        self._logger.log(level, json.dumps(log_data), exc_info=exc_info)

    def debug(self, message: str, **kwargs: object) -> None:
        self._log(logging.DEBUG, message, kwargs)

    def info(self, message: str, **kwargs: object) -> None:
        self._log(logging.INFO, message, kwargs)

    def warning(self, message: str, **kwargs: object) -> None:
        self._log(logging.WARNING, message, kwargs)

    def error(self, message: str, **kwargs: object) -> None:
        self._log(logging.ERROR, message, kwargs)

    def critical(self, message: str, **kwargs: object) -> None:
        self._log(logging.CRITICAL, message, kwargs)


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


# === Health Check ===

@dataclass
class HealthStatus:
    """Health check result."""
    status: str  # "healthy", "degraded", "unhealthy"
    checks: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


async def check_health(db_pool: Optional[Any] = None, redis: Optional[Any] = None) -> HealthStatus:
    """Run health checks on all dependencies."""
    checks = {}
    all_healthy = True

    # Database Check
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["database"] = {"status": "healthy"}
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            checks["database"] = {"status": "unhealthy", "error": str(e)}
            all_healthy = False
    else:
        checks["database"] = {"status": "not_configured"}

    # Redis Check
    if redis:
        try:
            await redis.ping()
            checks["redis"] = {"status": "healthy"}
        except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
            checks["redis"] = {"status": "unhealthy", "error": str(e)}
            all_healthy = False
    else:
        checks["redis"] = {"status": "not_configured"}

    # Metrics Check
    checks["metrics"] = {"status": "healthy" if _metrics_enabled else "disabled"}

    # Tracing Check
    checks["tracing"] = {"status": "healthy" if _tracing_enabled else "disabled"}

    status = "healthy" if all_healthy else "degraded"

    return HealthStatus(status=status, checks=checks)


__all__ = [
    # Metrics
    'get_metrics_registry',
    'record_request',
    'record_request_duration',
    'record_order_status',
    'record_order_value',
    'record_db_pool_state',
    # Tracing
    'get_tracer',
    'traced_async',
    'traced_sync',
    # Logging
    'StructuredLogger',
    'get_structured_logger',
    # Health
    'HealthStatus',
    'check_health',
]
