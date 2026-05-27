# Tg_bot/infrastructure/cache.py
"""
Cache Infrastructure Layer.

Unified cache service with Redis backend and in-memory fallback.
Includes circuit breaker for resilience.
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, cast

import redis.asyncio as redis

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "3600"))
CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "5"))
CIRCUIT_RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_RECOVERY_TIMEOUT", "30"))


class CacheError(Exception):
    """Base exception for cache errors."""
    pass


class CacheUnavailableError(CacheError):
    """Raised when cache is unavailable (Redis down, circuit open)."""
    pass


@dataclass
class CircuitBreakerState:
    """Circuit breaker state."""
    failures: int = 0
    last_failure_time: float = 0
    is_open: bool = False


class CircuitBreaker:
    """
    Circuit breaker for Redis connections.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if connection is restored
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout: int = CIRCUIT_RECOVERY_TIMEOUT
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitBreakerState()
        self._lock = asyncio.Lock()

    @property
    def is_closed(self) -> bool:
        return not self._state.is_open

    @property
    def is_open(self) -> bool:
        if not self._state.is_open:
            return False
        # Check If We Should Try Half-open
        if time.time() - self._state.last_failure_time > self.recovery_timeout:
            return False
        return True

    async def record_success(self) -> None:
        """Record successful operation."""
        async with self._lock:
            self._state.failures = 0
            self._state.is_open = False

    async def record_failure(self) -> None:
        """Record failed operation."""
        async with self._lock:
            self._state.failures += 1
            self._state.last_failure_time = time.time()

            if self._state.failures >= self.failure_threshold:
                self._state.is_open = True
                logger.warning(
                    f"Circuit breaker OPEN after {self._state.failures} failures"
                )


