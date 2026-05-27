# /databases/kojo/migrations/versions/002_add_info_pages.py
"""add_info_pages

Revision ID: 002
Revises: 001
Create Date: 2025-12-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Таблица для информационных страниц (cms)
    op.execute("""
        CREATE TABLE IF NOT EXISTS info_pages (
            id SERIAL PRIMARY KEY,
            parent_id INTEGER REFERENCES info_pages(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            body_text TEXT,
            image_id TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS info_pages;")