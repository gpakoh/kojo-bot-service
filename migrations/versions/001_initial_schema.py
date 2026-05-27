# /databases/kojo/migrations/versions/001_initial_schema.py
"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2023-10-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional


# Revision Identifiers, Used By Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. таблица метаданных синхронизации
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            product_folder TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            last_synced_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 2. таблица продуктов
    op.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            short_description TEXT,
            full_description TEXT,
            chapters TEXT[],
            images TEXT[],
            is_available BOOLEAN DEFAULT TRUE
        );
    """)

    # 3. таблица вариантов продуктов
    op.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id SERIAL PRIMARY KEY,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            weight_grams INTEGER,
            volume_ml INTEGER,
            attribute TEXT,
            price NUMERIC(10, 2) NOT NULL
        );
    """)

    # 4. таблица пользователей
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            fio VARCHAR(255) NOT NULL,
            phone VARCHAR(50),
            email VARCHAR(255),
            status VARCHAR(50) DEFAULT 'pending',
            role VARCHAR(50) DEFAULT 'user',
            moderator_id BIGINT,
            registration_message_id BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 5. таблица заказов
    op.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            total_amount NUMERIC(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'Принят',
            payment_url TEXT,
            cancellation_reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            issued_at TIMESTAMPTZ,
            issued_by BIGINT
        );
    """)

    # 6. элементы заказа
    op.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price NUMERIC(10, 2) NOT NULL
        );
    """)

    # 7. настройки (старая таблица settings, можно оставить для совместимости)
    op.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT
        );
    """)

    # 8. настройки бота (новая таблица)
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT
        );
    """)

    # 9. чат поддержки (треды)
    op.execute("""
        CREATE TABLE IF NOT EXISTS communication_threads (
            id SERIAL PRIMARY KEY,
            order_id INTEGER UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            is_read BOOLEAN DEFAULT TRUE,
            is_important BOOLEAN DEFAULT FALSE,
            last_message_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 10. сообщения в чатах
    op.execute("""
        CREATE TABLE IF NOT EXISTS thread_messages (
            id SERIAL PRIMARY KEY,
            thread_id INTEGER NOT NULL REFERENCES communication_threads(id) ON DELETE CASCADE,
            sender_telegram_id BIGINT NOT NULL,
            sender_role VARCHAR(50) NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # === новая таблица: корзина ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, product_id)
        );
    """)


def downgrade() -> None:
    # В случае отката удаляем таблицу корзины (остальное лучше не трогать, чтобы данные не потерять при тесте)
    op.execute("DROP TABLE IF EXISTS cart_items;")