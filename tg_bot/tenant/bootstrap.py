import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from tg_bot.models import UserRole
from tg_bot.tenant.config import TenantConfig, get_tenant_registry, set_current_tenant
from tg_bot.tenant.database import get_tenant_database
from tg_bot.tenant.migrations import TenantMigrationManager

logger = logging.getLogger(__name__)

DEFAULT_WELCOME_MESSAGE = "☕️ Добро пожаловать! Используйте меню, чтобы сделать заказ."

DEFAULT_SETTINGS: dict[str, str] = {
    "registration_welcome_text": DEFAULT_WELCOME_MESSAGE,
    "registration_logo_type": "photo",
}


class BootstrapStep(str, Enum):
    CREATE_SCHEMA = "create_schema"
    RUN_MIGRATIONS = "run_migrations"
    SEED_SETTINGS = "seed_settings"
    SEED_CMS = "seed_cms"
    CREATE_ADMIN = "create_admin"
    REGISTER_RUNTIME = "register_runtime"


@dataclass
class StepResult:
    step: BootstrapStep
    description: str
    status: str = "planned"
    detail: str = ""


@dataclass
class BootstrapPlan:
    tenant: TenantConfig
    steps: list[StepResult] = field(default_factory=list)

    def add_step(self, step: BootstrapStep, description: str, status: str = "planned", detail: str = "") -> None:
        self.steps.append(StepResult(step=step, description=description, status=status, detail=detail))

    @property
    def has_pending(self) -> bool:
        return any(s.status == "planned" for s in self.steps)


