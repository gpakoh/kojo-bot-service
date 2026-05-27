"""Tests for tenant migration management."""
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.tenant.config import TenantConfig
from tg_bot.tenant.migrations import TenantMigrationManager, get_migration_manager


@pytest.fixture
def tenant() -> TenantConfig:
    return TenantConfig(bot_id="test_bot", bot_token="test_token")


@pytest.fixture
def manager() -> TenantMigrationManager:
    return TenantMigrationManager(alembic_dir="/fake/alembic")


class TestInit:
    def test_default_alembic_dir(self) -> None:
        with patch.dict('os.environ', {}, clear=True):
            mgr = TenantMigrationManager()
        assert mgr.alembic_dir == "alembic"

    def test_custom_alembic_dir(self) -> None:
        mgr = TenantMigrationManager(alembic_dir="/custom/path")
        assert mgr.alembic_dir == "/custom/path"

    def test_from_env_variable(self) -> None:
        with patch.dict('os.environ', {"ALEMBIC_DIR": "/env/path"}, clear=True):
            mgr = TenantMigrationManager()
        assert mgr.alembic_dir == "/env/path"

    def test_explicit_overrides_env(self) -> None:
        with patch.dict('os.environ', {"ALEMBIC_DIR": "/env/path"}, clear=True):
            mgr = TenantMigrationManager(alembic_dir="/explicit")
        assert mgr.alembic_dir == "/explicit"


