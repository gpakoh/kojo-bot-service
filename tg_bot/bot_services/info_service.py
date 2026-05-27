# Tg_bot/bot_services/info_service.py
import logging
from typing import Any, Dict, List, Optional, cast

import asyncpg

logger = logging.getLogger(__name__)

class InfoService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_page(self, page_id: int) -> Optional[Dict[str, Any]]:
        """Получает страницу по ID."""
        query = "SELECT * FROM info_pages WHERE id = $1"
        return cast(dict[str, Any] | None, await self.pool.fetchrow(query, page_id))

    async def get_children(self, parent_id: Optional[int]) -> List[Dict[str, Any]]:
        """Получает список дочерних страниц (сортировка по sort_order и title)."""
        if parent_id is None:
            query = "SELECT * FROM info_pages WHERE parent_id IS NULL ORDER BY sort_order, title"
            return cast(list[dict[str, Any]], await self.pool.fetch(query))
        else:
            query = "SELECT * FROM info_pages WHERE parent_id = $1 ORDER BY sort_order, title"
            return cast(list[dict[str, Any]], await self.pool.fetch(query, parent_id))

    async def create_page(
        self, parent_id: Optional[int], title: str,
        text: str | None = None, image_id: str | None = None,
    ) -> int:
        """Создает новую страницу."""
        query = """
            INSERT INTO info_pages (parent_id, title, body_text, image_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        return cast(int, await self.pool.fetchval(query, parent_id, title, text, image_id))

    async def update_page_content(self, page_id: int, text: Optional[str], image_id: Optional[str]) -> Any:
        """Обновляет контент страницы."""
        query = """
            UPDATE info_pages
            SET body_text = $2, image_id = $3, updated_at = NOW()
            WHERE id = $1
        """
        await self.pool.execute(query, page_id, text, image_id)

    async def delete_page(self, page_id: int) -> Any:
        """Удаляет страницу (каскадно удалятся и дети благодаря FK)."""
        query = "DELETE FROM info_pages WHERE id = $1"
        await self.pool.execute(query, page_id)

    async def get_breadcrumbs(self, page_id: int) -> List[Dict[str, Any]]:
        """Получает цепочку навигации (хлебные крошки) до корня."""
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
        """Обновляет название страницы."""
        query = "UPDATE info_pages SET title = $2 WHERE id = $1"
        await self.pool.execute(query, page_id, title)

    async def update_page_order(self, page_id: int, sort_order: int) -> Any:
        """Обновляет приоритет сортировки."""
        query = "UPDATE info_pages SET sort_order = $2 WHERE id = $1"
        await self.pool.execute(query, page_id, sort_order)

    async def move_page(self, page_id: int, direction: str) -> Any:
        """
        Меняет порядок сортировки элемента с соседом.
        Пересчитывает порядок всех соседей, чтобы избежать коллизий.
        """
        # 1. получаем текущую страницу
        current_page = await self.get_page(page_id)
        if not current_page:
            return

        parent_id = current_page['parent_id']

        # 2. получаем всех "братьев" в текущем порядке
        # Важно: сортируем по sort_order, а затем по id (стабильная сортировка)
        if parent_id is None:
            query = "SELECT id, sort_order FROM info_pages WHERE parent_id IS NULL ORDER BY sort_order, id"
            siblings = await self.pool.fetch(query)
        else:
            query = "SELECT id, sort_order FROM info_pages WHERE parent_id = $1 ORDER BY sort_order, id"
            siblings = await self.pool.fetch(query, parent_id)

        # Превращаем в список изменяемых словарей для удобства
        items = [{'id': r['id'], 'sort_order': i} for i, r in enumerate(siblings)]

        # Находим индекс текущего элемента
        current_idx = next((i for i, item in enumerate(items) if item['id'] == page_id), None)

        if current_idx is None:
            return

        # 3. меняем местами в памяти
        if direction == 'up':
            if current_idx > 0:
                items[current_idx], items[current_idx - 1] = items[current_idx - 1], items[current_idx]
        elif direction == 'down':
            if current_idx < len(items) - 1:
                items[current_idx], items[current_idx + 1] = items[current_idx + 1], items[current_idx]

        # 4. сохраняем обновленный порядок в бд
        # Используем транзакцию для атомарности
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Обновляем sort_order для всех элементов, чтобы гарантировать последовательность 0, 1, 2...
                # (можно оптимизировать, обновляя только затронутые, но так надежнее для консистентности)
                for i, item in enumerate(items):
                    await conn.execute(
                        "UPDATE info_pages SET sort_order = $2 WHERE id = $1",
                        item['id'], i
                    )
