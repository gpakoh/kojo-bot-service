# Tg_bot/infrastructure/repositories/postgres_order_repository.py
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from tg_bot.domain.order import Money, Order, OrderItem, OrderStatus
from tg_bot.domain.order_repository import OrderRepository

logger = logging.getLogger(__name__)


class PostgresOrderRepository(OrderRepository):
    """
    PostgreSQL implementation of OrderRepository.
    Handles all database operations for orders.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        logger.info("Postgresorderrepository Initialized.")

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    async def _get_order_for_update(self, conn: asyncpg.Connection, order_id: int) -> Optional[asyncpg.Record]:
        """Lock order row for update to prevent race conditions."""
        return await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1 FOR UPDATE",
            order_id
        )

    async def create(self, order: Order) -> Order:
        """Create a new order with items."""
        delivery = order.delivery
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
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING *
                    """,
                    order.user_id,
                    order.total_amount.amount,
                    order.status.value,
                    delivery.delivery_type if delivery else None,
                    delivery.address if delivery else None,
                    order.delivery_price.amount if order.delivery_price else 0.0,
                    delivery.point_id if delivery else None,
                    delivery.info if delivery else None,
                    order.is_gift,
                    order.gift_comment,
                )

                order.id = order_row['id']
                order.created_at = order_row['created_at']
                order.updated_at = order_row['updated_at']

                for item in order.items:
                    await conn.execute(
                        """
                        INSERT INTO order_items (order_id, product_id, quantity, price, name)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        order.id, item.product_id, item.quantity, item.price.amount, item.name
                    )

                logger.info(f"Order #{order.id} created via repository.")
                return order

    async def get_by_id(self, order_id: int) -> Optional[Order]:
        """Get order by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
            return Order.from_db_row(dict(row)) if row else None

    async def get_by_id_with_items(self, order_id: int) -> Optional[Tuple[Order, List[OrderItem]]]:
        """Get order with its items."""
        async with self.pool.acquire() as conn:
            order_row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
            if not order_row:
                return None

            items_rows = await conn.fetch("SELECT * FROM order_items WHERE order_id = $1", order_id)

            order = Order.from_db_row(dict(order_row))
            items = [
                OrderItem(
                    product_id=row['product_id'],
                    quantity=row['quantity'],
                    price=Money(row['price']),
                    name=row.get('name', '')
                )
                for row in items_rows
            ]

            return (order, items)

    async def get_by_user_id(self, user_id: int) -> List[Order]:
        """Get all orders for a user."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC",
                user_id
            )
            return [Order.from_db_row(dict(row)) for row in rows]

    async def get_by_user_id_with_clear_check(self, user_id: int, cleared_at: Optional[datetime] = None) -> List[Order]:
        """Get orders for user, filtering by clear timestamp if provided."""
        if cleared_at:
            return await self.get_by_user_id_after_timestamp(user_id, cleared_at)
        else:
            return await self.get_by_user_id(user_id)

    async def get_by_user_id_after_timestamp(self, user_id: int, timestamp: datetime) -> List[Order]:
        """Get orders for user created after timestamp."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE user_id = $1 AND created_at > $2 ORDER BY created_at DESC",
                user_id, timestamp
            )
            return [Order.from_db_row(dict(row)) for row in rows]

    async def update_status(self, order_id: int, new_status: OrderStatus) -> Optional[Order]:
        """Update order status."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current_order_row = await self._get_order_for_update(conn, order_id)
                if not current_order_row:
                    return None

                row = await conn.fetchrow(
                    """
                    UPDATE orders
                    SET status = $1, updated_at = NOW()
                    WHERE id = $2
                    RETURNING *
                    """,
                    new_status.value, order_id
                )
                return Order.from_db_row(dict(row)) if row else None

    async def cancel(self, order_id: int, reason: str) -> Optional[Order]:
        """Cancel order with reason."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current_order_row = await self._get_order_for_update(conn, order_id)
                if not current_order_row:
                    return None

                row = await conn.fetchrow(
                    """
                    UPDATE orders
                    SET status = $1, cancellation_reason = $2, updated_at = NOW()
                    WHERE id = $3
                    RETURNING *
                    """,
                    OrderStatus.CANCELLED.value, reason, order_id
                )
                return Order.from_db_row(dict(row)) if row else None

    async def update_delivery(
        self,
        order_id: int,
        total_amount: float,
        delivery_type: str,
        delivery_address: str,
        delivery_price: float,
        delivery_point_id: str,
        delivery_info: dict[str, Any],
        is_gift: bool,
        gift_comment: str,
    ) -> Optional[Order]:
        """Update order delivery info."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current_order_row = await self._get_order_for_update(conn, order_id)
                if not current_order_row:
                    return None

                current_status = OrderStatus(current_order_row['status'])

                if current_status == OrderStatus.PAID:
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
                        total_amount, delivery_type, delivery_address, delivery_price,
                        delivery_point_id, delivery_info, is_gift, gift_comment, order_id
                    )
                else:
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
                        total_amount, delivery_type, delivery_address, delivery_price,
                        delivery_point_id, delivery_info, is_gift, gift_comment, order_id
                    )

                return Order.from_db_row(dict(row)) if row else None

    async def update_comment(self, order_id: int, comment: str) -> None:
        """Update order comment."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE orders
                SET gift_comment = $1, updated_at = NOW()
                WHERE id = $2
                """,
                comment, order_id
            )

    async def set_payment_url(self, order_id: int, url: str) -> None:
        """Set payment URL and update status."""
        async with self._pool.acquire() as conn:
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

    async def get_by_statuses(self, statuses: List[OrderStatus]) -> List[Order]:
        """Get orders by statuses."""
        status_values = [s.value for s in statuses]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE status = ANY($1) ORDER BY created_at DESC",
                status_values
            )
            return [Order.from_db_row(dict(row)) for row in rows]

    async def get_last_active_for_user(self, user_id: int) -> Optional[Order]:
        """Get last active (non-completed) order for user."""
        active_statuses = [
            OrderStatus.ACCEPTED.value,
            OrderStatus.AWAITING_PAYMENT.value,
            OrderStatus.PAID.value,
            OrderStatus.ASSEMBLING.value,
            OrderStatus.READY_FOR_PICKUP.value,
            OrderStatus.SHIPPED.value,
        ]
        query = "SELECT * FROM orders WHERE user_id = $1 AND status = ANY($2) ORDER BY created_at DESC LIMIT 1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, active_statuses)
            return Order.from_db_row(dict(row)) if row else None

    async def get_staff_view_orders(self, statuses: List[OrderStatus]) -> List[dict[str, Any]]:
        """Get aggregated staff view data."""
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
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, status_values)
            return [dict[str, Any](row) for row in rows]

    async def get_counts_by_status(self) -> Dict[OrderStatus, int]:
        """Get order counts grouped by status."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT status, COUNT(*) as count FROM orders GROUP BY status")
            result = {}
            for row in rows:
                try:
                    status_enum = OrderStatus(row['status'])
                    result[status_enum] = row['count']
                except ValueError:
                    continue
            return result


__all__ = ['PostgresOrderRepository']
