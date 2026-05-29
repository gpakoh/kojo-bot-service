# Tg_bot/bot_services/favorite_service.py
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, cast

import asyncpg

from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)

class FavoriteService:
    def __init__(self, pool: asyncpg.Pool, db_manager: Any = None) -> None:
        self.pool = pool
        self.db_manager = db_manager

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
        """Создает таблицу избранного."""
        async with self._connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_favorites (
                    user_id BIGINT NOT NULL,
                    product_id INT NOT NULL,
                    notify_on_restock BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (user_id, product_id)
                );
                CREATE INDEX IF NOT EXISTS idx_fav_user ON user_favorites(user_id);
            """)

    async def add_favorite(self, user_id: int, product_id: int) -> Any:
        """Добавляет товар в избранное."""
        async with self._connection() as conn:
            await conn.execute("""
                INSERT INTO user_favorites (user_id, product_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
            """, user_id, product_id)

    async def remove_favorite(self, user_id: int, product_id: int) -> Any:
        """Удаляет товар из избранного."""
        async with self._connection() as conn:
            await conn.execute("""
                DELETE FROM user_favorites
                WHERE user_id = $1 AND product_id = $2
            """, user_id, product_id)

    async def toggle_favorite(self, user_id: int, product_id: int) -> bool:
        """
        Переключает состояние.
        Возвращает True, если добавлено, False, если удалено.
        """
        is_fav = await self.is_favorite(user_id, product_id)
        if is_fav:
            await self.remove_favorite(user_id, product_id)
            return False
        else:
            await self.add_favorite(user_id, product_id)
            return True

    async def is_favorite(self, user_id: int, product_id: int) -> bool:
        """Проверяет, находится ли товар в избранном."""
        async with self._connection() as conn:
            res = await conn.fetchval("""
                SELECT 1 FROM user_favorites
                WHERE user_id = $1 AND product_id = $2
            """, user_id, product_id)
            return bool(res)

    async def get_user_favorites(self, user_id: int) -> List[int]:
        """Возвращает список ID товаров в избранном."""
        async with self._connection() as conn:
            rows = await conn.fetch("""
                SELECT product_id FROM user_favorites
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)
            return [r['product_id'] for r in rows]

    async def get_favorites_count(self, user_id: int) -> int:
        """Возвращает количество товаров в избранном."""
        async with self._connection() as conn:
            return cast(int, await conn.fetchval("SELECT COUNT(*) FROM user_favorites WHERE user_id = $1", user_id))

    async def set_notification(self, user_id: int, product_id: int, notify: bool) -> Any:
        """Включает/выключает уведомление о поступлении."""
        async with self._connection() as conn:
            await conn.execute("""
                UPDATE user_favorites
                SET notify_on_restock = $1
                WHERE user_id = $2 AND product_id = $3
            """, notify, user_id, product_id)

    async def get_notification_status(self, user_id: int, product_id: int) -> bool:
        async with self._connection() as conn:
            return await conn.fetchval("""
                SELECT notify_on_restock FROM user_favorites
                WHERE user_id = $1 AND product_id = $2
            """, user_id, product_id) or False

    async def get_pending_notifications(self) -> List[dict[str, Any]]:
        """
        Возвращает список уведомлений, которые нужно отправить.
        Выбирает только те товары, которые ЕСТЬ в наличии (p.is_available = True)
        и на которые пользователь подписан (f.notify_on_restock = True).
        """
        async with self._connection() as conn:
            # Join позволяет нам сразу проверить наличие товара в таблице products
            rows = await conn.fetch("""
                SELECT
                    f.user_id,
                    f.product_id,
                    p.name as product_name
                FROM user_favorites f
                JOIN products p ON f.product_id = p.id
                WHERE f.notify_on_restock = TRUE
                  AND p.is_available = TRUE
            """)
            return [dict[str, Any](row) for row in rows]

    async def disable_notification(self, user_id: int, product_id: int) -> Any:
        """Отключает уведомление после успешной отправки."""
        async with self._connection() as conn:
            await conn.execute("""
                UPDATE user_favorites
                SET notify_on_restock = FALSE
                WHERE user_id = $1 AND product_id = $2
            """, user_id, product_id)

    async def save_recipe(self, user_id: int, product_id: int, text: str) -> Any:
        """Сохраняет текст рецепта для пользователя."""
        logger.info(f"Saving recipe for user {user_id}, product {product_id}")
        async with self._connection() as conn:
            await conn.execute("""
                INSERT INTO user_favorite_recipes (user_id, product_id, recipe_text)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, product_id) DO UPDATE SET recipe_text = EXCLUDED.recipe_text
            """, user_id, product_id, text)

    async def get_saved_recipes(self, user_id: int) -> List[dict[str, Any]]:
        """Получает все сохраненные рецепты с названиями товаров."""
        async with self._connection() as conn:
            rows = await conn.fetch("""
                SELECT r.*, p.name as product_name
                FROM user_favorite_recipes r
                JOIN products p ON r.product_id = p.id
                WHERE r.user_id = $1
                ORDER BY r.created_at DESC
            """, user_id)
            return [dict[str, Any](r) for r in rows]

    async def delete_recipe(self, user_id: int, product_id: int) -> Any:
        """Удаляет рецепт."""
        async with self._connection() as conn:
            await conn.execute("DELETE FROM user_favorite_recipes WHERE user_id = $1 AND product_id = $2", user_id, product_id)

    async def is_recipe_saved(self, user_id: int, product_id: int) -> bool:
        """Проверяет, сохранен ли уже этот рецепт."""
        async with self._connection() as conn:
            res = await conn.fetchval("SELECT 1 FROM user_favorite_recipes WHERE user_id = $1 AND product_id = $2", user_id, product_id)
            return bool(res)

    async def has_any_favorites(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя хотя бы один товар или рецепт в избранном."""
        async with self._connection() as conn:
            # Используем exists для максимальной скорости (нам не нужно считать всё)
            res = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM user_favorites WHERE user_id = $1
                    UNION ALL
                    SELECT 1 FROM user_favorite_recipes WHERE user_id = $1
                )
            """, user_id)
            return bool(res)
