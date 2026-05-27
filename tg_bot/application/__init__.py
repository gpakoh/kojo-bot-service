# Tg_bot/application/__init__.py
"""
Application Layer - CQRS Pattern Implementation.

Commands: tg_bot/application/commands/
Queries: tg_bot/application/queries/
"""
from tg_bot.application.queries import (
    GetOrderDetailsQuery,
    GetOrderListQuery,
    GetOrdersMenuCountsQuery,
    GetOrderStatisticsQuery,
    GetUserDetailsQuery,
    GetUserListQuery,
    GetUsersMenuCountsQuery,
    PaginatedResult,
    PaginationParams,
    QueryHandler,
    ReadRepository,
)

__all__ = [
    'QueryHandler',
    'ReadRepository',
    'PaginationParams',
    'PaginatedResult',
    'GetUserListQuery',
    'GetUserDetailsQuery',
    'GetUsersMenuCountsQuery',
    'GetOrderListQuery',
    'GetOrderDetailsQuery',
    'GetOrdersMenuCountsQuery',
    'GetOrderStatisticsQuery',
]
