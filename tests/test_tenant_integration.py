"""Integration tests for multi-tenancy (Phase 7)."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.infrastructure.database import DatabaseManager
from tg_bot.tenant.config import (
    FeatureFlags,
    TenantConfig,
    TenantRegistry,
    get_current_tenant,
    set_current_tenant,
)
from tg_bot.tenant.middleware import TenantMiddleware


def _mock_pool(conn: AsyncMock) -> MagicMock:
    """Create a mock asyncpg pool that yields the given connection."""
    mock_pool = MagicMock()

    @asynccontextmanager
    async def acquire(*args: object, **kwargs: object):
        yield conn

    mock_pool.acquire = acquire
    return mock_pool


# === Fixtures ===

@pytest.fixture
def tenant1() -> TenantConfig:
    return TenantConfig(bot_id="bot_alpha", bot_token="token_alpha")


@pytest.fixture
def tenant2() -> TenantConfig:
    return TenantConfig(bot_id="bot_beta", bot_token="token_beta")


# === Task 3: Contextvars Isolation ===

class TestTenantContext:
    def test_contextvars_isolation(self, tenant1: TenantConfig, tenant2: TenantConfig) -> None:
        set_current_tenant(tenant1)
        assert get_current_tenant() == tenant1

        set_current_tenant(tenant2)
        assert get_current_tenant() == tenant2

    def test_get_current_tenant_default_none(self) -> None:
        set_current_tenant(None)
        assert get_current_tenant() is None

    def test_set_current_tenant_none(self) -> None:
        set_current_tenant(None)
        assert get_current_tenant() is None


# === Task 2: Feature Flags ===

class TestFeatureFlags:
    @pytest.mark.asyncio
    async def test_is_enabled_reads_from_config(self) -> None:
        mock_config = MagicMock()
        mock_config.get = AsyncMock(return_value="true")

        flags = FeatureFlags(config=mock_config)
        result = await flags.is_enabled("lightrag")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_enabled_default_false(self) -> None:
        mock_config = MagicMock()
        mock_config.get = AsyncMock(return_value=None)

        flags = FeatureFlags(config=mock_config)
        result = await flags.is_enabled("unknown_flag")
        assert result is False

    def test_cache_invalidation(self) -> None:
        flags = FeatureFlags()
        flags._cache["test"] = True
        flags.invalidate("test")
        assert "test" not in flags._cache

    def test_invalidate_all(self) -> None:
        flags = FeatureFlags()
        flags._cache["a"] = True
        flags._cache["b"] = False
        flags.invalidate_all()
        assert flags._cache == {}

    @pytest.mark.asyncio
    async def test_cache_hit_within_ttl(self) -> None:
        mock_config = MagicMock()
        mock_config.get = AsyncMock(return_value="true")

        flags = FeatureFlags(config=mock_config, cache_ttl=60.0)
        await flags.is_enabled("cached_flag")

        # Second Call Should Hit Cache, Not Call Config.get
        mock_config.get.reset_mock()
        result = await flags.is_enabled("cached_flag")
        assert result is True
        mock_config.get.assert_not_called()


# === Task 1: Tenantregistry ===

class TestTenantRegistry:
    def test_registry_empty_when_no_env(self) -> None:
        with patch.dict('os.environ', {}, clear=True):
            registry = TenantRegistry()
            assert len(registry.get_all_tenants()) == 0

    def test_registry_loads_from_secrets_loader(self) -> None:
        with patch(
            "tg_bot.tenant.config.SecretsLoader.get",
            side_effect=lambda key, default="": {
                "WARMUP_BOT_IDS": "bot_a",
                "bot_a_TOKEN": "tok_a",
                "bot_a_DATABASE_URL": "postgres://a",
                "bot_a_ADMIN_IDS": "111,222",
                "bot_a_FEATURES": "lightrag,beta",
            }.get(key, default),
        ):
            registry = TenantRegistry()
            tenant = registry.get_tenant("bot_a")
            assert tenant is not None
            assert tenant.bot_token == "tok_a"
            assert tenant.database_url == "postgres://a"
            assert tenant.admin_ids == [111, 222]
            assert tenant.features == {"lightrag": True, "beta": True}

    def test_get_default_tenant_returns_first(self) -> None:
        with patch(
            "tg_bot.tenant.config.SecretsLoader.get",
            side_effect=lambda key, default="": {
                "WARMUP_BOT_IDS": "bot_a,bot_b",
                "bot_a_TOKEN": "tok_a",
                "bot_b_TOKEN": "tok_b",
            }.get(key, default),
        ):
            registry = TenantRegistry()
            default = registry.get_default_tenant()
            assert default is not None
            assert default.bot_id == "bot_a"


# === Task 3: Tenant Middleware ===

class TestTenantMiddleware:
    @pytest.mark.asyncio
    async def test_extracts_tenant_from_context(self, tenant1: TenantConfig) -> None:
        mw = TenantMiddleware()

        mock_update = MagicMock()
        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        mock_context.bot.username = "bot_alpha"
        mock_context.bot.token = "token_alpha"
        mock_context.bot_data = {}

        next_handler = AsyncMock(return_value="ok")

        with patch.object(mw.registry, 'get_all_tenants', return_value={"bot_alpha": tenant1}):
            with patch.object(mw.registry, 'get_default_tenant', return_value=tenant1):
                result = await mw(mock_update, mock_context, next_handler)

        assert result == "ok"
        assert mock_context.bot_data.get('_tenant_bot_id') == "bot_alpha"


# === Task 4: RLS In Databasemanager ===

class TestDatabaseManagerRls:
    @pytest.mark.asyncio
    async def test_set_tenant_context(self) -> None:
        mock_conn = AsyncMock()
        db = DatabaseManager(pool=_mock_pool(mock_conn))
        await db.set_tenant_context("bot_kojo")

        mock_conn.execute.assert_called_once_with(
            "SELECT set_tenant_context($1)", "bot_kojo"
        )

    @pytest.mark.asyncio
    async def test_tenant_connection_sets_context(self) -> None:
        mock_conn = AsyncMock()
        db = DatabaseManager(pool=_mock_pool(mock_conn))
        async with db.tenant_connection("bot_kojo"):
            pass

        mock_conn.execute.assert_called_once_with(
            "SELECT set_tenant_context($1)", "bot_kojo"
        )

    @pytest.mark.asyncio
    async def test_tenant_connection_without_tenant_skips_rls(self) -> None:
        mock_conn = AsyncMock()
        db = DatabaseManager(pool=_mock_pool(mock_conn))
        async with db.tenant_connection():
            pass

        mock_conn.execute.assert_not_called()
