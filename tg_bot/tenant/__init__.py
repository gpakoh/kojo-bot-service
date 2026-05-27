# Tg_bot/tenant/__init__.py
"""
Multi-tenancy Support.

Provides:
- Tenant configuration management
- Tenant middleware for request context
- Database isolation (schema-per-tenant or shared-schema)
- Migration management for multiple tenants

Configuration via environment:
    WARMUP_BOT_IDS=kojo,lebo_coffee,MarxMind
    kojo_TOKEN=xxx
    lebo_coffee_TOKEN=xxx
    MarxMind_TOKEN=xxx

    # Optional Per-tenant Overrides
    kojo_QUART_URL=http://localhost:5000
    lebo_coffee_QUART_URL=http://other:5000
"""
from typing import Any, Optional

from tg_bot.tenant.config import (
    TenantConfig,
    TenantRegistry,
    get_current_tenant,
    get_tenant_registry,
    set_current_tenant,
)
from tg_bot.tenant.database import (
    TenantDatabase,
    get_tenant_database,
)
from tg_bot.tenant.middleware import (
    TenantMiddleware,
    get_tenant_from_context,
)
from tg_bot.tenant.migrations import (
    TenantMigrationManager,
    get_migration_manager,
)

__all__ = [
    # Config
    'TenantConfig',
    'TenantRegistry',
    'get_tenant_registry',
    'get_current_tenant',
    'set_current_tenant',
    # Middleware
    'TenantMiddleware',
    'get_tenant_from_context',
    # Database
    'TenantDatabase',
    'get_tenant_database',
    # Migrations
    'TenantMigrationManager',
    'get_migration_manager',
]
