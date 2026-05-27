# /quart-ollama_bot/databases/kojo/tg_bot/test_db_schema.py
import asyncio
import logging
import os

import asyncpg
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Подключается к БД и выводит схему таблицы order_items."""
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        logger.error("❌ ошибка: переменная database_url не найдена в файле .env")
        return

    logger.info("Подключаюсь к базе данных: %s", db_url)
    conn = None
    try:
        conn = await asyncpg.connect(db_url)
        logger.info("✅ соединение установлено.")

        logger.info("\n--- схема таблицы 'order_items' ---")

        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'order_items';
        """)

        if not columns:
            logger.info("Таблица 'order_items' не найдена в базе данных!")
        else:
            logger.info("Найдены столбцы:")
            for col in columns:
                logger.info("  - Имя: %s, Тип: %s", col['column_name'], col['data_type'])

        logger.info("---------------------------------")

    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error("❌ Произошла ошибка: %s", e)
    finally:
        if conn:
            await conn.close()
            logger.info("Соединение закрыто.")

if __name__ == "__main__":
    asyncio.run(main())
