"""Add event store for order event sourcing

Revision ID: 004_event_store
Revises: 001_initial, 002_indexes, 003_missing_tables
Create Date: 2026-04-26

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '004_event_store'
down_revision = ('001_initial', '002_indexes', '003_missing_tables')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'event_store',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('stream_id', sa.String(255), nullable=False, index=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('metadata', postgresql.JSONB),
    )

    # Composite Index For Stream Replay
    op.create_index('idx_event_store_stream_version', 'event_store', ['stream_id', 'version'])

    # Index For Event Type Queries (projections)
    op.create_index('idx_event_store_type_created', 'event_store', ['event_type', 'created_at'])

    # Index For Analytics Queries
    op.create_index('idx_event_store_created', 'event_store', ['created_at'])


def downgrade() -> None:
    op.drop_table('event_store')
