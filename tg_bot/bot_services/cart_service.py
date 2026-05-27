# Tg_bot/bot_services/cart_service.py
import logging
from enum import Enum
from typing import Any, Dict

import asyncpg

logger = logging.getLogger(__name__)

class CartValidationResult(Enum):
    OK = "ok"
    CLEARED_OLD = "cleared_old" # Очищено из-за 24ч + изменения цены/наличия
    ITEM_UNAVAILABLE = "item_unavailable" # Позиция недоступна (нельзя купить)

class CartService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def update_item(self, user_id: int, product_id: int, quantity: int) -> Any:
        """
        Добавляет/обновляет товар и СОХРАНЯЕТ ТЕКУЩУЮ ЦЕНУ (snapshot).
        """
        # Мы используем подзапрос, чтобы взять актуальную цену из product_variants
        query = """
            INSERT INTO cart_items (user_id, product_id, quantity, saved_price, created_at)
            VALUES (
                $1, $2, $3,
                (SELECT price FROM product_variants WHERE product_id = $2 LIMIT 1),
                NOW()
            )
            ON CONFLICT (user_id, product_id)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                saved_price = (SELECT price FROM product_variants WHERE product_id = $2 LIMIT 1),
                created_at = NOW()
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, product_id, quantity)
            logger.info(f"User {user_id}: обновлен товар {product_id}, кол-во {quantity}")

    async def remove_item(self, user_id: int, product_id: int) -> Any:
        """Удаляет конкретный товар из корзины."""
        query = "DELETE FROM cart_items WHERE user_id = $1 AND product_id = $2"
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, product_id)

    async def clear_cart(self, user_id: int) -> Any:
        """Полная очистка корзины пользователя."""
        query = "DELETE FROM cart_items WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id)
            logger.info(f"User {user_id}: корзина очищена")

    async def get_cart(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает корзину в формате, совместимом со старой логикой:
        { 'product_id_str': {'quantity': int, 'price': float} }
        Берет актуальную цену из таблицы product_variants (первый вариант).
        """
        # Мы джойним variants, чтобы сразу получить актуальную цену.
        # Distinct on (ci.product_id) берет первый попавшийся вариант цены (обычно он один или основной).
        query = """
            SELECT DISTINCT ON (ci.product_id)
                ci.product_id,
                ci.quantity,
                pv.price
            FROM cart_items ci
            JOIN product_variants pv ON ci.product_id = pv.product_id
            WHERE ci.user_id = $1
            ORDER BY ci.product_id, pv.price ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)

        cart = {}
        for row in rows:
            # Преобразуем в структуру, которую ожидают хендлеры
            cart[str(row['product_id'])] = {
                'quantity': row['quantity'],
                'price': float(row['price'])
            }

        return cart

    async def is_cart_empty(self, user_id: int) -> bool:
        query = "SELECT EXISTS(SELECT 1 FROM cart_items WHERE user_id = $1)"
        async with self.pool.acquire() as conn:
            return not await conn.fetchval(query, user_id)


    async def validate_cart(self, user_id: int) -> tuple[CartValidationResult, str | None]:
        """
        Проверяет корзину на соответствие правилам:
        1. Если товар лежит > 24ч И (цена изменилась ИЛИ availability=False) -> Очистить всё.
        2. Если просто availability=False (даже если < 24ч) -> Запретить покупку.

        Возвращает: (Статус, Сообщение для пользователя)
        """
        query = """
            SELECT
                ci.product_id,
                ci.saved_price,
                ci.created_at,
                p.name,
                p.is_available,
                pv.price as current_price
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            LEFT JOIN product_variants pv ON ci.product_id = pv.product_id
            WHERE ci.user_id = $1
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)

        if not rows:
            return CartValidationResult.OK, None

        stale_items = []
        for row in rows:
            # Данные из строки
            created_at = row['created_at']
            saved_price = float(row['saved_price'] or 0)
            current_price = float(row['current_price'] or 0)
            is_available = row['is_available']
            product_name = row['name']

            # Проверка времени (postgres возвращает datetime с таймзоной)
            import datetime
            now = datetime.datetime.now(created_at.tzinfo)
            age = now - created_at
            is_older_than_24h = age.total_seconds() > 24 * 3600

            # Правило 1: больше 24 часов + изменения
            if is_older_than_24h:
                price_changed = abs(saved_price - current_price) > 0.01
                # Если цена изменилась или товара нет в наличии
                if price_changed or not is_available:
                    stale_items.append(product_name)

        # Если есть устаревшие товары с изменениями - очищаем всё
        if stale_items:
            await self.clear_cart(user_id)
            items_str = ", ".join(stale_items[:3])  # Показываем первые 3
            if len(stale_items) > 3:
                items_str += f" и ещё {len(stale_items) - 3} товаров"
            return CartValidationResult.CLEARED_OLD, f"⚠️ Ваша корзина была автоматически очищена, так как товары находились в ней более 24 часов и произошли изменения (цены или наличия): {items_str}. Пожалуйста, соберите заказ заново."  # noqa: E501

        # Check For Unavailable Items (rule 2)
        for row in rows:
            if not row['is_available']:
                product_name = row['name']
                return CartValidationResult.ITEM_UNAVAILABLE, f"⚠️ Позиция «{product_name}» к сожалению, больше нет в наличии. Мы приносим свои извинения. Пожалуйста, удалите её из корзины."  # noqa: E501

        return CartValidationResult.OK, None