class TenantBootstrapService:
    def __init__(
        self,
        pool: Any,
        db_manager: Any,
        settings_service: Any,
        info_service: Any,
        user_service: Any,
    ) -> None:
        self.pool = pool
        self.db_manager = db_manager
        self.settings_service = settings_service
        self.info_service = info_service
        self.user_service = user_service

    async def plan(
        self,
        tenant: TenantConfig,
        admin_telegram_ids: Optional[list[int]] = None,
        skip_existing: bool = True,
    ) -> BootstrapPlan:
        plan = BootstrapPlan(tenant=tenant)

        schema_exists = await self._check_schema_exists(tenant)
        if schema_exists:
            if skip_existing:
                plan.add_step(BootstrapStep.CREATE_SCHEMA, f"Schema '{tenant.db_schema}' already exists", "skipped")
            else:
                plan.add_step(
                    BootstrapStep.CREATE_SCHEMA,
                    f"Schema '{tenant.db_schema}' already exists (will recreate)",
                    "planned",
                )
        else:
            plan.add_step(BootstrapStep.CREATE_SCHEMA, f"Create schema '{tenant.db_schema}'", "planned")

        migrations_needed = not schema_exists or await self._check_migrations_needed(tenant)
        if migrations_needed:
            plan.add_step(BootstrapStep.RUN_MIGRATIONS, "Run Alembic migrations to head", "planned")
        else:
            plan.add_step(BootstrapStep.RUN_MIGRATIONS, "Migrations already at head", "skipped")

        settings_seeded = await self._check_settings_seeded(tenant)
        if settings_seeded and skip_existing:
            plan.add_step(BootstrapStep.SEED_SETTINGS, "Default settings already seeded", "skipped")
        else:
            plan.add_step(BootstrapStep.SEED_SETTINGS, f"Seed {len(DEFAULT_SETTINGS)} default settings", "planned")

        cms_seeded = await self._check_cms_seeded(tenant)
        if cms_seeded and skip_existing:
            plan.add_step(BootstrapStep.SEED_CMS, "Default CMS pages already seeded", "skipped")
        else:
            plan.add_step(BootstrapStep.SEED_CMS, "Seed default CMS info pages", "planned")

        if admin_telegram_ids:
            existing_admins = await self._check_existing_admins(tenant, admin_telegram_ids)
            missing_ids = [tid for tid in admin_telegram_ids if tid not in existing_admins]
            if missing_ids:
                plan.add_step(
                    BootstrapStep.CREATE_ADMIN,
                    f"Create {len(missing_ids)} admin user(s): {missing_ids}",
                    "planned",
                )
            else:
                plan.add_step(BootstrapStep.CREATE_ADMIN, "All admin users already exist", "skipped")
        else:
            plan.add_step(BootstrapStep.CREATE_ADMIN, "No admin telegram IDs provided — skipped", "skipped")

        registry = get_tenant_registry()
        if registry.get_tenant(tenant.bot_id):
            plan.add_step(
                BootstrapStep.REGISTER_RUNTIME,
                f"Tenant '{tenant.bot_id}' already registered in runtime",
                "skipped",
            )
        else:
            plan.add_step(
                BootstrapStep.REGISTER_RUNTIME,
                f"Register tenant '{tenant.bot_id}' in runtime registry",
                "planned",
            )

        return plan

    async def execute(
        self,
        plan: BootstrapPlan,
        admin_telegram_ids: Optional[list[int]] = None,
    ) -> bool:
        tenant = plan.tenant

        for step in plan.steps:
            if step.status != "planned":
                continue

            try:
                if step.step == BootstrapStep.CREATE_SCHEMA:
                    db = get_tenant_database()
                    if db:
                        await db.create_tenant_schema(tenant)
                    step.status = "completed"

                elif step.step == BootstrapStep.RUN_MIGRATIONS:
                    mm = TenantMigrationManager()
                    success = await mm.migrate_tenant(tenant)
                    if not success:
                        step.status = "error"
                        step.detail = "Migration subprocess failed"
                        return False
                    step.status = "completed"

                elif step.step == BootstrapStep.SEED_SETTINGS:
                    set_current_tenant(tenant)
                    for key, value in DEFAULT_SETTINGS.items():
                        await self.settings_service.set_setting(key, value)
                    set_current_tenant(None)
                    step.status = "completed"

                elif step.step == BootstrapStep.SEED_CMS:
                    set_current_tenant(tenant)
                    await self._seed_default_cms_pages()
                    set_current_tenant(None)
                    step.status = "completed"

                elif step.step == BootstrapStep.CREATE_ADMIN:
                    set_current_tenant(tenant)
                    for tid in (admin_telegram_ids or []):
                        await self.user_service.create_approved_admin(
                            telegram_id=tid,
                            fio=f"Admin {tid}",
                            phone="N/A",
                            email=f"a{tid}@bot.local",
                        )
                    set_current_tenant(None)
                    step.status = "completed"

                elif step.step == BootstrapStep.REGISTER_RUNTIME:
                    registry = get_tenant_registry()
                    registry._tenants[tenant.bot_id] = tenant  # type: ignore[union-attr]
                    step.status = "completed"

            except Exception as e:
                logger.error(f"Bootstrap step {step.step.value} failed: {e}")
                step.status = "error"
                step.detail = str(e)
                return False

        return True

    async def _check_schema_exists(self, tenant: TenantConfig) -> bool:
        schema = tenant.db_schema
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchval(
                    "SELECT schema_name FROM information_schema.schemata WHERE schema_name = $1",
                    schema,
                )
                return bool(row)
        except Exception:
            return False

    async def _check_migrations_needed(self, tenant: TenantConfig) -> bool:
        schema = tenant.db_schema
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    f"WHERE table_schema = '{schema}' AND table_name = 'alembic_version')"
                )
                return not bool(row)
        except Exception:
            return True

    async def _check_settings_seeded(self, tenant: TenantConfig) -> bool:
        set_current_tenant(tenant)
        try:
            for key in DEFAULT_SETTINGS:
                value = await self.settings_service.get_setting(key)
                if value is None:
                    return False
            return True
        except Exception:
            return False
        finally:
            set_current_tenant(None)

    async def _check_cms_seeded(self, tenant: TenantConfig) -> bool:
        set_current_tenant(tenant)
        try:
            pages = await self.info_service.get_children(None)
            return len(pages) > 0
        except Exception:
            return False
        finally:
            set_current_tenant(None)

    async def _check_existing_admins(self, tenant: TenantConfig, admin_ids: list[int]) -> set[int]:
        set_current_tenant(tenant)
        try:
            users = await self.user_service.get_users_by_criteria(role=UserRole.ADMIN)
            return {u.telegram_id for u in users if hasattr(u, 'telegram_id')}
        except Exception:
            return set()
        finally:
            set_current_tenant(None)

    async def _seed_default_cms_pages(self) -> None:
        try:
            await self.info_service.create_page(
                parent_id=None,
                title="О нас",
                text="Добро пожаловать! Информация о нашем магазине будет добавлена позже.",
            )
        except Exception as e:
            logger.warning(f"Failed to seed default CMS page: {e}")


__all__ = [
    "BootstrapStep",
    "StepResult",
    "BootstrapPlan",
    "TenantBootstrapService",
    "DEFAULT_SETTINGS",
    "DEFAULT_WELCOME_MESSAGE",
]
