# Tg_bot/application/queries/order_queries.py
"""
Query Handlers For Order Domain.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, cast

import asyncpg

from tg_bot.application.queries.base import (
    PaginatedResult,
    PaginationParams,
    QueryHandler,
    ReadRepository,
)
from tg_bot.read_models.admin import OrderDetailsView, OrderListView, OrdersMenuView, OrderStatsView


class OrderReadRepository(ReadRepository):
    """Read-only repository for order queries."""

    async def get_orders_paginated(
        self,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        pagination: Optional[PaginationParams] = None
    ) -> PaginatedResult[OrderListView]:
        """Get paginated order list."""
        pagination = pagination or PaginationParams()

        conditions = []
        params: list[str | int] = []

        if status:
            params.append(status)
            conditions.append(f"o.status = ${len(params)}")

        if user_id:
            params.append(user_id)
            conditions.append(f"o.user_id = ${len(params)}")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count
        count_sql = f"SELECT COUNT(*) FROM orders o WHERE {where_clause}"
        total = cast(int, await self.fetch_val(count_sql, *params))

        # Main Query
        params.append(pagination.page_size)
        params.append(pagination.offset)

        sql = f"""
            SELECT
                o.id as order_id,
                u.fio as user_fio,
                o.total_amount,
                o.status,
                o.created_at,
                COUNT(oi.id) as item_count
            FROM orders o
            JOIN users u ON o.user_id = u.telegram_id
            LEFT JOIN order_items oi ON o.id = oi.order_id
            WHERE {where_clause}
            GROUP BY o.id, u.fio
            ORDER BY o.created_at DESC
            LIMIT ${len(params)-1} OFFSET ${len(params)}
        """

        rows = await self.fetch_all(sql, *params)

        items = [
            OrderListView(
                order_id=cast(int, row['order_id']),
                user_fio=cast(str, row['user_fio'] or "—"),
                total_amount=cast(float, row['total_amount'] or 0),
                status=cast(str, row['status']),
                created_at=str(row['created_at']) if row['created_at'] else "",
                item_count=cast(int, row['item_count'] or 0),
            )
            for row in rows
        ]

        return PaginatedResult(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size
        )

    async def get_order_details(self, order_id: int) -> Optional[OrderDetailsView]:
        """Get full order details."""
        sql = """
            SELECT
                o.id as order_id,
                o.user_id,
                u.fio as user_fio,
                u.phone as user_phone,
                o.total_amount,
                o.status,
                o.delivery_type,
                o.delivery_address,
                o.created_at,
                o.updated_at,
                o.is_gift,
                o.gift_comment,
                o.cancellation_reason
            FROM orders o
            JOIN users u ON o.user_id = u.telegram_id
            WHERE o.id = $1
        """
        row = await self.fetch_one(sql, order_id)

        if not row:
            return None

        items_sql = """
            SELECT product_id, quantity, price, name
            FROM order_items
            WHERE order_id = $1
        """
        items_rows = await self.fetch_all(items_sql, order_id)

        items = [
            {
                'product_id': cast(int, r['product_id']),
                'quantity': cast(int, r['quantity']),
                'price': cast(float, r['price']),
                'name': cast(str, r['name']),
            }
            for r in items_rows
        ]

        return OrderDetailsView(
            order_id=cast(int, row['order_id']),
            user_id=cast(int, row['user_id']),
            user_fio=cast(str, row['user_fio'] or "—"),
            user_phone=cast(str, row['user_phone'] or "—"),
            total_amount=cast(float, row['total_amount'] or 0),
            status=cast(str, row['status']),
            status_label=cast(str, row['status']),
            payment_url=None,
            delivery_type=cast(str, row['delivery_type']),
            delivery_address=cast(Optional[str], row['delivery_address'] or "—"),
            delivery_price=cast(float, row.get('delivery_price', 0) or 0),
            items=items,  # type: ignore[arg-type]
            is_gift=cast(bool, row.get('is_gift', False)) or False,
            gift_comment=cast(Optional[str], row.get('gift_comment')),
        )

    async def get_orders_menu_counts(self) -> OrdersMenuView:
        """Get aggregate counts for orders menu."""
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE status = 'Принят') as new_count,
                COUNT(*) FILTER (WHERE status = 'Ожидает оплаты') as payment_pending_count,
                COUNT(*) FILTER (WHERE status = 'Оплачен') as paid_count,
                COUNT(*) FILTER (WHERE status = 'Комплектуется') as assembling_count,
                COUNT(*) FILTER (WHERE status = 'Готов к выдаче') as ready_count,
                COUNT(*) FILTER (WHERE status = 'Передан в доставку') as shipped_count,
                COUNT(*) FILTER (WHERE status = 'Завершён') as completed_count,
                COUNT(*) FILTER (WHERE status = 'Отменён') as cancelled_count
            FROM orders
            WHERE created_at > NOW() - INTERVAL '30 days'
        """
        row = await self.fetch_one(sql)

        if not row:
            return OrdersMenuView(counts={"new_count": 0, "payment_pending_count": 0, "paid_count": 0, "assembling_count": 0, "ready_count": 0, "shipped_count": 0, "completed_count": 0, "cancelled_count": 0})

        return OrdersMenuView(
            counts=dict(row) if row else {"new_count": 0, "payment_pending_count": 0, "paid_count": 0, "assembling_count": 0, "ready_count": 0, "shipped_count": 0, "completed_count": 0, "cancelled_count": 0},
        )

    async def get_order_statistics(self) -> OrderStatsView:
        """Get order statistics (for materialized view optimization)."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sql = """
            SELECT
                -- Today
                COUNT(*) FILTER (WHERE created_at >= $1) as today_orders,
                COALESCE(SUM(total_amount) FILTER (WHERE created_at >= $1), 0) as today_revenue,

                -- This week
                COUNT(*) FILTER (WHERE created_at >= $2) as week_orders,
                COALESCE(SUM(total_amount) FILTER (WHERE created_at >= $2), 0) as week_revenue,

                -- This month
                COUNT(*) FILTER (WHERE created_at >= $3) as month_orders,
                COALESCE(SUM(total_amount) FILTER (WHERE created_at >= $3), 0) as month_revenue,

                -- All time
                COUNT(*) as total_orders,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COALESCE(AVG(total_amount), 0) as avg_order_value
            FROM orders
            WHERE status NOT IN ('Отменён')
        """
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)

        row = await self.fetch_one(sql, today_start, week_start, month_start)

        if not row:
            return OrderStatsView(0, 0, 0, 0, 0, 0, 0, 0, 0)

        return OrderStatsView(
            today_orders=cast(int, row['today_orders'] or 0),
            today_revenue=float(cast(float, row['today_revenue'] or 0)),
            week_orders=cast(int, row['week_orders'] or 0),
            week_revenue=float(cast(float, row['week_revenue'] or 0)),
            month_orders=cast(int, row['month_orders'] or 0),
            month_revenue=float(cast(float, row['month_revenue'] or 0)),
            total_orders=cast(int, row['total_orders'] or 0),
            total_revenue=float(cast(float, row['total_revenue'] or 0)),
            avg_order_value=float(cast(float, row['avg_order_value'] or 0)),
        )


class GetOrderListQuery(QueryHandler[PaginatedResult[OrderListView]]):
    """Query: Get paginated order list."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = OrderReadRepository(read_pool)

    async def execute(  # type: ignore[override]
        self,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedResult[OrderListView]:
        return await self._repo.get_orders_paginated(
            status=status,
            user_id=user_id,
            pagination=PaginationParams(page=page, page_size=page_size)
        )


class GetOrderDetailsQuery(QueryHandler[Optional[OrderDetailsView]]):
    """Query: Get order details."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = OrderReadRepository(read_pool)

    async def execute(self, order_id: int) -> Optional[OrderDetailsView]:  # type: ignore[override]
        return await self._repo.get_order_details(order_id)


class GetOrdersMenuCountsQuery(QueryHandler[OrdersMenuView]):
    """Query: Get orders menu aggregate counts."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = OrderReadRepository(read_pool)

    async def execute(self) -> OrdersMenuView:  # type: ignore[override]
        return await self._repo.get_orders_menu_counts()


class GetOrderStatisticsQuery(QueryHandler[OrderStatsView]):
    """Query: Get order statistics."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = OrderReadRepository(read_pool)

    async def execute(self) -> OrderStatsView:  # type: ignore[override]
        return await self._repo.get_order_statistics()



__all__ = [
    'OrderReadRepository',
    'GetOrderListQuery',
    'GetOrderDetailsQuery',
    'GetOrdersMenuCountsQuery',
    'GetOrderStatisticsQuery',
]
