# Tg_bot/bot_services/settings_service.py
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg

from tg_bot.tenant.config import get_current_tenant
from utils.logging_setup import logger


class SettingsService:
    def __init__(self, pool: asyncpg.Pool, db_manager: Any = None) -> None:
        self.pool = pool
        self.db_manager = db_manager
        logger.info("Сервис настроек инициализирован.")

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Any]:
        tenant = get_current_tenant()
        tenant_id = getattr(tenant, "bot_id", tenant)

        if tenant_id and self.db_manager is not None:
            async with self.db_manager.tenant_connection(tenant_id) as conn:
                yield conn
            return

        async with self.pool.acquire() as conn:
            yield conn

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Получает значение настройки из БД. Возвращает default, если ключ не найден."""
        async with self._connection() as conn:
            value = await conn.fetchval("SELECT value FROM bot_settings WHERE key = $1", key)
        return value if value is not None else default

    async def set_setting(self, key: str, value: str) -> Any:
        """Устанавливает или обновляет значение настройки в БД."""
        logger.info(f"Обновление настройки: '{key}' = '{value}'")
        async with self._connection() as conn:
            return await conn.execute(
                """
                INSERT INTO bot_settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                """,
                key, value
            )

    async def get_all_settings(self) -> dict[str, str]:
        """Получает все настройки из БД."""
        async with self._connection() as conn:
            rows = await conn.fetch("SELECT key, value FROM bot_settings")
        return {row['key']: row['value'] for row in rows}

    async def delete_setting(self, key: str) -> None:
        """Удаляет настройку из БД."""
        logger.info(f"Удаление настройки: '{key}'")
        async with self._connection() as conn:
            await conn.execute("DELETE FROM bot_settings WHERE key = $1", key)
