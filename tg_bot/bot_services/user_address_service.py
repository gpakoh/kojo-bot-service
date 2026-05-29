# Tg_bot/bot_services/user_address_service.py
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, Optional, cast

import asyncpg

from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)

class UserAddressService:
    def __init__(self, pool: asyncpg.Pool, db_manager: Any = None) -> None:
        self.pool = pool
        self.db_manager = db_manager
        logger.info("Useraddressservice инициализирован.")

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Any]:
        tenant = get_current_tenant()
        tenant_id = getattr(tenant, "bot_id", None) if tenant else None

        if self.db_manager is not None and tenant_id:
            async with self.db_manager.tenant_connection(tenant_id) as conn:
                yield conn
            return

        async with self.pool.acquire() as conn:
            yield conn

    async def init_table(self) -> Any:
        """Создает таблицу адресов, если она не существует."""
        async with self._connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_saved_addresses (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    provider VARCHAR(20) NOT NULL, -- 'cdek' или 'yandex'
                    point_id VARCHAR(100) NOT NULL,
                    address_text TEXT NOT NULL,
                    custom_name VARCHAR(100), -- Название, которое дал пользователь (напр. 'Дом')
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, provider, point_id) -- Чтобы не дублировать одну точку
                );
                CREATE INDEX IF NOT EXISTS idx_usa_user ON user_saved_addresses(user_id);
            """)
            logger.info("Таблица user_saved_addresses проверена/создана.")

    async def add_address(self, user_id: int, provider: str, point_id: str, address_text: str, custom_name: str | None = None) -> int:
        """Добавляет адрес. Если это первый адрес провайдера - делает его дефолтным."""
        provider = 'cdek' if 'cdek' in provider else 'yandex' # Нормализация

        async with self._connection() as conn:
            # Проверяем, есть ли уже адреса этого типа
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM user_saved_addresses WHERE user_id = $1 AND provider = $2",
                user_id, provider
            )
            is_default = (count == 0) # Если 0, то новый будет дефолтным

            # Вставляем или обновляем (если точка уже была, обновляем имя/адрес)
            address_id = await conn.fetchval("""
                INSERT INTO user_saved_addresses (user_id, provider, point_id, address_text, custom_name, is_default)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, provider, point_id)
                DO UPDATE SET address_text = EXCLUDED.address_text, custom_name = COALESCE(EXCLUDED.custom_name, user_saved_addresses.custom_name)
                RETURNING id
            """, user_id, provider, point_id, address_text, custom_name, is_default)

            return cast(int, address_id)

    async def get_addresses(self, user_id: int, provider: str | None = None) -> List[dict[str, Any]]:
        """Получает список адресов пользователя."""
        async with self._connection() as conn:
            if provider:
                provider = 'cdek' if 'cdek' in provider else 'yandex'
                rows = await conn.fetch("""
                    SELECT * FROM user_saved_addresses
                    WHERE user_id = $1 AND provider = $2
                    ORDER BY is_default DESC, created_at DESC
                """, user_id, provider)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM user_saved_addresses
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                """, user_id)
            return [dict[str, Any](row) for row in rows]

    async def get_default_address(self, user_id: int, provider: str) -> Optional[dict[str, Any]]:
        """Получает дефолтный адрес для конкретного провайдера."""
        provider = 'cdek' if 'cdek' in provider else 'yandex'
        async with self._connection() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM user_saved_addresses
                WHERE user_id = $1 AND provider = $2 AND is_default = TRUE
                LIMIT 1
            """, user_id, provider)
            return dict(row) if row else None

    async def set_default_address(self, user_id: int, address_id: int) -> Any:
        """Делает адрес дефолтным, снимая флаг с остальных адресов ТОГО ЖЕ провайдера."""
        async with self._connection() as conn:
            async with conn.transaction():
                # 1. узнаем провайдера этого адреса
                provider = await conn.fetchval("SELECT provider FROM user_saved_addresses WHERE id = $1", address_id)
                if not provider:
                    return

                # 2. снимаем дефолт со всех адресов этого юзера и провайдера
                await conn.execute("""
                    UPDATE user_saved_addresses
                    SET is_default = FALSE
                    WHERE user_id = $1 AND provider = $2
                """, user_id, provider)

                # 3. ставим дефолт нужному
                await conn.execute("UPDATE user_saved_addresses SET is_default = TRUE WHERE id = $1", address_id)

    async def delete_address(self, address_id: int, user_id: int) -> Any:
        """Удаляет адрес. Если он был дефолтным, пытается назначить новый дефолт."""
        async with self._connection() as conn:
            async with conn.transaction():
                # Проверяем, был ли он дефолтным и какой провайдер
                row = await conn.fetchrow("SELECT provider, is_default FROM user_saved_addresses WHERE id = $1 AND user_id = $2", address_id, user_id)
                if not row:
                    return

                provider, was_default = row['provider'], row['is_default']

                await conn.execute("DELETE FROM user_saved_addresses WHERE id = $1", address_id)

                if was_default:
                    # Назначаем самый свежий адрес новым дефолтным
                    await conn.execute("""
                        UPDATE user_saved_addresses
                        SET is_default = TRUE
                        WHERE id = (
                            SELECT id FROM user_saved_addresses
                            WHERE user_id = $1 AND provider = $2
                            ORDER BY created_at DESC LIMIT 1
                        )
                    """, user_id, provider)

    async def rename_address(self, address_id: int, user_id: int, new_name: str) -> Any:
        """Обновляет пользовательское название адреса."""
        async with self._connection() as conn:
            await conn.execute("""
                UPDATE user_saved_addresses
                SET custom_name = $1
                WHERE id = $2 AND user_id = $3
            """, new_name, address_id, user_id)
