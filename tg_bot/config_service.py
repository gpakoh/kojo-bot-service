# Tg_bot/config_service.py
# Hierarchical Config Service With 3 Levels:
# 1. Environmentconfig (read-only: Os.environ/.env At Startup)
# 2. Databaseconfig (runtime Overrides: Bot_settings Table)
# 3. Cachedconfig (in-memory With TTL: Hot Path Reads)

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from cachetools import TTLCache

from tg_bot.bot_services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass
class ConfigSource:
    """Source of a config value with metadata."""
    value: str
    source: str  # "env" | "db" | "cache"
    cached_at: Optional[float] = None


class CachedConfig:
    """Level 3: In-memory cache with TTL."""
    def __init__(self, ttl: float = 60.0, maxsize: int = 1000) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.ttl = ttl

    def get(self, key: str) -> Optional[ConfigSource]:
        return self._cache.get(key)

    def set(self, key: str, value: ConfigSource) -> Any:
        self._cache[key] = value

    def invalidate(self, key: str) -> Any:
        self._cache.pop(key, None)

    def clear(self) -> Any:
        self._cache.clear()

    def invalidate_prefix(self, prefix: str) -> Any:
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
        for k in keys_to_remove:
            self._cache.pop(k, None)


class DatabaseConfig:
    """Level 2: Runtime overrides from bot_settings table."""
    def __init__(self, settings_service: SettingsService) -> None:
        self._settings = settings_service

    async def get(self, key: str) -> Optional[str]:
        return await self._settings.get_setting(key)

    async def set(self, key: str, value: str) -> Any:
        await self._settings.set_setting(key, value)

    async def delete(self, key: str) -> Any:
        await self._settings.delete_setting(key)

    async def load_all(self) -> dict[str, str]:
        return await self._settings.get_all_settings()


class EnvironmentConfig:
    """Level 1: Read-only (os.environ + deploy/.env).
    NOTE: EnvironmentConfig is a config source, NOT secrets source.
    Secrets must use SecretsLoader.
    """
    def __init__(self, env_path: Optional[str] = None) -> None:
        self._env_path = env_path
        self._values: dict[str, str] = {}
        self._load_env_file()

    def _load_env_file(self) -> Any:
        if self._env_path and os.path.exists(self._env_path):
            with open(self._env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        self._values[key.strip()] = value.strip()

    def get(self, key: str) -> Optional[str]:
        return os.environ.get(key) or self._values.get(key)


class HierarchicalConfig:
    """
    Unified hierarchical config with 3 levels:
    - env: os.environ / .env (read-only startup)
    - db: bot_settings (runtime overrides)
    - cache: in-memory (hot path with TTL)
    """
    def __init__(
        self,
        env_config: EnvironmentConfig,
        db_config: Optional[DatabaseConfig] = None,
        cache_ttl: float = 60.0
    ):
        self._env = env_config
        self._db = db_config
        self._cache = CachedConfig(ttl=cache_ttl)
        self._cache_warm: bool = False

    async def warm_cache(self) -> Any:
        """Pre-load all DB configs into memory cache."""
        if not self._db:
            return
        all_settings = await self._db.load_all()
        for key, value in all_settings.items():
            self._cache.set(key, ConfigSource(value=value, source="db", cached_at=time.monotonic()))
        self._cache_warm = True
        logger.info(f"[Config] Cache warmed with {len(all_settings)} values")

    def _get_cached(self, key: str) -> Optional[ConfigSource]:
        """Check level 3: cache."""
        cached = self._cache.get(key)
        if cached:
            return cached
        return None

    async def _get_from_db(self, key: str) -> Optional[str]:
        """Check level 2: db runtime overrides."""
        if not self._db:
            return None
        return await self._db.get(key)

    def _get_from_env(self, key: str) -> Optional[str]:
        """Check level 1: environment config."""
        return self._env.get(key)

    async def get(self, key: str, default: Optional[str] = None) -> str:
        """
        Unified get: cache → db → env → default.
        Returns value and source via ConfigSource.
        """
        cached = self._get_cached(key)
        if cached:
            return cached.value

        db_value = await self._get_from_db(key)
        if db_value is not None:
            self._cache.set(key, ConfigSource(value=db_value, source="db", cached_at=time.monotonic()))
            return db_value

        env_value = self._get_from_env(key)
        if env_value is not None:
            self._cache.set(key, ConfigSource(value=env_value, source="env", cached_at=time.monotonic()))
            return env_value

        return default if default is not None else ""

    async def set(self, key: str, value: str) -> Any:
        """Set runtime override in DB (level 2)."""
        if self._db:
            await self._db.set(key, value)
        self._cache.set(key, ConfigSource(value=value, source="db", cached_at=time.monotonic()))

    async def delete(self, key: str) -> Any:
        """Delete from DB (level 2)."""
        if self._db:
            await self._db.delete(key)
        self._cache.invalidate(key)

    def invalidate(self, key: str) -> Any:
        """Invalidate cache for a key."""
        self._cache.invalidate(key)

    def invalidate_prefix(self, prefix: str) -> Any:
        """Invalidate all cache keys starting with prefix."""
        self._cache.invalidate_prefix(prefix)

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {"size": len(self._cache._cache), "warmed": self._cache_warm}


async def create_hierarchical_config(
    settings_service: Optional[SettingsService] = None,
    env_path: Optional[str] = None,
    cache_ttl: float = 60.0
) -> HierarchicalConfig:
    """Factory: create and warm config hierarchy."""
    env = EnvironmentConfig(env_path)
    db = DatabaseConfig(settings_service) if settings_service else None

    config = HierarchicalConfig(env_config=env, db_config=db, cache_ttl=cache_ttl)

    if db:
        await config.warm_cache()

    return config


# Singleton Instance — Import This In Main.py After Services Are Initialized
app_config: Optional[HierarchicalConfig] = None
