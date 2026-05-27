"""Tests for FeatureFlags integration in handlers and metrics."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.infrastructure.metrics import kojo_active_users, kojo_orders_total
from tg_bot.tenant.config import FeatureFlags


class TestFeatureFlagsInHandlers:
    @pytest.mark.asyncio
    async def test_lightrag_flag_reads_from_config(self) -> None:
        mock_config = MagicMock()
        mock_config.get = AsyncMock(return_value="true")

        flags = FeatureFlags(config=mock_config)
        result = await flags.is_enabled("lightrag")
        assert result is True

    @pytest.mark.asyncio
    async def test_auto_approve_flag_default_false(self) -> None:
        mock_config = MagicMock()
        mock_config.get = AsyncMock(return_value=None)

        flags = FeatureFlags(config=mock_config)
        result = await flags.is_enabled("auto_approve_orders")
        assert result is False


class TestTenantMetrics:
    def test_orders_total_has_tenant_label(self) -> None:
        assert "tenant_id" in kojo_orders_total._labelnames

    def test_active_users_has_tenant_label(self) -> None:
        assert "tenant_id" in kojo_active_users._labelnames

    def test_orders_total_works_with_tenant_id(self) -> None:
        kojo_orders_total.labels(status="created", tenant_id="test_bot").inc()
        # No Exception Means Label Assignment Succeeded
        assert True

    def test_active_users_works_with_tenant_id(self) -> None:
        kojo_active_users.labels(tenant_id="test_bot").set(1)
        assert True
