# Databases/kojo/migrations/versions/010_allow_consultations.py
"""allow_consultations

Revision ID: 010
Revises: 009
Create Date: 2025-12-22 21:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. делаем order_id необязательным (для общих консультаций)
    op.execute("ALTER TABLE communication_threads ALTER COLUMN order_id DROP NOT NULL;")
    # 2. убираем уникальность order_id, если она мешает (необязательно, но для гибкости)
    # 3. добавляем колонку темы (чтобы в админке было видно: заказ # или консультация)
    op.add_column('communication_threads', sa.Column('subject', sa.String(length=100), nullable=True))
    print("[DEBUG] Migration 010: communication_threads updated for general consultations.")

def downgrade() -> None:
    op.drop_column('communication_threads', 'subject')
    op.execute("ALTER TABLE communication_threads ALTER COLUMN order_id SET NOT NULL;")