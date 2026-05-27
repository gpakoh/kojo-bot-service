# Databases/kojo/migrations/versions/008_add_search_variants.py
"""add_search_variants

Revision ID: 008
Revises: 007
Create Date: 2025-12-22 16:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Добавляем колонку для хранения вариантов поиска (синонимов)
    op.add_column('products', sa.Column('search_variants', sa.Text(), nullable=True))
    print("[DEBUG] Migration 008: Column 'search_variants' added to 'products' table.")

def downgrade() -> None:
    op.drop_column('products', 'search_variants')
    print("[DEBUG] Migration 008: Column 'search_variants' dropped.")