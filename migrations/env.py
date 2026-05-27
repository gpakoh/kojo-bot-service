# Quart-ollama_bot/databases/kojo/migrations/env.py
import os
import sys
import asyncio
from alembic import context
from sqlalchemy import pool
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from typing import Any, Optional


# Добавляем корневую директорию в путь, чтобы видеть модули проекта
sys.path.append(os.getcwd())

# Считываем конфиг
config = context.config

# Переопределяем url базы из переменных окружения (для docker)
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Alembic требует драйвер postgresql+asyncpg
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection) -> Any:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())