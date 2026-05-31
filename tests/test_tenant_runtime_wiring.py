"""Tests for tenant runtime wiring in main.py."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.main import configure_tenant_runtime
from tg_bot.tenant.config import TenantRegistry


class TestConfigureTenantRuntime:
    """configure_tenant_runtime helper — stores registry + fallback bot_id."""

    def teardown_method(self) -> None:
        TenantRegistry._instance = None

    def test_stores_tenant_registry_in_bot_data(self) -> None:
        app = MagicMock()
        app.bot_data = {}

        configure_tenant_runtime(app, bot_id="kojo")

        assert "tenant_registry" in app.bot_data
        assert isinstance(app.bot_data["tenant_registry"], TenantRegistry)

    def test_sets_fallback_tenant_bot_id_from_argument(self) -> None:
        app = MagicMock()
        app.bot_data = {}

        configure_tenant_runtime(app, bot_id="kojo")

        assert app.bot_data["_tenant_bot_id"] == "kojo"

    def test_sets_fallback_tenant_bot_id_from_env(self) -> None:
        app = MagicMock()
        app.bot_data = {}

        with patch.dict("os.environ", {"BOT_ID_FOR_QUART": "lebo"}, clear=True):
            configure_tenant_runtime(app)

        assert app.bot_data["_tenant_bot_id"] == "lebo"

    def test_fallback_default_when_no_bot_id(self) -> None:
        app = MagicMock()
        app.bot_data = {}

        with patch.dict("os.environ", {}, clear=True):
            configure_tenant_runtime(app)

        assert app.bot_data["_tenant_bot_id"] == "default"

    def test_does_not_require_warmup_bot_ids(self) -> None:
        """Single-tenant mode: WARMUP_BOT_IDS not set → empty registry, no crash."""
        app = MagicMock()
        app.bot_data = {}

        with patch.dict("os.environ", {}, clear=True):
            configure_tenant_runtime(app, bot_id="kojo")

        registry = app.bot_data["tenant_registry"]
        assert len(registry.get_all_tenants()) == 0
        assert registry.get_default_tenant() is None

    def test_registry_is_singleton(self) -> None:
        """Multiple calls return the same TenantRegistry singleton."""
        TenantRegistry._instance = None
        app = MagicMock()
        app.bot_data = {}

        configure_tenant_runtime(app, bot_id="kojo")
        first = app.bot_data["tenant_registry"]

        app2 = MagicMock()
        app2.bot_data = {}
        configure_tenant_runtime(app2, bot_id="lebo")
        second = app2.bot_data["tenant_registry"]

        assert first is second

    def test_can_register_tenants_via_env(self) -> None:
        """When WARMUP_BOT_IDS is set, tenants are loaded into the registry."""
        TenantRegistry._instance = None
        app = MagicMock()
        app.bot_data = {}

        with patch(
            "tg_bot.tenant.config.SecretsLoader.get",
            side_effect=lambda key, default="": {
                "WARMUP_BOT_IDS": "bot_a",
                "bot_a_TOKEN": "tok_a",
            }.get(key, default),
        ):
            configure_tenant_runtime(app, bot_id="bot_a")

        registry = app.bot_data["tenant_registry"]
        assert registry.get_tenant("bot_a") is not None
        assert registry.get_tenant("bot_a").bot_token == "tok_a"


class TestTenantMiddlewareWired:
    """Verify that TenantMiddleware is reachable via the middleware chain."""

    def test_tenant_middleware_importable(self) -> Any:
        from tg_bot.tenant.middleware import TenantMiddleware
        assert TenantMiddleware is not None

    @pytest.mark.asyncio
    async def test_tenant_middleware_sets_bot_data(self) -> None:
        """Integration-style: middleware sets _tenant_bot_id in context."""
        from tg_bot.tenant.config import TenantConfig
        from tg_bot.tenant.middleware import TenantMiddleware

        registry = TenantRegistry()
        registry._tenants["test_bot"] = TenantConfig(
            bot_id="test_bot", bot_token="test_token"
        )
        mw = TenantMiddleware(registry=registry)

        mock_update = MagicMock()
        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        mock_context.bot.username = "test_bot"
        mock_context.bot.token = "test_token"
        mock_context.bot_data = {}

        next_handler = AsyncMock(return_value="ok")

        result = await mw(mock_update, mock_context, next_handler)

        assert result == "ok"
        assert mock_context.bot_data["_tenant_bot_id"] == "test_bot"

    @pytest.mark.asyncio
    async def test_tenant_middleware_fallback_to_bot_data(self) -> None:
        """When no token match, falls back to _tenant_bot_id already in bot_data."""
        from tg_bot.tenant.config import TenantConfig
        from tg_bot.tenant.middleware import TenantMiddleware

        registry = TenantRegistry()
        registry._tenants["kojo"] = TenantConfig(
            bot_id="kojo", bot_token="real_token"
        )
        mw = TenantMiddleware(registry=registry)

        mock_update = MagicMock()
        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        mock_context.bot.username = "SomeOtherBot"
        mock_context.bot.token = "no_match"
        mock_context.bot_data = {"_tenant_bot_id": "kojo"}

        next_handler = AsyncMock(return_value="ok")

        result = await mw(mock_update, mock_context, next_handler)
        assert result == "ok"
        assert mock_context.bot_data["_tenant_bot_id"] == "kojo"

    @pytest.mark.asyncio
    async def test_tenant_middleware_resets_context_after_handler(self) -> None:
        """Contextvars are cleaned up in the finally block."""
        from tg_bot.tenant.config import (
            TenantConfig,
            get_current_tenant,
            set_current_tenant,
        )
        from tg_bot.tenant.middleware import TenantMiddleware

        registry = TenantRegistry()
        registry._tenants["test_bot"] = TenantConfig(
            bot_id="test_bot", bot_token="test_token"
        )
        mw = TenantMiddleware(registry=registry)

        mock_update = MagicMock()
        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        mock_context.bot.username = "test_bot"
        mock_context.bot.token = "test_token"
        mock_context.bot_data = {}

        # Set a previous tenant to verify cleanup
        set_current_tenant(TenantConfig(bot_id="previous", bot_token="prev"))
        previous = get_current_tenant()

        next_handler = AsyncMock(return_value="ok")
        await mw(mock_update, mock_context, next_handler)

        # After middleware returns, context should be restored
        restored = get_current_tenant()
        assert restored == previous