class Cache:
    """
    Unified cache service with Redis backend and in-memory fallback.

    Features:
    - Redis as primary storage
    - In-memory fallback when Redis unavailable
    - Circuit breaker for resilience
    - TTL support
    - Pub/Sub for cache invalidation across pods
    """

    _instance: Optional['Cache'] = None

    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        ttl: int = DEFAULT_TTL,
        enable_config_mode: bool = False
    ):
        self.redis_url = redis_url
        self.ttl = ttl
        self._redis: Optional[redis.Redis] = None
        self._local_cache: Dict[str, tuple[float, Any]] = {}  # key -> (timestamp, value)
        self._circuit = CircuitBreaker()
        self._lock = asyncio.Lock()
        self._enable_config_mode = enable_config_mode
        self._pubsub_task: Optional[asyncio.Task[None]] = None
        self._running = False

    @classmethod
    def get_instance(cls, redis_url: str = DEFAULT_REDIS_URL) -> 'Cache':
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls(redis_url)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        if cls._instance and cls._instance._redis:
            asyncio.create_task(cls._instance._redis.aclose())  # type: ignore[attr-defined]
        cls._instance = None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test Connection
            try:
                await self._redis.ping()  # type: ignore[misc]
                logger.info("Cache: Redis Connection Established")
            except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
                logger.warning(f"Cache: Redis unavailable, using in-memory fallback: {e}")
                await self._redis.aclose()  # type: ignore[union-attr, attr-defined]
                self._redis = None

        if self._enable_config_mode and self._redis:
            self._running = True
            self._pubsub_task = asyncio.create_task(self._listen_for_invalidations())

    async def _listen_for_invalidations(self) -> None:
        """Background task for config invalidation via Pub/Sub."""
        while self._running and self._redis:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe("cache:invalidate")

                async for message in pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] != "message":
                        continue

                    try:
                        data = json.loads(message["data"])
                        key = data.get("key")
                        if key == "*":
                            self._local_cache.clear()
                            logger.debug("Cache: Full Invalidation")
                        elif key:
                            self._local_cache.pop(key, None)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"[databases/kojo/tg_bot/infrastructure/cache.py] JSON/KeyError: {e}")

            except asyncio.CancelledError:
                break
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Cache invalidation listener error: {e}")
                await asyncio.sleep(1)

    async def close(self) -> None:
        """Close connections."""
        self._running = False
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                logger.debug("[databases/kojo/tg_bot/infrastructure/cache.py] Cancellederror (expected)")
        if self._redis:
            await self._redis.aclose()  # type: ignore[attr-defined]
            self._redis = None

    def _local_get(self, key: str) -> Optional[Any]:
        """Get from local cache with TTL check."""
        if key in self._local_cache:
            ts, val = self._local_cache[key]
            if time.time() - ts < self.ttl:
                return val
            del self._local_cache[key]
        return None

    def _local_set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set in local cache."""
        self._local_cache[key] = (time.time(), value)

    def _local_delete(self, key: str) -> None:
        """Delete from local cache."""
        self._local_cache.pop(key, None)

    # Backward Compatibility For Internal Methods
    def _cache_get(self, key: str) -> Optional[Any]:
        """Backward compat: _cache_get - uses instance ttl"""
        return self._local_get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        """Backward compat: _cache_set - uses instance ttl"""
        self._local_set(key, value)

    def _cache_invalidate(self, key: str) -> None:
        """Backward compat: _cache_invalidate"""
        self._local_delete(key)

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache.
        Falls back to local cache if Redis unavailable.
        """
        # Try Local First (fastest)
        local_val = self._local_get(key)
        if local_val is not None:
            return local_val

        # Try Redis If Circuit Is Closed
        if self._redis and self._circuit.is_closed:
            try:
                val = await self._redis.get(key)
                await self._circuit.record_success()

                if val is not None:
                    try:
                        result = json.loads(val)
                        # Store In Local For Next Time
                        self._local_set(key, result, self.ttl)
                        return result
                    except json.JSONDecodeError:
                        return val
                return default
            except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
                await self._circuit.record_failure()
                logger.warning(f"Cache: Redis error, using fallback: {e}")

        return default

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache.
        Writes to both Redis and local cache.
        """
        ttl = ttl or self.ttl

        # Always Set Locally
        self._local_set(key, value, ttl)

        # Try Redis If Circuit Is Closed
        if self._redis and self._circuit.is_closed:
            try:
                serialized = json.dumps(value, default=str)
                await self._redis.setex(key, ttl, serialized)
                await self._circuit.record_success()

                # Publish Invalidation For Other Pods (always For Config Mode Backward Compat)
                await self._redis.publish("config:invalidate", json.dumps({"key": key}))
                if self._enable_config_mode:
                    await self._redis.publish("cache:invalidate", json.dumps({"key": key}))

                return True
            except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
                await self._circuit.record_failure()
                logger.warning(f"Cache: Redis set error: {e}")

        return True  # Local cache always works

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        self._local_delete(key)

        if self._redis and self._circuit.is_closed:
            try:
                await self._redis.delete(key)
                await self._circuit.record_success()

                if self._enable_config_mode:
                    await self._redis.publish("cache:invalidate", json.dumps({"key": key}))
                    await self._redis.publish("config:invalidate", json.dumps({"key": key}))  # Backward compat

                return True
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()

        return True

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        # Check Local First
        if self._local_get(key) is not None:
            return True

        if self._redis and self._circuit.is_closed:
            try:
                result = await self._redis.exists(key)
                await self._circuit.record_success()
                return bool(result)
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()

        return False

    async def clear(self) -> bool:
        """Clear all cache."""
        self._local_cache.clear()

        if self._redis and self._circuit.is_closed:
            try:
                if self._enable_config_mode:
                    await self._redis.flushdb()
                    await self._redis.publish("cache:invalidate", json.dumps({"key": "*"}))
                await self._circuit.record_success()
                return True
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()

        return True

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        local_size = len(self._local_cache)

        redis_info = {}
        if self._redis and self._circuit.is_closed:
            try:
                info = await self._redis.info("stats")
                redis_info = {
                    "connected": True,
                    "keys": await self._redis.dbsize(),
                    "hits": info.get("keyspace_hits", 0),
                    "misses": info.get("keyspace_misses", 0),
                }
            except (redis.ConnectionError, redis.TimeoutError, OSError):
                redis_info = {"connected": False}
        else:
            redis_info = {"connected": False}

        return {
            "local_cache_size": local_size,
            "redis": redis_info,
            "circuit_open": self._circuit.is_open,
        }

    # === Convenience Methods For Hash Operations (for Config) ===

    async def hget(self, name: str, key: str, default: Any = None) -> Any:
        """Get value from hash."""
        if self._redis and self._circuit.is_closed:
            try:
                val = await self._redis.hget(name, key)  # type: ignore[misc]
                await self._circuit.record_success()
                if val is not None:
                    try:
                        return json.loads(val)
                    except json.JSONDecodeError:
                        return val
                return default
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()

        # Fallback: Check Local For Config Mode
        local_key = f"{name}:{key}"
        return self._local_get(local_key) or default

    async def hset(self, name: str, key: str, value: Any) -> bool:
        """Set value in hash."""
        # Always Set Locally
        local_key = f"{name}:{key}"
        self._local_set(local_key, value, self.ttl)

        if self._redis and self._circuit.is_closed:
            try:
                serialized = json.dumps(value, default=str)
                await self._redis.hset(name, key, serialized)  # type: ignore[misc]
                await self._circuit.record_success()

                # Publish Invalidation For Other Pods (always For Config Backward Compat)
                await self._redis.publish("config:invalidate", json.dumps({"key": key}))
                if self._enable_config_mode:
                    await self._redis.publish("cache:invalidate", json.dumps({"key": key}))

                return True
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()

        return True

    async def hgetall(self, name: str) -> dict[str, Any]:
        """Get all values from hash."""
        if self._redis and self._circuit.is_closed:
            try:
                data = await self._redis.hgetall(name)  # type: ignore[misc]
                await self._circuit.record_success()
                result = {}
                for k, v in data.items():
                    try:
                        result[k] = json.loads(v)
                    except json.JSONDecodeError:
                        result[k] = v
                return result
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()

        return {}

    async def delete_hash(self, name: str) -> bool:
        """Delete entire hash."""
        if self._redis and self._circuit.is_closed:
            try:
                await self._redis.delete(name)
                await self._circuit.record_success()
                return True
            except (ConnectionError, TimeoutError, OSError):
                await self._circuit.record_failure()
        return True

    # === Backward Compatibility Methods ===

    async def read_config_value(self, key: str, default: Any = None) -> Any:
        """Backward compatible: read config value from 'config' hash."""
        # Check Simple Cache First (for Backward Compat With Direct _cache_set)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        # Then Check Hash
        return await self.hget("config", key, default)

    async def write_config_value(self, key: str, value: Any) -> bool:
        """Backward compatible: write config value to 'config' hash."""
        return await self.hset("config", key, value)

    async def read_all_config(self) -> dict[str, Any]:
        """Backward compatible: read all config from 'config' hash."""
        return await self.hgetall("config")

    async def write_all_config(self, data: dict[str, Any]) -> bool:
        """Backward compatible: write all config to 'config' hash."""
        await self.delete_hash("config")
        for key, value in data.items():
            await self.hset("config", key, value)
        return True

    async def invalidate_key(self, key: str) -> None:
        """Backward compatible: invalidate config key."""
        await self.delete(f"config:{key}")

    async def start_listener(self) -> None:
        """Backward compat: Start cache invalidation listener."""
        if self._enable_config_mode:
            return
        self._enable_config_mode = True
        await self.connect()

    @property
    def _cache_ttl(self) -> int:
        """Backward compat: cache TTL property"""
        return self.ttl

    @_cache_ttl.setter
    def _cache_ttl(self, value: int) -> None:
        """Backward compat: set[Any] TTL for tests"""
        self.ttl = value

    def get_local_cache_for_test(self) -> Dict[str, tuple[float, Any]]:
        """Backward compat: expose local cache for tests"""
        return self._local_cache

    def set_local_cache_for_test(self, value: Dict[str, tuple[float, Any]]) -> None:
        """Backward compat: set[Any] local cache for tests"""
        self._local_cache = value


# Backward Compatibility Aliases
RedisConfigManager = Cache
RedisPersistence = Cache


class CacheManager:
    """Lightweight cache facade that wraps a pre-configured Redis instance.

    Used by integration tests that inject a mock Redis directly.
    """

    def __init__(self, redis: Any, default_ttl: int = 300) -> None:
        self._redis = redis
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Any:
        """Get value; returns None on miss."""
        val = await self._redis.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value with optional TTL."""
        serialized = json.dumps(value, default=str)
        await self._redis.set(key, serialized, ex=ttl or self.default_ttl)

    async def delete(self, key: str) -> int:
        """Delete a single key."""
        return cast(int, await self._redis.delete(key))

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern."""
        keys = await self._redis.keys(pattern)
        if not keys:
            return 0
        return cast(int, await self._redis.delete(*keys))

    async def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return cached value or compute + cache via factory."""
        val = await self.get(key)
        if val is not None:
            return val
        val = await factory()
        await self.set(key, val)
        return val


__all__ = [
    'Cache',
    'CacheError',
    'CacheUnavailableError',
    'CircuitBreaker',
    'CacheManager',
    'RedisConfigManager',  # Backward compat
    'RedisPersistence',    # Backward compat
]
