import logging
from typing import TYPE_CHECKING, cast

from tg_bot.bot_services.settings_service import SettingsService
from tg_bot.config_service import HierarchicalConfig, create_hierarchical_config

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def init_app_config(
    settings_service: SettingsService | None = None,
    env_path: str | None = None,
    cache_ttl: float = 60.0,
) -> HierarchicalConfig:
    """Create app config - caller must store in bot_data."""
    config = await create_hierarchical_config(
        settings_service=settings_service,
        env_path=env_path,
        cache_ttl=cache_ttl,
    )
    logger.info("App Config Created")
    return config


def get_app_config(context: 'ContextTypes.DEFAULT_TYPE') -> HierarchicalConfig:
    """Get config from context.bot_data (DI)."""
    config = context.bot_data.get('app_config')
    if config is None:
        raise RuntimeError("app_config not found in bot_data. Initialize in post_init.")
    return cast(HierarchicalConfig, config)


__all__ = ['init_app_config', 'get_app_config', 'HierarchicalConfig']
