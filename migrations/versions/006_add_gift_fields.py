# Databases/kojo/migrations/versions/006_add_gift_fields.py
"""add_gift_fields

Revision ID: 006
Revises: 005
Create Date: 2025-12-19 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Добавляем поля для подарка в таблицу orders
    op.execute("""
        ALTER TABLE orders
        ADD COLUMN IF NOT EXISTS is_gift BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS gift_comment TEXT;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE orders
        DROP COLUMN IF EXISTS is_gift,
        DROP COLUMN IF EXISTS gift_comment;
    """)