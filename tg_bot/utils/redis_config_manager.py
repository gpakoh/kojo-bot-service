# Tg_bot/utils/redis_config_manager.py
"""
Redis Config Manager (Backward Compatibility Wrapper).

Use tg_bot.infrastructure.cache.Cache for new code.
"""
import logging

logger = logging.getLogger(__name__)

# Re-export From Infrastructure For Backward Compatibility

from tg_bot.infrastructure.cache import Cache as RedisConfigManager

__all__ = ['RedisConfigManager']
