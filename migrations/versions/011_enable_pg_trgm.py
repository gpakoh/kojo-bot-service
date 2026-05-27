# Databases/kojo/migrations/versions/011_enable_pg_trgm.py
"""enable pg_trgm extension

Revision ID: 011
Revises: 010
Create Date: 2025-12-23 12:00:00.000000
"""
from alembic import op
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '011'
down_revision = '010' # Укажи здесь ID предыдущей миграции
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Включаем расширение для нечеткого поиска
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    print("[DEBUG] Migration 011: pg_trgm extension enabled.")

def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
    print("[DEBUG] Migration 011: pg_trgm extension dropped.")