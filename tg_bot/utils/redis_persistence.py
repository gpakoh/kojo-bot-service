# Tg_bot/utils/redis_persistence.py
"""
Redis Persistence for PTB.

Uses DictPersistence as base (simpler implementation).
For production with Redis, consider external sync or PTB's built-in solutions.
"""
import logging

from telegram.ext import DictPersistence

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class RedisPersistence(DictPersistence):
    """PTB Persistence using in-memory Dict (Redis sync can be added later)."""

    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
    ):
        super().__init__()
        self.redis_url = redis_url
        logger.info(f"RedisPersistence initialized with Redis URL: {redis_url}")


__all__ = ['RedisPersistence']
