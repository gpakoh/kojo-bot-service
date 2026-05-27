# Tg_bot/tenant/migrations.py
"""
Multi-tenant Migration Management.

Applies Alembic migrations to all tenants (schemas).
"""
import logging
import os
import subprocess
import sys
from typing import Any, List, Optional

from tg_bot.tenant.config import TenantConfig, get_tenant_registry

logger = logging.getLogger(__name__)


class TenantMigrationManager:
    """
    Manages migrations for multiple tenants.

    Supports:
    - Running migrations for all tenants
    - Running migrations for specific tenant
    - Rolling back migrations
    - Creating new tenant schemas
    """

    def __init__(self, alembic_dir: Optional[str] = None) -> None:
        self.alembic_dir = str(alembic_dir or os.environ.get(
            "ALEMBIC_DIR", "alembic"
        ))

    def get_tenants_to_migrate(self) -> List[TenantConfig]:
        """Get list of tenants that need migrations."""
        registry = get_tenant_registry()

        # Check If We Should Migrate All Or Specific Tenant
        target_tenant = os.environ.get("TENANT_TO_MIGRATE")

        if target_tenant:
            tenant = registry.get_tenant(target_tenant)
            return [tenant] if tenant else []

        return list(registry.get_all_tenants().values())

    async def migrate_tenant(
        self,
        tenant: TenantConfig,
        revision: str = "head",
        verbose: bool = False,
    ) -> bool:
        """
        Run migrations for a specific tenant.

        Uses schema-per-tenant strategy: sets search_path before running.
        """
        schema = tenant.db_schema
        logger.info(f"🔄 Running migrations for tenant: {tenant.bot_id} (schema: {schema})")

        env = os.environ.copy()
        env["TENANT_SCHEMA"] = schema
        env["TENANT_BOT_ID"] = tenant.bot_id

        cmd: List[str] = [
            sys.executable, "-m", "alembic",
            "upgrade", revision,
            "--directory", self.alembic_dir,
        ]

        if verbose:
            cmd.append("-v")

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                logger.info(f"✅ Migrations applied for {tenant.bot_id}")
                if verbose:
                    logger.info(result.stdout)
                return True
            else:
                logger.error(f"❌ Migration failed for {tenant.bot_id}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"⏱️ Migration timeout for {tenant.bot_id}")
            return False
        except Exception as e:
            # Broad by design: maintenance wrapper — migration error must not crash the process
            logger.error(f"❌ Migration error for {tenant.bot_id}: {e}")
            return False

    async def migrate_all_tenants(
        self,
        revision: str = "head",
        fail_fast: bool = False,
    ) -> dict[str, Any]:
        """
        Run migrations for all configured tenants.

        Returns:
            dict[str, Any] with results: {"kojo": True, "lebo_coffee": False, ...}
        """
        tenants = self.get_tenants_to_migrate()

        if not tenants:
            logger.warning("No Tenants Configured For Migration")
            return {}

        results = {}

        for tenant in tenants:
            success = await self.migrate_tenant(tenant, revision)
            results[tenant.bot_id] = success

            if fail_fast and not success:
                logger.error(f"Stopping migration due to failure in {tenant.bot_id}")
                break

        # Summary
        success_count = sum(1 for v in results.values() if v)
        total = len(results)

        logger.info(
            f"📊 Migration complete: {success_count}/{total} tenants successful"
        )

        return results
    async def rollback_tenant(
        self,
        tenant: TenantConfig,
        revision: str = "-1",
        verbose: bool = False,
    ) -> bool:
        """
        Rollback tenant schema to previous migration revision.
        """
        schema = tenant.db_schema
        logger.info(f"⏪ Rolling back tenant: {tenant.bot_id} (schema: {schema})")

        env = os.environ.copy()
        env["TENANT_SCHEMA"] = schema
        env["TENANT_BOT_ID"] = tenant.bot_id

        cmd: List[str] = [
            sys.executable, "-m", "alembic",
            "downgrade", revision,
            "--directory", self.alembic_dir,
        ]

        if verbose:
            cmd.append("-v")

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                logger.info(f"✅ Rollback applied for {tenant.bot_id}")
                if verbose:
                    logger.info(result.stdout)
                return True
            else:
                logger.error(f"❌ Rollback failed for {tenant.bot_id}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"⏱️ Rollback timeout for {tenant.bot_id}")
            return False
        except Exception as e:
            # Broad by design: maintenance wrapper — rollback error must not crash the process
            logger.error(f"❌ Rollback error for {tenant.bot_id}: {e}")
            return False

    async def create_tenant(
        self,
        tenant: TenantConfig,
        run_migrations: bool = True,
    ) -> bool:
        """
        Create new tenant schema and optionally run migrations.

        Steps:
        1. Create schema
        2. Run base migrations (tables, etc.)
        """
        logger.info(f"🆕 Creating tenant: {tenant.bot_id}")

        # Import Here To Avoid Circular Imports
        from tg_bot.tenant.database import get_tenant_database

        db = get_tenant_database()
        if db:
            try:
                await db.create_tenant_schema(tenant)
            except Exception as e:
                # Broad by design: maintenance wrapper — schema creation error must not crash tenant setup
                logger.error(f"Failed to create schema for {tenant.bot_id}: {e}")
                return False

        # Run Migrations
        if run_migrations:
            return await self.migrate_tenant(tenant)

        return True

    async def drop_tenant(self, tenant: TenantConfig) -> bool:
        """
        Drop tenant schema (DANGEROUS!).
        """
        logger.warning(f"🗑️ Dropping tenant: {tenant.bot_id}")

        from tg_bot.tenant.database import get_tenant_database

        db = get_tenant_database()
        if db:
            try:
                await db.drop_tenant_schema(tenant)
                return True
            except Exception as e:
                # Broad by design: maintenance wrapper — drop error must not crash cleanup
                logger.error(f"Failed to drop schema for {tenant.bot_id}: {e}")
                return False

        return False


def get_migration_manager() -> TenantMigrationManager:
    """Get migration manager instance."""
    return TenantMigrationManager()


__all__ = [
    'TenantMigrationManager',
    'get_migration_manager',
]
