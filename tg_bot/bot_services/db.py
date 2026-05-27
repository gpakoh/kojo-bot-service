# Tg_bot/bot_services/db.py
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

async def init_db(pool: asyncpg.Pool) -> Any:
    """
    Инициализация схемы делегирована alembic.
    Эта функция оставлена для обратной совместимости.
    """
    logger.info("Схема управляется alembic, init_db пропущен.")
    return
