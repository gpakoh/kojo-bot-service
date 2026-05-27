"""add idempotency_key column to orders table

Revision ID: 013
Revises: 012
Create Date: 2025-12-25 10:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = '013'
down_revision = '012'

def upgrade() -> None:
    op.add_column('orders', sa.Column('idempotency_key', sa.String(255), nullable=True))
    op.create_index('ix_orders_idempotency_key', 'orders', ['idempotency_key'])

def downgrade() -> None:
    op.drop_index('ix_orders_idempotency_key', table_name='orders')
    op.drop_column('orders', 'idempotency_key')
