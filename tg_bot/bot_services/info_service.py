# Tg_bot/bot_services/info_service.py
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, cast

import asyncpg

from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)

class InfoService:
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

    async def get_page(self, page_id: int) -> Optional[Dict[str, Any]]:
        async with self._connection() as conn:
            return cast(dict[str, Any] | None, await conn.fetchrow("SELECT * FROM info_pages WHERE id = $1", page_id))

    async def get_children(self, parent_id: Optional[int]) -> List[Dict[str, Any]]:
        async with self._connection() as conn:
            if parent_id is None:
                return cast(list[dict[str, Any]], await conn.fetch("SELECT * FROM info_pages WHERE parent_id IS NULL ORDER BY sort_order, title"))
            else:
                return cast(list[dict[str, Any]], await conn.fetch("SELECT * FROM info_pages WHERE parent_id = $1 ORDER BY sort_order, title", parent_id))

    async def create_page(
        self, parent_id: Optional[int], title: str,
        text: str | None = None, image_id: str | None = None,
    ) -> int:
        async with self._connection() as conn:
            return cast(int, await conn.fetchval("""
                INSERT INTO info_pages (parent_id, title, body_text, image_id)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, parent_id, title, text, image_id))

    async def update_page_content(self, page_id: int, text: Optional[str], image_id: Optional[str]) -> Any:
        async with self._connection() as conn:
            await conn.execute("""
                UPDATE info_pages
                SET body_text = $2, image_id = $3, updated_at = NOW()
                WHERE id = $1
            """, page_id, text, image_id)

    async def delete_page(self, page_id: int) -> Any:
        async with self._connection() as conn:
            await conn.execute("DELETE FROM info_pages WHERE id = $1", page_id)

    async def get_breadcrumbs(self, page_id: int) -> List[Dict[str, Any]]:
        breadcrumbs: list[dict[str, Any]] = []
        current_id = page_id

        while current_id is not None:
            page = await self.get_page(current_id)
            if not page:
                break
            breadcrumbs.insert(0, page)
            current_id = page['parent_id']

        return breadcrumbs

    async def update_page_title(self, page_id: int, title: str) -> Any:
        async with self._connection() as conn:
            await conn.execute("UPDATE info_pages SET title = $2 WHERE id = $1", page_id, title)

    async def update_page_order(self, page_id: int, sort_order: int) -> Any:
        async with self._connection() as conn:
            await conn.execute("UPDATE info_pages SET sort_order = $2 WHERE id = $1", page_id, sort_order)

    async def move_page(self, page_id: int, direction: str) -> Any:
        current_page = await self.get_page(page_id)
        if not current_page:
            return

        parent_id = current_page['parent_id']

        async with self._connection() as conn:
            if parent_id is None:
                query = "SELECT id, sort_order FROM info_pages WHERE parent_id IS NULL ORDER BY sort_order, id"
                siblings = await conn.fetch(query)
            else:
                query = "SELECT id, sort_order FROM info_pages WHERE parent_id = $1 ORDER BY sort_order, id"
                siblings = await conn.fetch(query, parent_id)

            items = [{'id': r['id'], 'sort_order': i} for i, r in enumerate(siblings)]

            current_idx = next((i for i, item in enumerate(items) if item['id'] == page_id), None)
            if current_idx is None:
                return

            if direction == 'up':
                if current_idx > 0:
                    items[current_idx], items[current_idx - 1] = items[current_idx - 1], items[current_idx]
            elif direction == 'down':
                if current_idx < len(items) - 1:
                    items[current_idx], items[current_idx + 1] = items[current_idx + 1], items[current_idx]

            async with conn.transaction():
                for i, item in enumerate(items):
                    await conn.execute(
                        "UPDATE info_pages SET sort_order = $2 WHERE id = $1",
                        item['id'], i
                    )
