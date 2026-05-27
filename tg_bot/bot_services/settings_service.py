# Tg_bot/bot_services/settings_service.py
from typing import Any

import asyncpg

from utils.logging_setup import logger


class SettingsService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        logger.info("Сервис настроек инициализирован.")

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Получает значение настройки из БД. Возвращает default, если ключ не найден."""
        value = await self.pool.fetchval("SELECT value FROM bot_settings WHERE key = $1", key)
        return value if value is not None else default

    async def set_setting(self, key: str, value: str) -> Any:
        """Устанавливает или обновляет значение настройки в БД."""
        logger.info(f"Обновление настройки: '{key}' = '{value}'")
        await self.pool.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """,
            key, value
        )

    async def get_all_settings(self) -> dict[str, str]:
        """Получает все настройки из БД."""
        rows = await self.pool.fetch("SELECT key, value FROM bot_settings")
        return {row['key']: row['value'] for row in rows}

    async def delete_setting(self, key: str) -> None:
        """Удаляет настройку из БД."""
        logger.info(f"Удаление настройки: '{key}'")
        await self.pool.execute("DELETE FROM bot_settings WHERE key = $1", key)
