"""Tests for TenantBootstrapService — dry-run plan + execution."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.tenant.bootstrap import (
    DEFAULT_WELCOME_MESSAGE,
    BootstrapPlan,
    BootstrapStep,
    StepResult,
    TenantBootstrapService,
)
from tg_bot.tenant.config import TenantConfig, TenantRegistry


@pytest.fixture(autouse=True)
def _reset_registry() -> Any:
    TenantRegistry._instance = None
    yield
    TenantRegistry._instance = None


@pytest.fixture
def tenant() -> TenantConfig:
    return TenantConfig(bot_id="test_bot", bot_token="test_token")


@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock()
    cm = MagicMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    pool.acquire.return_value = cm
    return pool


@pytest.fixture
def mock_services() -> dict[str, Any]:
    settings = AsyncMock()
    settings.get_setting = AsyncMock(return_value=None)
    settings.set_setting = AsyncMock()
    info = AsyncMock()
    info.get_children = AsyncMock(return_value=[])
    info.create_page = AsyncMock(return_value=1)
    user = AsyncMock()
    user.get_users_by_criteria = AsyncMock(return_value=[])
    user.create_approved_admin = AsyncMock()
    return {
        "db_manager": MagicMock(),
        "settings_service": settings,
        "info_service": info,
        "user_service": user,
    }


@pytest.fixture
def bootstrap_service(
    mock_pool: MagicMock,
    mock_services: dict[str, Any],
) -> TenantBootstrapService:
    return TenantBootstrapService(
        pool=mock_pool,
        db_manager=mock_services["db_manager"],
        settings_service=mock_services["settings_service"],
        info_service=mock_services["info_service"],
        user_service=mock_services["user_service"],
    )


class TestTenantBootstrapServicePlan:

    @pytest.mark.asyncio
    async def test_plan_fresh_tenant_all_steps_planned(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None

        plan = await bootstrap_service.plan(tenant, admin_telegram_ids=[12345])

        assert isinstance(plan, BootstrapPlan)
        assert plan.tenant is tenant
        planned_steps = {s.step for s in plan.steps if s.status == "planned"}
        assert BootstrapStep.CREATE_SCHEMA in planned_steps
        assert BootstrapStep.RUN_MIGRATIONS in planned_steps
        assert BootstrapStep.SEED_SETTINGS in planned_steps
        assert BootstrapStep.SEED_CMS in planned_steps
        assert BootstrapStep.CREATE_ADMIN in planned_steps
        assert BootstrapStep.REGISTER_RUNTIME in planned_steps
        assert plan.has_pending

    @pytest.mark.asyncio
    async def test_plan_skips_existing_schema(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = tenant.db_schema

        plan = await bootstrap_service.plan(tenant)

        schema_step = [s for s in plan.steps if s.step == BootstrapStep.CREATE_SCHEMA][0]
        assert schema_step.status == "skipped"

    @pytest.mark.asyncio
    async def test_plan_skips_existing_settings(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
        mock_services: dict[str, Any],
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None
        mock_services["settings_service"].get_setting.return_value = "exists"

        plan = await bootstrap_service.plan(tenant)

        settings_step = [s for s in plan.steps if s.step == BootstrapStep.SEED_SETTINGS][0]
        assert settings_step.status == "skipped"

    @pytest.mark.asyncio
    async def test_plan_skips_existing_cms(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
        mock_services: dict[str, Any],
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None
        mock_services["info_service"].get_children.return_value = [{"id": 1, "title": "About"}]

        plan = await bootstrap_service.plan(tenant)

        cms_step = [s for s in plan.steps if s.step == BootstrapStep.SEED_CMS][0]
        assert cms_step.status == "skipped"

    @pytest.mark.asyncio
    async def test_plan_skips_existing_admins(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
        mock_services: dict[str, Any],
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None
        mock_user = MagicMock()
        mock_user.telegram_id = 12345
        mock_services["user_service"].get_users_by_criteria.return_value = [mock_user]

        plan = await bootstrap_service.plan(tenant, admin_telegram_ids=[12345])

        admin_step = [s for s in plan.steps if s.step == BootstrapStep.CREATE_ADMIN][0]
        assert admin_step.status == "skipped"

    @pytest.mark.asyncio
    async def test_plan_no_admin_ids_skips_admin_step(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None

        plan = await bootstrap_service.plan(tenant)

        admin_step = [s for s in plan.steps if s.step == BootstrapStep.CREATE_ADMIN][0]
        assert admin_step.status == "skipped"

    @pytest.mark.asyncio
    async def test_plan_skips_registered_tenant(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = None
        registry = TenantRegistry.get_instance()
        registry._tenants["test_bot"] = tenant

        plan = await bootstrap_service.plan(tenant)

        register_step = [s for s in plan.steps if s.step == BootstrapStep.REGISTER_RUNTIME][0]
        assert register_step.status == "skipped"

    @pytest.mark.asyncio
    async def test_plan_no_pending_when_all_existing(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_pool: MagicMock,
        mock_services: dict[str, Any],
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval.return_value = tenant.db_schema
        mock_services["settings_service"].get_setting.return_value = "exists"
        mock_services["info_service"].get_children.return_value = [{"id": 1, "title": "About"}]
        mock_user = MagicMock()
        mock_user.telegram_id = 12345
        mock_services["user_service"].get_users_by_criteria.return_value = [mock_user]
        registry = TenantRegistry.get_instance()
        registry._tenants["test_bot"] = tenant

        plan = await bootstrap_service.plan(tenant, admin_telegram_ids=[12345])

        assert not plan.has_pending


class TestTenantBootstrapServiceExecute:

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_all_steps(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=True)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        for step_type in BootstrapStep:
            plan.add_step(step_type, f"Step {step_type.value}")

        success = await bootstrap_service.execute(plan, admin_telegram_ids=[12345])

        assert success
        mock_db.create_tenant_schema.assert_awaited_once_with(tenant)
        mock_mm.migrate_tenant.assert_awaited_once_with(tenant)

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_skips_non_planned(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=True)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.CREATE_SCHEMA, "Create schema")
        plan.add_step(BootstrapStep.SEED_SETTINGS, "Seed settings", status="skipped")
        plan.add_step(BootstrapStep.RUN_MIGRATIONS, "Migrate")

        success = await bootstrap_service.execute(plan)

        assert success
        mock_db.create_tenant_schema.assert_awaited_once()
        mock_mm.migrate_tenant.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_seeds_settings(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_services: dict[str, Any],
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=True)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.SEED_SETTINGS, "Seed settings")

        success = await bootstrap_service.execute(plan)

        assert success
        mock_services["settings_service"].set_setting.assert_any_call(
            "registration_welcome_text", DEFAULT_WELCOME_MESSAGE
        )
        mock_services["settings_service"].set_setting.assert_any_call("registration_logo_type", "photo")

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_seeds_cms(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_services: dict[str, Any],
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=True)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.SEED_CMS, "Seed CMS")

        success = await bootstrap_service.execute(plan)

        assert success
        mock_services["info_service"].create_page.assert_awaited_once_with(
            parent_id=None,
            title="О нас",
            text="Добро пожаловать! Информация о нашем магазине будет добавлена позже.",
        )

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_creates_admin(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_services: dict[str, Any],
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=True)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.CREATE_ADMIN, "Create admin")

        success = await bootstrap_service.execute(plan, admin_telegram_ids=[12345, 67890])

        assert success
        assert mock_services["user_service"].create_approved_admin.await_count == 2

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_registers_in_runtime(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=True)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.REGISTER_RUNTIME, "Register")

        assert TenantRegistry.get_instance().get_tenant("test_bot") is None

        success = await bootstrap_service.execute(plan)

        assert success
        assert TenantRegistry.get_instance().get_tenant("test_bot") is tenant

    @pytest.mark.asyncio
    @patch("tg_bot.tenant.bootstrap.get_tenant_database")
    @patch("tg_bot.tenant.bootstrap.TenantMigrationManager")
    async def test_execute_returns_false_on_migration_failure(
        self,
        mock_migration_manager: MagicMock,
        mock_get_tenant_database: MagicMock,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
    ) -> None:
        mock_db = AsyncMock()
        mock_get_tenant_database.return_value = mock_db
        mock_mm = MagicMock()
        mock_mm.migrate_tenant = AsyncMock(return_value=False)
        mock_migration_manager.return_value = mock_mm

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.CREATE_SCHEMA, "Create schema")
        plan.add_step(BootstrapStep.RUN_MIGRATIONS, "Migrate")
        plan.add_step(BootstrapStep.SEED_SETTINGS, "Seed settings")

        success = await bootstrap_service.execute(plan)

        assert not success
        migrate_step = plan.steps[1]
        assert migrate_step.status == "error"

    @pytest.mark.asyncio
    async def test_execute_on_empty_plan_succeeds(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
    ) -> None:
        plan = BootstrapPlan(tenant=tenant)

        success = await bootstrap_service.execute(plan)

        assert success

    @pytest.mark.asyncio
    async def test_execute_handles_exception_gracefully(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_services: dict[str, Any],
    ) -> None:
        mock_services["settings_service"].set_setting.side_effect = RuntimeError("DB gone")

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.SEED_SETTINGS, "Seed settings")

        success = await bootstrap_service.execute(plan)

        assert not success
        assert plan.steps[0].status == "error"
        assert "DB gone" in plan.steps[0].detail

    @pytest.mark.asyncio
    async def test_execute_contextvar_is_cleaned_after_seed(
        self,
        bootstrap_service: TenantBootstrapService,
        tenant: TenantConfig,
        mock_services: dict[str, Any],
    ) -> None:
        from tg_bot.tenant.config import get_current_tenant

        plan = BootstrapPlan(tenant=tenant)
        plan.add_step(BootstrapStep.SEED_SETTINGS, "Seed settings")

        await bootstrap_service.execute(plan)

        assert get_current_tenant() is None


class TestBootstrapPlanHelpers:

    def test_has_pending_true(self) -> None:
        plan = BootstrapPlan(tenant=MagicMock())
        plan.add_step(BootstrapStep.CREATE_SCHEMA, "Create")
        assert plan.has_pending

    def test_has_pending_false(self) -> None:
        plan = BootstrapPlan(tenant=MagicMock())
        plan.add_step(BootstrapStep.CREATE_SCHEMA, "Create", status="completed")
        assert not plan.has_pending

    def test_add_step_appends(self) -> None:
        plan = BootstrapPlan(tenant=MagicMock())
        plan.add_step(BootstrapStep.CREATE_SCHEMA, "test", status="skipped", detail="exists")
        assert len(plan.steps) == 1
        s = plan.steps[0]
        assert s.step == BootstrapStep.CREATE_SCHEMA
        assert s.description == "test"
        assert s.status == "skipped"
        assert s.detail == "exists"


class TestBootstrapStepResult:

    def test_defaults(self) -> None:
        r = StepResult(step=BootstrapStep.CREATE_SCHEMA, description="test")
        assert r.status == "planned"
        assert r.detail == ""
