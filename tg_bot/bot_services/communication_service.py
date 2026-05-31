# Tg_bot/services/communication_service.py
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, Optional, cast

import asyncpg

from tg_bot.models import CommunicationThread, SenderRole, ThreadMessage
from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)

class CommunicationService:
    def __init__(self, pool: asyncpg.Pool, db_manager: Any = None) -> None:
        self.pool = pool
        self.db_manager = db_manager
        logger.info("Communicationservice инициализирован.")

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Any]:
        tenant = get_current_tenant()
        tenant_id = getattr(tenant, "bot_id", tenant)

        if tenant_id and self.db_manager is not None:
            async with self.db_manager.tenant_connection(tenant_id) as conn:
                yield conn
            return

        async with self.pool.acquire() as conn:
            yield conn

    async def get_or_create_thread(self, order_id: int) -> CommunicationThread:
        """
        Находит чат по ID заказа. Если чата нет, создает новый.
        """
        async with self._connection() as conn:
            thread_row = await conn.fetchrow(
                "SELECT * FROM communication_threads WHERE order_id = $1", order_id
            )
            if thread_row:
                return CommunicationThread(**dict(thread_row))

            # Если чата нет, создаем его
            logger.info(f"Создание нового чата для заказа #{order_id}.")
            new_thread_row = await conn.fetchrow(
                """
                INSERT INTO communication_threads (order_id)
                VALUES ($1)
                RETURNING *
                """,
                order_id
            )
            return CommunicationThread(**dict(new_thread_row))


    async def add_message_by_thread_id(
        self, thread_id: int, sender_id: int, sender_role: SenderRole, text: str
    ) -> ThreadMessage:
        """
        Добавляет сообщение в чат, зная ID треда.
        """
        async with self._connection() as conn:
            async with conn.transaction():
                # Добавляем сообщение
                message_row = await conn.fetchrow(
                    """
                    INSERT INTO thread_messages (thread_id, sender_telegram_id, sender_role, text)
                    VALUES ($1, $2, $3, $4)
                    RETURNING *
                    """,
                    thread_id, sender_id, sender_role.value, text
                )

                # Обновляем статус чата
                # Если пишет персонал (staff), чат становится прочитанным (для персонала),
                # Но можно добавить логику is_read_by_user, если нужно.
                # В текущей логике: is_read=true значит "прочитано персоналом".
                # Если пишет user -> is_read=false (не прочитано персоналом).
                # Если пишет staff -> is_read=true (персонал ответил/прочел).

                is_read_for_staff = (sender_role == SenderRole.STAFF)

                await conn.execute(
                    """
                    UPDATE communication_threads
                    SET last_message_at = NOW(), is_read = $1
                    WHERE id = $2
                    """,
                    is_read_for_staff, thread_id
                )

                logger.info(f"Сообщение добавлено в тред #{thread_id} от {sender_role.value}.")
                return ThreadMessage(**dict(message_row))

    async def add_message_by_order_id(
        self, order_id: int, sender_id: int, sender_role: SenderRole, text: str
    ) -> ThreadMessage:
        """
        Добавляет сообщение, зная только ID заказа (автоматически находит или создает тред).
        """
        thread = await self.get_or_create_thread(order_id)
        return await self.add_message_by_thread_id(thread.id, sender_id, sender_role, text)



    async def get_customer_id_from_thread(self, thread_id: int) -> Optional[int]:
        """
        Возвращает telegram_id клиента, который сделал заказ, связанный с этим чатом.
        """
        query = """
            SELECT o.user_id
            FROM communication_threads ct
            JOIN orders o ON ct.order_id = o.id
            WHERE ct.id = $1
        """
        async with self._connection() as conn:
            user_id = await conn.fetchval(query, thread_id)
            if user_id:
                logger.info(f"Для треда #{thread_id} найден клиент {user_id}.")
                return cast(int | None, user_id)
            else:
                logger.warning(f"Для треда #{thread_id} не найден клиент (возможно, заказ удален).")
                return None


    async def get_all_threads_sorted(self) -> List[CommunicationThread]:
        """
        Возвращает список всех чатов, отсортированный по правилу:
        1. Важные и непрочитанные
        2. Просто непрочитанные
        3. Важные, но прочитанные
        4. Просто прочитанные
        """
        async with self._connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM communication_threads
                ORDER BY is_important DESC, is_read ASC, last_message_at DESC
                """
            )
            return [CommunicationThread(**dict(row)) for row in rows]

    async def get_messages_for_thread(self, thread_id: int) -> List[ThreadMessage]:
        """Возвращает сообщения чата, скрывая те, что были до очистки (для юзера)."""
        # Примечание: для админки мы можем использовать другой метод или флаг ignore_clear
        async with self._connection() as conn:
            # Находим владельца заказа через тред
            user_data = await conn.fetchrow(
                "SELECT u.data_cleared_at FROM communication_threads ct "
                "JOIN orders o ON ct.order_id = o.id "
                "JOIN users u ON o.user_id = u.telegram_id "
                "WHERE ct.id = $1", thread_id
            )

            cleared_at = user_data['data_cleared_at'] if user_data else None

            if cleared_at:
                query = "SELECT * FROM thread_messages WHERE thread_id = $1 AND created_at > $2 ORDER BY created_at ASC"
                rows = await conn.fetch(query, thread_id, cleared_at)
            else:
                query = "SELECT * FROM thread_messages WHERE thread_id = $1 ORDER BY created_at ASC"
                rows = await conn.fetch(query, thread_id)

            return [ThreadMessage(**dict(row)) for row in rows]

    async def update_thread_status(
        self, thread_id: int, is_read: Optional[bool] = None, is_important: Optional[bool] = None
    ) -> None:
        """Обновляет статусы 'прочитано' и 'важно' для чата."""
        # Собираем запрос динамически, чтобы не обновлять лишние поля
        updates = []
        params: list[object] = []

        if is_read is not None:
            params.append(is_read)
            updates.append(f"is_read = ${len(params)}")

        if is_important is not None:
            params.append(is_important)
            updates.append(f"is_important = ${len(params)}")

        if not updates:
            return

        params.append(thread_id)
        query = f"UPDATE communication_threads SET {', '.join(updates)} WHERE id = ${len(params)}"

        async with self._connection() as conn:
            await conn.execute(query, *params)
        logger.info(f"Статус чата #{thread_id} обновлен.")

    async def get_or_create_thread_by_id(self, thread_id: int) -> Optional[CommunicationThread]:
        """Находит чат по его собственному ID."""
        async with self._connection() as conn:
            row = await conn.fetchrow("SELECT * FROM communication_threads WHERE id = $1", thread_id)
            return CommunicationThread(**dict(row)) if row else None

    async def get_thread_by_order_id(self, order_id: int) -> Any:
        """Получает тред по номеру заказа."""
        query = "SELECT * FROM communication_threads WHERE order_id = $1"
        async with self._connection() as conn:
            row = await conn.fetchrow(query, order_id)
            if row:
                from tg_bot.models import CommunicationThread  # Локальный импорт
                return CommunicationThread(**dict(row))
            return None

    async def check_order_has_messages(self, order_id: int) -> bool:
        """
        Проверяет, есть ли хотя бы одно сообщение в треде заказа.
        Возвращает True/False.
        """
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM thread_messages tm
                JOIN communication_threads ct ON tm.thread_id = ct.id
                WHERE ct.order_id = $1
            )
        """
        async with self._connection() as conn:
            return cast(bool, await conn.fetchval(query, order_id))

    async def get_or_create_consultation_thread(self, user_id: int) -> CommunicationThread:
        """Находит или создает общую ветку консультации для пользователя."""
        async with self._connection() as conn:
            # Ищем тред, где order_id is null (это и есть консультация)
            # Нам нужно найти тред именно этого пользователя, поэтому джойним заказы или
            # (что проще) ориентируемся на сообщения.
            # Но правильнее будет искать по subject 'консультация' и привязке к пользователю.

            query = """
                SELECT ct.* FROM communication_threads ct
                JOIN thread_messages tm ON ct.id = tm.thread_id
                WHERE ct.order_id IS NULL AND tm.sender_telegram_id = $1
                ORDER BY ct.last_message_at DESC LIMIT 1
            """
            row = await conn.fetchrow(query, user_id)
            if row:
                return CommunicationThread(**dict(row))

            # Если нет — создаем новый
            new_row = await conn.fetchrow(
                "INSERT INTO communication_threads (subject) VALUES ('Консультация') RETURNING *"
            )
            return CommunicationThread(**dict(new_row))

    async def add_message_general(self, thread_id: int, sender_id: int, sender_role: SenderRole, text: str) -> Any:
        """Универсальный метод добавления сообщения в любой тред."""
        # Используем твой существующий add_message_by_thread_id
        return await self.add_message_by_thread_id(thread_id, sender_id, sender_role, text)
