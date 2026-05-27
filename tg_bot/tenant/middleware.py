# Tg_bot/tenant/middleware.py
"""
Tenant Middleware For Telegram Bot.

Extracts tenant (bot_id) from webhook URL or bot token.
Sets tenant context for request processing using contextvars.
"""
import logging
from typing import Any, Callable, Optional

from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.tenant.config import (
    TenantConfig,
    TenantRegistry,
    _tenant_context,
    get_tenant_registry,
    set_current_tenant,
)

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Middleware to extract and set tenant context.

    Supports multiple extraction methods:
    1. From webhook URL path: /webhook/{bot_id}
    2. From bot token (if single-tenant)
    3. From custom header

    Uses contextvars for asyncio-safe tenant isolation.
    """

    def __init__(
        self,
        registry: Optional[TenantRegistry] = None,
        path_prefix: str = "/webhook",
    ):
        self.registry = registry or get_tenant_registry()
        self.path_prefix = path_prefix

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        next_handler: Callable,
    ) -> Any:
        """
        Extract tenant and execute handler in tenant context.

        Extracts bot_id from:
        1. context.bot.username / token match
        2. Custom header X-Bot-ID (in bot_data)
        3. Falls back to default tenant
        """
        bot_id = None

        # Method 1: Match By Bot Token
        if context.bot and context.bot.username:
            for tenant_bot_id, config in self.registry.get_all_tenants().items():
                if config.bot_token == context.bot.token:
                    bot_id = tenant_bot_id
                    break

            if not bot_id:
                bot_id = context.bot.username

        # Method 2: From Bot_data Set By Reverse Proxy
        if not bot_id:
            bot_id = context.bot_data.get('_tenant_bot_id')

        # Method 3: Default Tenant
        if not bot_id:
            default_tenant = self.registry.get_default_tenant()
            if default_tenant:
                bot_id = default_tenant.bot_id

        # Validate
        tenant = None
        if bot_id:
            tenant = self.registry.get_tenant(bot_id)

        if tenant is None:
            logger.warning("Unknown tenant: %s, using default", bot_id)
            tenant = self.registry.get_default_tenant()

        if tenant is None:
            logger.error("No Tenants Configured!")
            return await next_handler(update, context)

        # Set Asyncio-safe Tenant Context Via Contextvars
        token = _tenant_context.set(tenant)
        set_current_tenant(tenant)

        context.bot_data['_tenant'] = tenant
        context.bot_data['_tenant_bot_id'] = tenant.bot_id

        try:
            return await next_handler(update, context)
        finally:
            _tenant_context.reset(token)


def get_tenant_from_context(context: ContextTypes.DEFAULT_TYPE) -> Optional[TenantConfig]:
    """Get current tenant from context."""
    return context.bot_data.get('_tenant')


__all__ = [
    'TenantMiddleware',
    'get_tenant_from_context',
]
