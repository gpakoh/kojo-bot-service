# /databases/kojo/migrations/versions/003_add_delivery_columns.py
"""add_delivery_columns

Revision ID: 003
Revises: 002
Create Date: 2025-12-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поля доставки в таблицу orders
    op.execute("""
        ALTER TABLE orders
        ADD COLUMN IF NOT EXISTS delivery_type VARCHAR(50) DEFAULT 'pickup',
        ADD COLUMN IF NOT EXISTS delivery_address TEXT,
        ADD COLUMN IF NOT EXISTS delivery_price NUMERIC(10, 2) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS cdek_uuid VARCHAR(100),
        ADD COLUMN IF NOT EXISTS cdek_info JSONB;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE orders
        DROP COLUMN IF EXISTS delivery_type,
        DROP COLUMN IF EXISTS delivery_address,
        DROP COLUMN IF EXISTS delivery_price,
        DROP COLUMN IF EXISTS cdek_uuid,
        DROP COLUMN IF EXISTS cdek_info;
    """)