# Tg_bot/bot_services/user_service.py
from typing import Any, Optional

import asyncpg

from tg_bot.models import User, UserRole, UserStatus
from utils.logging_setup import logger


# Низкоуровневые sql-запросы
async def _get_user_by_telegram_id(pool: asyncpg.Pool, telegram_id: int) -> Optional[User]:
    async with pool.acquire() as connection:
        row = await connection.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        if row:
            return User(**dict(row))
        return None

async def _create_user(pool: asyncpg.Pool, telegram_id: int, fio: str, phone: str, email: str) -> User:
    async with pool.acquire() as connection:
        # Добавлен email в запрос
        row = await connection.fetchrow(
            """
            INSERT INTO users (telegram_id, fio, phone, email, status, role)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
            """,
            telegram_id, fio, phone, email, UserStatus.PENDING.value, UserRole.USER.value
        )
        return User(**dict(row))

async def _update_user_status(pool: asyncpg.Pool, telegram_id: int, status: UserStatus) -> Optional[User]:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "UPDATE users SET status = $1 WHERE telegram_id = $2 RETURNING *",
            status.value, telegram_id
        )
        if row:
            return User(**dict(row))
        return None

# Высокоуровневый сервис
class UserService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Получает пользователя по его Telegram ID."""
        return await _get_user_by_telegram_id(self.pool, telegram_id)

    async def approve_user(self, telegram_id: int, moderator_id: int) -> Optional[User]:
        user = await self.get_user(telegram_id)
        if user and user.status == UserStatus.PENDING:
            logger.info(f"Модератор {moderator_id} одобряет пользователя {telegram_id}.")
            return await _update_user_status(self.pool, telegram_id, UserStatus.APPROVED)
        return None

    async def decline_user(self, telegram_id: int, moderator_id: int) -> Optional[User]:
        user = await self.get_user(telegram_id)
        if user and user.status == UserStatus.PENDING:
            logger.info(f"Модератор {moderator_id} отклоняет пользователя {telegram_id}.")
            return await _update_user_status(self.pool, telegram_id, UserStatus.BLOCKED)
        return None

    def is_admin(self, user: Optional[User], admin_ids: list[int]) -> bool:
        if not user:
            return False
        if user.telegram_id in admin_ids:
            return True
        return user.role == UserRole.ADMIN

    def has_staff_privileges(self, user: Optional[User], admin_ids: list[int]) -> bool:
        if not user:
            return False
        if self.is_admin(user, admin_ids):
            return True
        return user.role == UserRole.MANAGER

    async def create_approved_admin(self, telegram_id: int, fio: str, phone: str, email: str) -> Any:
        """Создает нового пользователя со статусом 'approved' и ролью 'admin'."""
        logger.info(f"Создание одобренного администратора в БД для telegram_id={telegram_id}")

        await self.pool.execute(
            """
            INSERT INTO users (telegram_id, fio, phone, email, role, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (telegram_id) DO UPDATE SET
            role = EXCLUDED.role, status = EXCLUDED.status;
            """,
            telegram_id, fio, phone, email, UserRole.ADMIN.value, UserStatus.APPROVED.value
        )

    async def get_users_by_criteria(self, role: UserRole | None = None, status: UserStatus | None = None) -> list[User]:
        """
        Возвращает список пользователей.
        Для статуса PENDING возвращает только тех, кто заполнил ФИО.
        """
        logger.info(f"Запрос пользователей: role={role}, status={status}")

        query = "SELECT * FROM users WHERE 1=1"
        params = []

        if role:
            params.append(role.value)
            query += f" AND role = ${len(params)}"

        if status:
            params.append(status.value)
            query += f" AND status = ${len(params)}"
            # [критично] если смотрим ожидающих — исключаем пустые профили (после logout/reset)
            if status == UserStatus.PENDING:
                query += " AND fio != '' AND fio IS NOT NULL"

        query += " ORDER BY fio;"

        async with self.pool.acquire() as connection:
            rows = await connection.fetch(query, *params)

        users = [User(**dict(row)) for row in rows]
        logger.info(f"Найдено {len(users)} валидных пользователей.")
        return users


    async def get_user_by_db_id(self, db_id: int) -> Optional[User]:
        """Получает пользователя по его первичному ключу (ID) из базы данных."""
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM users WHERE id = $1", db_id)
            if row:
                return User(**dict(row))
            return None


    async def update_user_role(self, db_id: int, new_role: UserRole) -> Optional[User]:
        """Обновляет роль пользователя по его ID в базе."""
        logger.info(f"Обновление роли для пользователя с ID={db_id} на '{new_role.value}'")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE users SET role = $1 WHERE id = $2 RETURNING *",
                new_role.value, db_id
            )
        return User(**dict(row)) if row else None

    async def update_user_status_by_db_id(self, db_id: int, new_status: UserStatus) -> Optional[User]:
        """Обновляет статус пользователя по его ID в базе."""
        logger.info(f"Обновление статуса для пользователя с ID={db_id} на '{new_status.value}'")
        async with self.pool.acquire() as conn:
            # При разблокировке также сбрасываем роль на 'user'
            if new_status == UserStatus.APPROVED:
                row = await conn.fetchrow(
                    "UPDATE users SET status = $1, role = $2 WHERE id = $3 RETURNING *",
                    new_status.value, UserRole.USER.value, db_id
                )
            else:
                 row = await conn.fetchrow(
                    "UPDATE users SET status = $1 WHERE id = $2 RETURNING *",
                    new_status.value, db_id
                )
        return User(**dict(row)) if row else None


    async def register_new_user(self, telegram_id: int, fio: str, phone: str, email: str, auto_approve: bool = False) -> User:
        """Регистрирует или обновляет данные пользователя (UPSERT)."""
        logger.info(f"Запись регистрации для {telegram_id}: {fio}, {phone}")
        new_status = UserStatus.APPROVED.value if auto_approve else UserStatus.PENDING.value

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (telegram_id, fio, phone, email, status, role, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'user', NOW(), NOW())
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    fio = EXCLUDED.fio,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                RETURNING *
                """,
                telegram_id, fio, phone, email, new_status
            )
            return User(**dict(row))


    async def logout_user(self, telegram_id: int, clear_data: bool = False) -> Any:
        """
        Полный выход: зануляет данные пользователя, чтобы он прошел регистрацию заново.
        История (заказы) сохраняется в БД, привязанная к telegram_id, но отсекается по дате.
        """
        logger.info(f"Выход и сброс данных пользователя {telegram_id}. Очистка данных: {clear_data}")
        async with self.pool.acquire() as conn:
            if clear_data:
                # Оборачиваем в транзакцию для надежного каскадного удаления
                async with conn.transaction():
                    # 1. сбрасываем фио, телефон, email и ставим отсечку времени очистки
                    await conn.execute(
                        """
                        UPDATE users
                        SET fio = '', phone = '', email = '',
                            status = $1, data_cleared_at = NOW()
                        WHERE telegram_id = $2
                        """,
                        UserStatus.PENDING.value, telegram_id
                    )

                    # 2. физически удаляем все сохраненные пользовательские данные
                    await conn.execute("DELETE FROM user_favorites WHERE user_id = $1", telegram_id)
                    await conn.execute("DELETE FROM user_favorite_recipes WHERE user_id = $1", telegram_id)
                    await conn.execute("DELETE FROM cart_items WHERE user_id = $1", telegram_id)
                    await conn.execute("DELETE FROM user_saved_addresses WHERE user_id = $1", telegram_id)

                    logger.info(f"🗑 Полная очистка: Избранное, рецепты, корзина и адреса удалены для {telegram_id}")
            else:
                # Просто сбрасываем данные для повторной авторизации
                await conn.execute(
                    """
                    UPDATE users
                    SET fio = '', phone = '', email = '',
                        status = $1
                    WHERE telegram_id = $2
                    """,
                    UserStatus.PENDING.value, telegram_id
                )
        logger.debug("User %s reset for fresh authentication.", telegram_id)


    async def save_registration_message_id(self, telegram_id: int, message_id: int) -> Any:
        """
        Сохраняет ID сообщения о регистрации.
        Нужно для того, чтобы бот мог отредактировать его после одобрения админом.
        """
        logger.info(f"Сохранение registration_message_id={message_id} для пользователя {telegram_id}")
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET registration_message_id = $1 WHERE telegram_id = $2",
                message_id, telegram_id
            )
        logger.debug("Registration message ID %s saved for %s", message_id, telegram_id)

    async def anonymize_user(self, telegram_id: int, requested_by: int) -> bool:
        """
        GDPR-совместимое удаление: анонимизирует все PII пользователя.
        Заказы сохраняются для бухгалтерии, но без персональных данных.
        Возвращает True, если пользователь был найден и анонимизирован.
        """
        logger.warning(
            f"GDPR anonymization requested for telegram_id={telegram_id} "
            f"by moderator={requested_by}"
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT id FROM users WHERE telegram_id = $1",
                    telegram_id,
                )
                if not row:
                    logger.warning(f"GDPR: user {telegram_id} not found")
                    return False

                user_db_id = row['id']

                await conn.execute(
                    """
                    UPDATE users
                    SET fio = '[deleted]', phone = NULL, email = NULL,
                        status = $1, data_cleared_at = NOW(),
                        registration_message_id = NULL
                    WHERE telegram_id = $2
                    """,
                    UserStatus.BLOCKED.value, telegram_id,
                )

                await conn.execute(
                    "DELETE FROM user_favorites WHERE user_id = $1",
                    telegram_id,
                )
                await conn.execute(
                    "DELETE FROM user_favorite_recipes WHERE user_id = $1",
                    telegram_id,
                )
                await conn.execute(
                    "DELETE FROM cart_items WHERE user_id = $1",
                    telegram_id,
                )
                await conn.execute(
                    "DELETE FROM user_saved_addresses WHERE user_id = $1",
                    telegram_id,
                )

                await conn.execute(
                    """
                    UPDATE orders
                    SET delivery_address = NULL,
                        delivery_info = '{}'::jsonb,
                        gift_comment = NULL
                    WHERE user_id = $1
                    """,
                    user_db_id,
                )

        logger.info(
            f"GDPR: user {telegram_id} (db_id={user_db_id}) anonymized. "
            f"Orders preserved without PII."
        )
        return True
