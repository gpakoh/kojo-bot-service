# Migrations/versions/012_add_favorite_recipes.py
"""add favorite recipes table

Revision ID: 012
Revises: 011
Create Date: 2025-12-24 15:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

revision = '012'
down_revision = '011'

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_favorite_recipes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            product_id INTEGER NOT NULL,
            recipe_text TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        );
    """)

def downgrade() -> None:
    op.drop_table('user_favorite_recipes')