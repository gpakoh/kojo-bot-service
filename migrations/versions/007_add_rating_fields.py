# Databases/kojo/migrations/versions/007_add_rating_fields.py
"""add_rating_fields

Revision ID: 007
Revises: 006
Create Date: 2025-12-20 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('orders', sa.Column('rating', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('rating_comment', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('orders', 'rating_comment')
    op.drop_column('orders', 'rating')