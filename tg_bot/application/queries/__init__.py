# Tg_bot/application/queries/__init__.py
"""
CQRS Query Handlers.

Usage:
    from tg_bot.application.queries import GetUserListQuery, GetOrderStatisticsQuery

    query = GetUserListQuery(read_pool)
    result = await query.execute(page=1, page_size=20)
"""
from tg_bot.application.queries.base import (
    PaginatedResult,
    PaginationParams,
    QueryHandler,
    ReadRepository,
)
from tg_bot.application.queries.order_queries import (
    GetOrderDetailsQuery,
    GetOrderListQuery,
    GetOrdersMenuCountsQuery,
    GetOrderStatisticsQuery,
    OrderReadRepository,
)
from tg_bot.application.queries.user_queries import (
    GetUserDetailsQuery,
    GetUserListQuery,
    GetUsersMenuCountsQuery,
    UserReadRepository,
)

__all__ = [
    # Base
    'QueryHandler',
    'ReadRepository',
    'PaginationParams',
    'PaginatedResult',
    # User Queries
    'UserReadRepository',
    'GetUserListQuery',
    'GetUserDetailsQuery',
    'GetUsersMenuCountsQuery',
    # Order Queries
    'OrderReadRepository',
    'GetOrderListQuery',
    'GetOrderDetailsQuery',
    'GetOrdersMenuCountsQuery',
    'GetOrderStatisticsQuery',
]
