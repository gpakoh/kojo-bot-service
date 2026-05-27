# Tg_bot/tenant/config.py
"""
Multi-tenant Configuration.

Manages tenant (bot) configurations and registry.
"""
import contextvars
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tg_bot.infrastructure.secrets_loader import SecretsLoader

logger = logging.getLogger(__name__)

# === Asyncio-safe Tenant Context (contextvars) ===

_tenant_context: contextvars.ContextVar[Optional['TenantConfig']] = contextvars.ContextVar(
    'current_tenant', default=None
)


def get_current_tenant() -> Optional['TenantConfig']:
    """Get tenant for current async task context (contextvars-safe)."""
    return _tenant_context.get()


def set_current_tenant(tenant: Optional['TenantConfig']) -> None:
    """Set tenant for current async task context."""
    if tenant is None:
        _tenant_context.set(None)
    else:
        _tenant_context.set(tenant)


# === Tenant Config ===

@dataclass
class TenantConfig:
    """Configuration for a single tenant (bot)."""
    bot_id: str
    bot_token: str
    database_url: Optional[str] = None
    quart_url: Optional[str] = None
    integration_url: Optional[str] = None

    # Feature Flags
    features: Dict[str, bool] = field(default_factory=dict)

    # Admin Users
    admin_ids: List[int] = field(default_factory=list)

    @property
    def db_schema(self) -> str:
        """Database schema for this tenant (lowercase, safe for SQL)."""
        return self.bot_id.lower().replace('-', '_').replace(' ', '_')


# === Feature Flags (task 2) ===

class FeatureFlags:
    """Runtime feature flags with TTL cache and hot-reload."""

    def __init__(
        self,
        config: Optional[Any] = None,
        cache_ttl: float = 60.0,
    ) -> None:
        self._config = config
        self._cache: Dict[str, bool] = {}
        self._cache_ttl = cache_ttl
        self._last_update = 0.0

    async def is_enabled(self, flag_name: str, default: bool = False) -> bool:
        """Check if feature flag is enabled (cached with TTL)."""
        now = time.monotonic()

        if flag_name in self._cache and (now - self._last_update) < self._cache_ttl:
            return self._cache[flag_name]

        value = default
        if self._config:
            raw = await self._config.get(f"feature_{flag_name}")
            if raw is not None:
                value = raw.lower() in ("true", "1", "yes", "on")

        self._cache[flag_name] = value
        self._last_update = now
        return value

    def invalidate(self, flag_name: str) -> None:
        """Invalidate cache for a single flag."""
        self._cache.pop(flag_name, None)

    def invalidate_all(self) -> None:
        """Invalidate all cached flags."""
        self._cache.clear()
        self._last_update = 0.0


# === Tenant Registry (task 1) ===

class TenantRegistry:
    """
    Registry of all tenants (bots).

    Loads from SecretsLoader (Vault > Docker > File > Env):
    - WARMUP_BOT_IDS: comma-separated list of bot IDs
    - {BOT_ID}_TOKEN: bot token for each bot
    - {BOT_ID}_DATABASE_URL: optional separate DB
    """

    _instance: Optional['TenantRegistry'] = None

    def __init__(self, config: Optional[Any] = None) -> None:
        self._tenants: Dict[str, TenantConfig] = {}
        self._load_from_config(config)

    @classmethod
    def get_instance(cls) -> 'TenantRegistry':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_from_config(self, config: Optional[Any] = None) -> None:
        """Load tenant configs from SecretsLoader (Vault > Docker > File > Env).

        Args:
            config: Optional HierarchicalConfig for future async pre-load.
                     Currently falls back to SecretsLoader for sync init.
        """
        bot_ids_str = SecretsLoader.get("WARMUP_BOT_IDS", "")
        if not bot_ids_str:
            logger.warning("No WARMUP_BOT_IDS Configured")
            return

        bot_ids = [b.strip() for b in bot_ids_str.split(',') if b.strip()]

        for bot_id in bot_ids:
            token = SecretsLoader.get(f"{bot_id}_TOKEN")
            if not token:
                logger.warning("No token for bot %s", bot_id)
                continue

            cfg = TenantConfig(
                bot_id=bot_id,
                bot_token=token,
                database_url=SecretsLoader.get(f"{bot_id}_DATABASE_URL"),
                quart_url=SecretsLoader.get(f"{bot_id}_QUART_URL"),
                integration_url=SecretsLoader.get(f"{bot_id}_INTEGRATION_URL"),
            )

            admin_ids_str = SecretsLoader.get(f"{bot_id}_ADMIN_IDS", "")
            if admin_ids_str:
                cfg.admin_ids = [
                    int(x.strip()) for x in admin_ids_str.split(',') if x.strip()
                ]

            features_str = SecretsLoader.get(f"{bot_id}_FEATURES", "")
            if features_str:
                for f in features_str.split(','):
                    f = f.strip()
                    if f:
                        cfg.features[f] = True

            self._tenants[bot_id] = cfg
            logger.info("Loaded tenant: %s", bot_id)

    def get_tenant(self, bot_id: str) -> Optional[TenantConfig]:
        """Get tenant config by bot ID."""
        return self._tenants.get(bot_id)

    def get_all_tenants(self) -> Dict[str, TenantConfig]:
        """Get all configured tenants."""
        return self._tenants.copy()

    def get_default_tenant(self) -> Optional[TenantConfig]:
        """Get default tenant (first one configured)."""
        if self._tenants:
            return next(iter(self._tenants.values()))
        return None

    def is_valid_tenant(self, bot_id: str) -> bool:
        """Check if bot_id is a valid tenant."""
        return bot_id in self._tenants


def get_tenant_registry() -> TenantRegistry:
    """Get the singleton tenant registry."""
    return TenantRegistry.get_instance()


__all__ = [
    'TenantConfig',
    'TenantRegistry',
    'FeatureFlags',
    'get_tenant_registry',
    'get_current_tenant',
    'set_current_tenant',
]
