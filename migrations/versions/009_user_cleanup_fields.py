# Databases/kojo/migrations/versions/009_user_cleanup_fields.py
"""user_cleanup_fields

Revision ID: 009
Revises: 008
Create Date: 2025-12-22 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Поле для отсечки видимости данных пользователем
    op.add_column('users', sa.Column('data_cleared_at', sa.DateTime(timezone=True), nullable=True))
    print("[DEBUG] Migration 009: Column 'data_cleared_at' added to 'users'.")

def downgrade() -> None:
    op.drop_column('users', 'data_cleared_at')