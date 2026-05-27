# Tg_bot/bot_services/order_service.py
import logging
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from tg_bot.domain.order import Order, OrderItem, OrderStatus
from tg_bot.infrastructure.metrics import kojo_order_value_sum, kojo_orders_total
from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, pool: asyncpg.Pool, idempotency_store: Optional[Any] = None) -> None:
        self.pool = pool
        self._idempotency = idempotency_store
        logger.info("OrderService инициализирован.")

    def calculate_total_amount(self, cart: dict[str, dict[str, Any]], delivery_price: float = 0.0) -> float:
        """
        Calculate total order amount from cart items + delivery.
        :param cart: {product_id: {'quantity': int, 'price': float}}
        :param delivery_price: Delivery cost
        :return: Total amount (>=0, rounded to 2 decimal places)
        """
        total = 0.0
        for product_id, item_data in cart.items():
            quantity = item_data.get('quantity', 0)
            price = item_data.get('price', 0.0)
            total += quantity * price

        # Add Delivery (only If Positive)
        if delivery_price > 0:
            total += delivery_price

        # Ensure Non-negative And Round To 2 Decimal Places
        return round(max(0.0, total), 2)

    async def update_order_status(
        self, order_id: int, new_status: OrderStatus, idempotency_key: str = ""
    ) -> Optional[Order]:
        logger.info(f"Обновление статуса заказа #{order_id} на '{new_status.value}'.")

        # Idempotency Check
        if idempotency_key and self._idempotency:
            cached = await self._idempotency.check("order:status", idempotency_key)
            if cached:
                return None  # Already processed this exact status update
            await self._idempotency.start("order:status", idempotency_key)

        async with self.pool.acquire() as conn:
            # First, Get Current Order To Check State Transition Validity
            current_row = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1",
                order_id
            )

            if not current_row:
                return None

            # Validate State Transition
            current_status = OrderStatus(current_row['status'])
            Order.validate_transition(current_status, new_status)

            # If Valid, Proceed With Update
            updated_order_row = await conn.fetchrow(
                """
                UPDATE orders
                SET status = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING *
                """,
                new_status.value, order_id
            )

            if updated_order_row:
                # Idempotency Completion
                if idempotency_key and self._idempotency:
                    await self._idempotency.complete(
                        "order:status", idempotency_key,
                        {"status": "completed", "order_id": order_id}
                    )
                return Order.from_db_row(updated_order_row)
            return None

    async def cancel_order_with_reason(self, order_id: int, reason: str) -> Optional[Order]:
        """
        Отменяет заказ и записывает причину отмены.
        """
        logger.info(f"Отмена заказа #{order_id}. Причина: {reason}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE orders
                SET status = $1, cancellation_reason = $2, updated_at = NOW()
                WHERE id = $3
                RETURNING *
                """,
                OrderStatus.CANCELLED.value, reason, order_id
            )
            if row:
                return Order.from_db_row(row)
            return None

    async def set_payment_url(self, order_id: int, url: str) -> Any:
        """
        Сохраняет URL для оплаты и переводит заказ в статус 'Ожидает оплаты'.
        """
        logger.info(f"Сохранение URL оплаты для заказа #{order_id} -> AWAITING_PAYMENT.")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE orders
                SET payment_url = $1, status = $2
                WHERE id = $3
                """,
                url,
                OrderStatus.AWAITING_PAYMENT.value,
                order_id
            )


    async def get_orders_by_user_id(self, user_id: int) -> List[Order]:
        """Возвращает заказы, скрывая те, что были созданы до последней очистки данных."""
        async with self.pool.acquire() as conn:
            # Получаем дату очистки (если была)
            cleared_at = await conn.fetchval("SELECT data_cleared_at FROM users WHERE telegram_id = $1", user_id)

            if cleared_at:
                # Фильтруем: только заказы новее даты очистки
                rows = await conn.fetch(
                    "SELECT * FROM orders WHERE user_id = $1 AND created_at > $2 ORDER BY created_at DESC",
                    user_id, cleared_at
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC",
                    user_id
                )
            return [Order.from_db_row(row) for row in rows]


    async def get_full_order_details(self, order_id: int) -> Optional[Tuple[Order, List[OrderItem]]]:
        """Возвращает заказ и список товаров."""
        async with self.pool.acquire() as conn:
            order_row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
            if not order_row:
                return None

            items_rows = await conn.fetch("SELECT * FROM order_items WHERE order_id = $1", order_id)

            order = Order.from_db_row(order_row)
            items = [OrderItem(**dict(row)) for row in items_rows]

            return (order, items)

    async def get_last_active_order_for_user(self, user_id: int) -> Optional[Order]:
        """Ищет последний активный заказ (не завершен/отменен)."""
        active_statuses = [
            OrderStatus.ACCEPTED.value, OrderStatus.AWAITING_PAYMENT.value,
            OrderStatus.PAID.value, OrderStatus.ASSEMBLING.value,
            OrderStatus.READY_FOR_PICKUP.value, OrderStatus.SHIPPED.value,
        ]
        query = "SELECT * FROM orders WHERE user_id = $1 AND status = ANY($2) ORDER BY created_at DESC LIMIT 1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, active_statuses)
            return Order.from_db_row(row) if row else None

    async def get_orders_for_staff_view(self, statuses: List[OrderStatus]) -> List[dict[str, Any]]:
        """Агрегированные данные для списка заказов персонала."""
        status_values = [s.value for s in statuses]
        query = """
            SELECT
                o.id, o.total_amount, o.created_at,
                u.fio as user_fio,
                STRING_AGG(oi.quantity || ' x ' || p.name, ', ') as items_str
            FROM orders o
            JOIN users u ON o.user_id = u.telegram_id
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status = ANY($1)
            GROUP BY o.id, u.fio
            ORDER BY o.created_at ASC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, status_values)
            return [dict[str, Any](row) for row in rows]

    async def get_order_counts_by_status(self) -> Dict[OrderStatus, int]:
        """Статистика по статусам."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT status, COUNT(*) as count FROM orders GROUP BY status")
            # Преобразуем строковые статусы из бд в enum ключи
            # Будь внимателен: если в бд есть статусы, которых нет в enum, будет ошибка.
            result = {}
            for row in rows:
                try:
                    status_enum = OrderStatus(row['status'])
                    result[status_enum] = row['count']
                except ValueError:
                    continue
            return result

    async def get_orders_by_statuses(self, statuses: List[OrderStatus]) -> List[Order]:
        """Список заказов по конкретным статусам."""
        status_values = [s.value for s in statuses]
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE status = ANY($1) ORDER BY created_at DESC",
                status_values
            )
            return [Order.from_db_row(row) for row in rows]


    async def update_order_delivery(
        self,
        order_id: int,
        cart: dict[str, Any] | None = None,  # If provided, calculate total_amount from cart
        total_amount: float | None = None,  # None means calculate from cart
        delivery_type: str = 'pickup',
        delivery_address: str | None = None,
        delivery_price: float = 0.0,
        delivery_point_id: str | None = None,
        delivery_info: dict[str, Any] | None = None,
        is_gift: bool = False,
        gift_comment: str | None = None
    ) -> Order:
        # Calculate Total_amount From Cart If Not Provided
        if total_amount is None and cart is not None:
            total_amount = self.calculate_total_amount(cart, delivery_price)
        elif total_amount is None:
            # If Neither Cart Nor Total_amount Provided, Fetch From DB
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT total_amount FROM orders WHERE id = $1", order_id)
                total_amount = float(row['total_amount']) if row else 0.0

        logger.debug("update_order_delivery: order_id=%d, is_gift=%s", order_id, is_gift)
        logger.info(f"Обновление доставки для заказа #{order_id}. Новая сумма: {total_amount}")

        async with self.pool.acquire() as conn:
            # First Check If Order Is Already Paid (to Preserve Payment_url)
            order_status_row = await conn.fetchrow(
                "SELECT status FROM orders WHERE id = $1",
                order_id
            )
            order_status = order_status_row['status'] if order_status_row else None

            # Only Reset Payment_url If Order Is NOT Already Paid
            if order_status and order_status in ['Оплачен', 'Paid']:
                # Keep Existing Payment_url For Paid Orders
                row = await conn.fetchrow(
                    """
                    UPDATE orders
                    SET total_amount = $1,
                        delivery_type = $2,
                        delivery_address = $3,
                        delivery_price = $4,
                        delivery_point_id = $5,
                        delivery_info = $6,
                        is_gift = $7,
                        gift_comment = $8,
                        updated_at = NOW()
                    WHERE id = $9
                    RETURNING *
                    """,
                    total_amount,
                    delivery_type,
                    delivery_address,
                    delivery_price,
                    delivery_point_id,
                    delivery_info,
                    is_gift, gift_comment,
                    order_id
                )
            else:
                # Reset Payment_url For Unpaid Orders
                row = await conn.fetchrow(
                    """
                    UPDATE orders
                    SET total_amount = $1,
                        delivery_type = $2,
                        delivery_address = $3,
                        delivery_price = $4,
                        delivery_point_id = $5,
                        delivery_info = $6,
                        is_gift = $7,
                        gift_comment = $8,
                        payment_url = NULL,
                        updated_at = NOW()
                    WHERE id = $9
                    RETURNING *
                    """,
                    total_amount,
                    delivery_type,
                    delivery_address,
                    delivery_price,
                    delivery_point_id,
                    delivery_info,
                    is_gift, gift_comment,
                    order_id
                )

            if row:
                return Order.from_db_row(row)
            raise ValueError(f"Заказ {order_id} не найден для обновления.")


    async def update_order_comment(self, order_id: int, comment: str) -> Any:
        """
        Обновляет комментарий к заказу (использует поле gift_comment для хранения комментария пользователя).
        """
        logger.info(f"Обновление комментария к заказу #{order_id}")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE orders
                SET gift_comment = $1, updated_at = NOW()
                WHERE id = $2
                """,
                comment, order_id
            )
    async def _get_order_by_id(self, order_id: int) -> Optional[Order]:
        """Fetch a single order by ID from the database."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
            if row:
                return Order.from_db_row(row)
            return None

    async def create_order(
        self,
        user_id: int,
        cart: dict[str, Any],
        total_amount: float | None = None,  # None means calculate from cart
        delivery_type: str = 'pickup',
        delivery_address: str | None = None,
        delivery_price: float = 0.0,
        delivery_point_id: str | None = None,
        delivery_info: dict[str, Any] | None = None,
        is_gift: bool = False,
        gift_comment: str | None = None,
        idempotency_key: str = ""  # Unique key for idempotency
    ) -> Order:
        # Idempotency Check
        if idempotency_key and self._idempotency:
            cached = await self._idempotency.check("order:create", idempotency_key)
            if cached:
                if cached.get("status") == "completed":
                    # Return Existing Order From DB To Avoid Duplicate Creation
                    existing = await self._get_order_by_id(cached["order_id"])
                    if existing:
                        return existing
                raise ValueError("Duplicate request in progress")

            await self._idempotency.start("order:create", idempotency_key)

        # Calculate Total_amount From Cart If Not Provided
        if total_amount is None:
            total_amount = self.calculate_total_amount(cart, delivery_price)

        # Reject Zero Or Negative Totals
        if total_amount <= 0:
            raise ValueError("Сумма заказа должна быть больше 0")

        logger.debug("create_order: is_gift=%s, comment_len=%d", is_gift, len(gift_comment) if gift_comment else 0)
        logger.info(f"Creating order for {user_id}. Gift: {is_gift}")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                order_row = await conn.fetchrow(
                    """
                    INSERT INTO orders (
                        user_id, total_amount, status,
                        delivery_type, delivery_address, delivery_price,
                        delivery_point_id, delivery_info,
                        is_gift, gift_comment
                    )
                    VALUES ($1, $2, $3, $4, $5, $6,
                            $7, $8, $9, $10)
                    RETURNING *
                    """,
                    user_id, total_amount, OrderStatus.ACCEPTED.value,
                    delivery_type, delivery_address, delivery_price,
                    delivery_point_id, delivery_info,
                    is_gift, gift_comment
                )

                new_order = Order.from_db_row(order_row)

                # Record Metrics
                tid = get_current_tenant()
                tenant_id = tid.bot_id if tid else "default"
                kojo_orders_total.labels(status=new_order.status.value, tenant_id=tenant_id).inc()
                kojo_order_value_sum.observe(float(new_order.total_amount.amount))

                # Insert Items
                for product_id, item_data in cart.items():
                    await conn.execute(
                        """
                        INSERT INTO order_items (order_id, product_id, quantity, price)
                        VALUES ($1, $2, $3, $4)
                        """,
                        new_order.id, int(product_id), item_data['quantity'], float(item_data['price'])
                    )

                logger.info(f"Order #{new_order.id} successfully created (Gift: {is_gift})")

                # Idempotency Completion
                if idempotency_key and self._idempotency:
                    await self._idempotency.complete(
                        "order:create", idempotency_key,
                        {"status": "completed", "order_id": new_order.id}
                    )

                return new_order
