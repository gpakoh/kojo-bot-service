import importlib
from typing import Any

import pytest

BOT_SERVICES_MODULES = [
    "tg_bot.bot_services.base_integration",
    "tg_bot.bot_services.cart_service",
    "tg_bot.bot_services.cart_validator",
    "tg_bot.bot_services.communication_service",
    "tg_bot.bot_services.config_service",
    "tg_bot.bot_services.delivery_service",
    "tg_bot.bot_services.favorite_service",
    "tg_bot.bot_services.info_service",
    "tg_bot.bot_services.notification_service",
    "tg_bot.bot_services.order_service",
    "tg_bot.bot_services.payment_service",
    "tg_bot.bot_services.product_service",
    "tg_bot.bot_services.product_sync_service",
    "tg_bot.bot_services.settings_service",
    "tg_bot.bot_services.user_address_service",
    "tg_bot.bot_services.user_service",
]


class TestBotServicesImport:
    @pytest.mark.parametrize("module_name", BOT_SERVICES_MODULES)
    def test_module_imports(self, module_name: str) -> Any:
        mod = importlib.import_module(module_name)
        assert mod is not None
