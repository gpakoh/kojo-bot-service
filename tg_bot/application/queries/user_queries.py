# Tg_bot/application/queries/user_queries.py
"""
Query Handlers For User Domain.
"""
from typing import Optional, cast

try:
    from typing import override
except ImportError:
    pass

import asyncpg

from tg_bot.application.queries.base import (
    PaginatedResult,
    PaginationParams,
    QueryHandler,
    ReadRepository,
)
from tg_bot.read_models.admin import UserDetailsView, UserListView, UsersMenuView


class UserReadRepository(ReadRepository):
    """Read-only repository for user queries."""

    async def get_users_paginated(
        self,
        status: Optional[str] = None,
        role: Optional[str] = None,
        search: Optional[str] = None,
        pagination: Optional[PaginationParams] = None
    ) -> PaginatedResult[UserListView]:
        """Get paginated user list with filters."""
        pagination = pagination or PaginationParams()

        conditions = []
        params = []

        if status:
            params.append(status)
            conditions.append(f"u.status = ${len(params)}")

        if role:
            params.append(role)
            conditions.append(f"u.role = ${len(params)}")

        if search:
            # Экранируем wildcard-символы postgresql, чтобы пользователь не мог ввести % или _ для матчинга всего
            safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{safe_search}%")
            params.append(f"%{safe_search}%")
            conditions.append(f"(u.fio ILIKE ${len(params)-1} OR u.telegram_id::text ILIKE ${len(params)})")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count Query
        count_sql = f"SELECT COUNT(*) FROM users u WHERE {where_clause}"
        total = await self.fetch_val(count_sql, *params)

        # Main Query
        params.append(str(pagination.page_size))
        params.append(str(pagination.offset))

        sql = f"""
            SELECT
                u.telegram_id as user_id,
                u.id as db_id,
                u.fio,
                u.status,
                u.role,
                u.created_at::text as registered_at
            FROM users u
            WHERE {where_clause}
            ORDER BY u.created_at DESC
            LIMIT ${len(params)-1} OFFSET ${len(params)}
        """

        rows = await self.fetch_all(sql, *params)

        items = [
            UserListView(
                user_id=cast(int, row['user_id']),
                db_id=cast(int, row['db_id']),
                fio=cast(str, row['fio']),
                status=cast(str, row['status']),
                role=cast(str, row['role']),
                registered_at=cast(str, row['registered_at']) if row['registered_at'] else "",
            )
            for row in rows
        ]

        return PaginatedResult(
            items=items,
            total=cast(int, total or 0),
            page=pagination.page,
            page_size=pagination.page_size
        )

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[UserDetailsView]:
        """Get full user details by telegram ID."""
        sql = """
            SELECT
                id as db_id,
                telegram_id,
                fio,
                phone,
                email,
                status,
                role,
                is_blocked,
                is_manager,
                is_admin,
                data_cleared_at
            FROM users
            WHERE telegram_id = $1
        """
        row = await self.fetch_one(sql, telegram_id)

        if not row:
            return None

        status_map = {
            'pending': 'На рассмотрении',
            'approved': 'Активен',
            'blocked': 'Заблокирован',
        }

        role_map = {
            'user': 'Пользователь',
            'manager': 'Менеджер',
            'admin': 'Админ',
        }

        return UserDetailsView(
            db_id=cast(int, row['db_id']),
            telegram_id=cast(int, row['telegram_id']),
            fio=cast(str, row['fio']) if row['fio'] else "—",
            phone=cast(str, row['phone']) if row['phone'] else "—",
            email=cast(str, row['email']) if row['email'] else "—",
            status_label=status_map.get(cast(str, row['status']), cast(str, row['status'])),
            role_label=role_map.get(cast(str, row['role']), cast(str, row['role'])),
            is_blocked=cast(bool, row['is_blocked']),
            is_manager=cast(bool, row['is_manager']),
            is_admin=cast(bool, row['is_admin']),
        )

    async def get_users_menu_counts(self) -> UsersMenuView:
        """Get aggregate counts for users menu."""
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
                COUNT(*) FILTER (WHERE status = 'blocked') as blocked_count,
                COUNT(*) FILTER (WHERE role = 'user') as user_count,
                COUNT(*) FILTER (WHERE role = 'manager') as manager_count,
                COUNT(*) FILTER (WHERE role = 'admin') as admin_count
            FROM users
        """
        row = await self.fetch_one(sql)

        if not row:
            return UsersMenuView(0, 0, 0, 0, 0, 0)

        return UsersMenuView(
            pending_count=cast(int, row['pending_count'] or 0),
            approved_count=cast(int, row['approved_count'] or 0),
            blocked_count=cast(int, row['blocked_count'] or 0),
            user_count=cast(int, row['user_count'] or 0),
            manager_count=cast(int, row['manager_count'] or 0),
            admin_count=cast(int, row['admin_count'] or 0),
        )


class GetUserListQuery(QueryHandler[PaginatedResult[UserListView]]):
    """Query: Get paginated user list."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = UserReadRepository(read_pool)

    async def execute(  # type: ignore[override]
        self,
        status: Optional[str] = None,
        role: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedResult[UserListView]:
        return await self._repo.get_users_paginated(
            status=status,
            role=role,
            search=search,
            pagination=PaginationParams(page=page, page_size=page_size)
        )


class GetUserDetailsQuery(QueryHandler[Optional[UserDetailsView]]):
    """Query: Get user details."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = UserReadRepository(read_pool)

    async def execute(self, *args: object, **kwargs: object) -> Optional[UserDetailsView]:
        telegram_id = cast(int, args[0] if args else kwargs.get('telegram_id'))
        return await self._repo.get_user_by_telegram_id(telegram_id)


class GetUsersMenuCountsQuery(QueryHandler[UsersMenuView]):
    """Query: Get users menu aggregate counts."""

    def __init__(self, read_pool: asyncpg.Pool) -> None:
        super().__init__(read_pool)
        self._repo = UserReadRepository(read_pool)

    async def execute(self, *args: object, **kwargs: object) -> UsersMenuView:
        return await self._repo.get_users_menu_counts()


__all__ = [
    'UserReadRepository',
    'GetUserListQuery',
    'GetUserDetailsQuery',
    'GetUsersMenuCountsQuery',
]
