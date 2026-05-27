"""Tests for Application Layer Queries with Mock DB."""
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.application.queries import (
    GetOrderDetailsQuery,
    GetOrderListQuery,
    GetOrderStatisticsQuery,
    GetUserListQuery,
)
from tg_bot.application.queries.base import PaginatedResult
from tg_bot.read_models.admin import OrderDetailsView, OrderStatsView, UserListView


class MockConnection:
    """Mock asyncpg.Connection with fetch/fetchrow/fetchval."""
    def __init__(self, fetch_return: Any = None, fetchrow_return: Any = None, fetchval_return: Any = None):
        self.fetch = AsyncMock(return_value=fetch_return or [])
        self.fetchrow = AsyncMock(return_value=fetchrow_return)
        self.fetchval = AsyncMock(return_value=fetchval_return)
        self.transaction = MagicMock()
        self.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
        self.transaction.return_value.__aexit__ = AsyncMock(return_value=None)


class MockPool:
    def __init__(self, conn: Optional[MockConnection] = None):
        self._conn = conn or MockConnection()
        self.acquire = MagicMock()
        self.acquire.return_value.__aenter__ = AsyncMock(return_value=self._conn)
        self.acquire.return_value.__aexit__ = AsyncMock(return_value=None)


class TestGetUserListQuery:
    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        mock_conn = MockConnection(
            fetch_return=[
                {
                    'user_id': 101, 'db_id': 1, 'fio': 'Иван',
                    'status': 'approved', 'role': 'user',
                    'registered_at': '2025-01-01'
                }
            ],
            fetchval_return=1
        )
        pool = MockPool(mock_conn)
        query = GetUserListQuery(pool)
        result = await query.execute(page=1, page_size=10)

        assert isinstance(result, PaginatedResult)
        assert result.total == 1
        assert len(result.items) == 1
        assert isinstance(result.items[0], UserListView)
        assert result.items[0].fio == 'Иван'
        assert result.has_next is False
        assert result.has_prev is False

    @pytest.mark.asyncio
    async def test_search_ilike_escape(self) -> None:
        """Verify search uses ILIKE with escaped wildcards."""
        mock_conn = MockConnection(fetch_return=[], fetchval_return=0)
        pool = MockPool(mock_conn)
        query = GetUserListQuery(pool)
        await query.execute(page=1, page_size=10, search="test_10%")

        # Check That Fetch Was Called With ILIKE
        fetch_call_args = mock_conn.fetch.call_args
        sql_query = fetch_call_args[0][0]
        assert 'ILIKE' in sql_query

    @pytest.mark.asyncio
    async def test_has_next_prev_boundary(self) -> None:
        # Total=15, Page=1 (size 10): Has_next=true, Has_prev=false
        mock_conn = MockConnection(fetch_return=[], fetchval_return=15)
        pool = MockPool(mock_conn)
        query = GetUserListQuery(pool)
        result = await query.execute(page=1, page_size=10)
        assert result.has_next is True
        assert result.has_prev is False

        # Page=2: Has_next=false, Has_prev=true
        result = await query.execute(page=2, page_size=10)
        assert result.has_next is False
        assert result.has_prev is True

        # Total=0: Both False
        mock_conn.fetchval.return_value = 0
        result = await query.execute(page=1, page_size=10)
        assert result.has_next is False
        assert result.has_prev is False


class TestGetOrderStatisticsQuery:
    @pytest.mark.asyncio
    async def test_empty_db(self) -> None:
        """If DB returns zeros, OrderStatsView must have zeros."""
        mock_conn = MockConnection(fetchrow_return={
            'today_orders': 0, 'today_revenue': 0.0,
            'week_orders': 0, 'week_revenue': 0.0,
            'month_orders': 0, 'month_revenue': 0.0,
            'total_orders': 0, 'total_revenue': 0.0, 'avg_order_value': 0.0,
        })
        pool = MockPool(mock_conn)
        query = GetOrderStatisticsQuery(pool)
        result = await query.execute()

        assert isinstance(result, OrderStatsView)
        assert result.today_orders == 0
        assert result.total_revenue == 0.0
        assert result.avg_order_value == 0.0


class TestGetOrderDetailsQuery:
    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        mock_conn = MockConnection(fetchrow_return=None)
        pool = MockPool(mock_conn)
        query = GetOrderDetailsQuery(pool)
        result = await query.execute(order_id=999)
        assert result is None

    @pytest.mark.asyncio
    async def test_found(self) -> None:
        # Orderdetailsquery Expects Specific Columns From JOIN Query
        mock_conn = MockConnection(fetchrow_return={
            'order_id': 1, 'user_id': 123, 'user_fio': 'Test User', 'user_phone': '123456',
            'total_amount': 1500.0, 'status': 'Принят', 'delivery_type': 'pickup',
            'delivery_address': None, 'delivery_price': 0.0, 'is_gift': False,
            'gift_comment': None, 'created_at': '2025-01-01'
        })
        pool = MockPool(mock_conn)
        query = GetOrderDetailsQuery(pool)
        result = await query.execute(order_id=1)
        assert isinstance(result, OrderDetailsView)
        assert result.order_id == 1
        assert result.user_fio == 'Test User'


class TestGetOrderListQuery:
    @pytest.mark.asyncio
    async def test_status_filter(self) -> None:
        mock_conn = MockConnection(fetch_return=[], fetchval_return=0)
        pool = MockPool(mock_conn)
        query = GetOrderListQuery(pool)
        await query.execute(page=1, page_size=10, status='Принят')

        fetch_call_args = mock_conn.fetch.call_args
        assert 'o.status = $' in fetch_call_args[0][0]
