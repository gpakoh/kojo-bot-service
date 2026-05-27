"""add_bot_relations

Revision ID: 002
Revises: 001
Create Date: 2025-04-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional


revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. добавляем bot_id в orders
    op.execute("""
        ALTER TABLE orders
        ADD COLUMN IF NOT EXISTS bot_id VARCHAR(50);
    """)
    
    # 2. создаем индекс для быстрого поиска по bot_id
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_bot_id
        ON orders(bot_id);
    """)
    
    # 3. создаем таблицу bot_users (many-to-many)
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_users (
            bot_id VARCHAR(50) NOT NULL,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (bot_id, user_id)
        );
    """)
    
    # 4. индекс для поиска пользователей бота
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_bot_users_user_id
        ON bot_users(user_id);
    """)
    
    # 5. обновляем существующие заказы: привязываем к боту 'kojo' для обратной совместимости
    # (только если orders не пустые и bot_id is null)
    op.execute("""
        UPDATE orders
        SET bot_id = 'kojo'
        WHERE bot_id IS NULL;
    """)


def downgrade() -> None:
    # 1. удаляем таблицу bot_users
    op.execute("DROP TABLE IF EXISTS bot_users;")
    
    # 2. удаляем индекс и колонку bot_id из orders
    op.execute("DROP INDEX IF EXISTS idx_orders_bot_id;")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS bot_id;")