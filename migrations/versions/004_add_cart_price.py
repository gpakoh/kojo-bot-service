# /databases/kojo/migrations/versions/004_add_cart_price.py
"""add_cart_price

Revision ID: 004
Revises: 003
Create Date: 2025-12-15 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку для сохранения цены на момент добавления в корзину
    op.execute("""
        ALTER TABLE cart_items
        ADD COLUMN IF NOT EXISTS saved_price NUMERIC(10, 2) DEFAULT 0;
    """)
    
    # Заполняем её текущими ценами для существующих записей (чтобы не сломать старые корзины)
    op.execute("""
        UPDATE cart_items ci
        SET saved_price = pv.price
        FROM product_variants pv
        WHERE ci.product_id = pv.product_id;
    """)

def downgrade() -> None:
    op.execute("ALTER TABLE cart_items DROP COLUMN IF EXISTS saved_price;")