# Databases/kojo/migrations/versions/005_generalize_delivery.py
"""generalize_delivery

Revision ID: 005
Revises: 004
Create Date: 2025-12-15 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

# Revision Identifiers, Used By Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Переименовываем колонки, чтобы они подходили для любой доставки
    op.alter_column('orders', 'cdek_uuid', new_column_name='delivery_point_id')
    op.alter_column('orders', 'cdek_info', new_column_name='delivery_info')


def downgrade() -> None:
    op.alter_column('orders', 'delivery_point_id', new_column_name='cdek_uuid')
    op.alter_column('orders', 'delivery_info', new_column_name='cdek_info')