class TestGetTenantsToMigrate:
    def test_all_tenants_when_no_target_env(self, manager: TenantMigrationManager) -> None:
        mock_registry = MagicMock()
        t1 = TenantConfig(bot_id="a", bot_token="t1")
        t2 = TenantConfig(bot_id="b", bot_token="t2")
        mock_registry.get_all_tenants.return_value = {"a": t1, "b": t2}
        with patch('tg_bot.tenant.migrations.get_tenant_registry', return_value=mock_registry):
            with patch.dict('os.environ', {}, clear=True):
                result = manager.get_tenants_to_migrate()
        assert result == [t1, t2]

    def test_specific_tenant(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_registry = MagicMock()
        mock_registry.get_tenant.return_value = tenant
        with patch('tg_bot.tenant.migrations.get_tenant_registry', return_value=mock_registry):
            with patch.dict('os.environ', {"TENANT_TO_MIGRATE": "test_bot"}):
                result = manager.get_tenants_to_migrate()
        assert result == [tenant]
        mock_registry.get_tenant.assert_called_once_with("test_bot")

    def test_unknown_tenant_returns_empty(self, manager: TenantMigrationManager) -> None:
        mock_registry = MagicMock()
        mock_registry.get_tenant.return_value = None
        with patch('tg_bot.tenant.migrations.get_tenant_registry', return_value=mock_registry):
            with patch.dict('os.environ', {"TENANT_TO_MIGRATE": "nonexistent"}):
                result = manager.get_tenants_to_migrate()
        assert result == []

    def test_no_tenants_configured(self, manager: TenantMigrationManager) -> None:
        mock_registry = MagicMock()
        mock_registry.get_all_tenants.return_value = {}
        with patch('tg_bot.tenant.migrations.get_tenant_registry', return_value=mock_registry):
            result = manager.get_tenants_to_migrate()
        assert result == []


class TestMigrateTenant:
    @pytest.mark.asyncio
    async def test_success(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result):
            result = await manager.migrate_tenant(tenant, verbose=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_success_non_verbose(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="details", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result):
            result = await manager.migrate_tenant(tenant, verbose=False)
        assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="error msg")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result):
            result = await manager.migrate_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        with patch('tg_bot.tenant.migrations.subprocess.run',
                   side_effect=subprocess.TimeoutExpired(cmd="test", timeout=120)):
            result = await manager.migrate_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_general_exception(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        with patch('tg_bot.tenant.migrations.subprocess.run',
                   side_effect=Exception("boom")):
            result = await manager.migrate_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_env_variables_passed(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result) as mock_run:
            await manager.migrate_tenant(tenant)
        _, kwargs = mock_run.call_args
        assert kwargs['env']["TENANT_SCHEMA"] == tenant.db_schema
        assert kwargs['env']["TENANT_BOT_ID"] == tenant.bot_id

    @pytest.mark.asyncio
    async def test_custom_revision(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result) as mock_run:
            await manager.migrate_tenant(tenant, revision="abc123")
        cmd = mock_run.call_args[0][0]
        assert "abc123" in cmd


class TestMigrateAllTenants:
    @pytest.mark.asyncio
    async def test_all_successful(self, manager: TenantMigrationManager) -> None:
        t1 = TenantConfig(bot_id="a", bot_token="ta")
        t2 = TenantConfig(bot_id="b", bot_token="tb")
        manager.get_tenants_to_migrate = MagicMock(return_value=[t1, t2])
        manager.migrate_tenant = AsyncMock(return_value=True)
        results = await manager.migrate_all_tenants()
        assert results == {"a": True, "b": True}

    @pytest.mark.asyncio
    async def test_with_failures(self, manager: TenantMigrationManager) -> None:
        t1 = TenantConfig(bot_id="a", bot_token="ta")
        t2 = TenantConfig(bot_id="b", bot_token="tb")
        manager.get_tenants_to_migrate = MagicMock(return_value=[t1, t2])
        manager.migrate_tenant = AsyncMock(side_effect=[True, False])
        results = await manager.migrate_all_tenants()
        assert results == {"a": True, "b": False}

    @pytest.mark.asyncio
    async def test_fail_fast_stops_early(self, manager: TenantMigrationManager) -> None:
        t1 = TenantConfig(bot_id="a", bot_token="ta")
        t2 = TenantConfig(bot_id="b", bot_token="tb")
        t3 = TenantConfig(bot_id="c", bot_token="tc")
        manager.get_tenants_to_migrate = MagicMock(return_value=[t1, t2, t3])
        manager.migrate_tenant = AsyncMock(side_effect=[True, False, True])
        results = await manager.migrate_all_tenants(fail_fast=True)
        assert results == {"a": True, "b": False}
        assert manager.migrate_tenant.call_count == 2

    @pytest.mark.asyncio
    async def test_fail_fast_all_succeed(self, manager: TenantMigrationManager) -> None:
        t1 = TenantConfig(bot_id="a", bot_token="ta")
        t2 = TenantConfig(bot_id="b", bot_token="tb")
        manager.get_tenants_to_migrate = MagicMock(return_value=[t1, t2])
        manager.migrate_tenant = AsyncMock(return_value=True)
        results = await manager.migrate_all_tenants(fail_fast=True)
        assert results == {"a": True, "b": True}
        assert manager.migrate_tenant.call_count == 2

    @pytest.mark.asyncio
    async def test_no_tenants_returns_empty_dict(self, manager: TenantMigrationManager) -> None:
        manager.get_tenants_to_migrate = MagicMock(return_value=[])
        results = await manager.migrate_all_tenants()
        assert results == {}

    @pytest.mark.asyncio
    async def test_custom_revision(self, manager: TenantMigrationManager) -> None:
        t1 = TenantConfig(bot_id="a", bot_token="ta")
        manager.get_tenants_to_migrate = MagicMock(return_value=[t1])
        manager.migrate_tenant = AsyncMock(return_value=True)
        await manager.migrate_all_tenants(revision="abc")
        manager.migrate_tenant.assert_called_once_with(t1, "abc")


class TestRollbackTenant:
    @pytest.mark.asyncio
    async def test_success(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result) as mock_run:
            result = await manager.rollback_tenant(tenant, verbose=True)
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "downgrade" in cmd
        assert "-1" in cmd

    @pytest.mark.asyncio
    async def test_failure(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="err")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result):
            result = await manager.rollback_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        with patch('tg_bot.tenant.migrations.subprocess.run',
                   side_effect=subprocess.TimeoutExpired(cmd="test", timeout=120)):
            result = await manager.rollback_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_general_exception(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        with patch('tg_bot.tenant.migrations.subprocess.run',
                   side_effect=Exception("rollback failed")):
            result = await manager.rollback_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_env_variables(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result) as mock_run:
            await manager.rollback_tenant(tenant)
        _, kwargs = mock_run.call_args
        assert kwargs['env']["TENANT_SCHEMA"] == tenant.db_schema
        assert kwargs['env']["TENANT_BOT_ID"] == tenant.bot_id

    @pytest.mark.asyncio
    async def test_custom_revision(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch('tg_bot.tenant.migrations.subprocess.run', return_value=mock_result) as mock_run:
            await manager.rollback_tenant(tenant, revision="base")
        cmd = mock_run.call_args[0][0]
        assert "base" in cmd


class TestCreateTenant:
    @pytest.mark.asyncio
    async def test_creates_schema_and_runs_migrations(
        self, manager: TenantMigrationManager, tenant: TenantConfig
    ) -> None:
        mock_db = AsyncMock()
        manager.migrate_tenant = AsyncMock(return_value=True)
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=mock_db):
            result = await manager.create_tenant(tenant, run_migrations=True)
        assert result is True
        mock_db.create_tenant_schema.assert_called_once_with(tenant)
        manager.migrate_tenant.assert_called_once_with(tenant)

    @pytest.mark.asyncio
    async def test_skip_migrations(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_db = AsyncMock()
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=mock_db):
            result = await manager.create_tenant(tenant, run_migrations=False)
        assert result is True
        mock_db.create_tenant_schema.assert_called_once_with(tenant)

    @pytest.mark.asyncio
    async def test_no_db_returns_true_if_migrations_skipped(
        self, manager: TenantMigrationManager, tenant: TenantConfig
    ) -> None:
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=None):
            result = await manager.create_tenant(tenant, run_migrations=False)
        assert result is True

    @pytest.mark.asyncio
    async def test_schema_creation_failure(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_db = AsyncMock()
        mock_db.create_tenant_schema.side_effect = Exception("schema error")
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=mock_db):
            result = await manager.create_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_migration_failure_returns_false(
        self, manager: TenantMigrationManager, tenant: TenantConfig
    ) -> None:
        mock_db = AsyncMock()
        manager.migrate_tenant = AsyncMock(return_value=False)
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=mock_db):
            result = await manager.create_tenant(tenant, run_migrations=True)
        assert result is False


class TestDropTenant:
    @pytest.mark.asyncio
    async def test_success(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_db = AsyncMock()
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=mock_db):
            result = await manager.drop_tenant(tenant)
        assert result is True
        mock_db.drop_tenant_schema.assert_called_once_with(tenant)

    @pytest.mark.asyncio
    async def test_no_db_returns_false(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=None):
            result = await manager.drop_tenant(tenant)
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, manager: TenantMigrationManager, tenant: TenantConfig) -> None:
        mock_db = AsyncMock()
        mock_db.drop_tenant_schema.side_effect = Exception("drop error")
        with patch('tg_bot.tenant.database.get_tenant_database', return_value=mock_db):
            result = await manager.drop_tenant(tenant)
        assert result is False


class TestGetMigrationManager:
    def test_returns_tenant_migration_manager_instance(self) -> None:
        mgr = get_migration_manager()
        assert isinstance(mgr, TenantMigrationManager)
