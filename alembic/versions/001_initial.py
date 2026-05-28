"""Initial schema migration

Revision ID: 001_initial
Revises: ''
Create Date: 2026-04-26

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    op.create_table(
        'sync_metadata',
        sa.Column('product_folder', sa.Text(), primary_key=True),
        sa.Column('file_hash', sa.Text(), nullable=False),
        sa.Column('last_synced_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    op.execute('CREATE SEQUENCE IF NOT EXISTS products_id_seq')
    op.execute('CREATE SEQUENCE IF NOT EXISTS product_variants_id_seq')
    op.execute('CREATE SEQUENCE IF NOT EXISTS users_id_seq')
    op.execute('CREATE SEQUENCE IF NOT EXISTS orders_id_seq')
    op.execute('CREATE SEQUENCE IF NOT EXISTS order_items_id_seq')
    op.execute('CREATE SEQUENCE IF NOT EXISTS communication_threads_id_seq')
    op.execute('CREATE SEQUENCE IF NOT EXISTS thread_messages_id_seq')

    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'products_id_seq\')')),
        sa.Column('name', sa.Text(), nullable=False, unique=True),
        sa.Column('short_description', sa.Text()),
        sa.Column('full_description', sa.Text()),
        sa.Column('chapters', postgresql.ARRAY(sa.Text())),
        sa.Column('images', postgresql.ARRAY(sa.Text())),
        sa.Column('is_available', sa.Boolean(), server_default='true'),
    )

    op.create_table(
        'product_variants',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'product_variants_id_seq\')')),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE')),
        sa.Column('weight_grams', sa.Integer()),
        sa.Column('volume_ml', sa.Integer()),
        sa.Column('attribute', sa.Text()),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'users_id_seq\')')),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False, unique=True),
        sa.Column('fio', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50)),
        sa.Column('email', sa.String(255)),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('role', sa.String(50), server_default='user'),
        sa.Column('moderator_id', sa.BigInteger()),
        sa.Column('registration_message_id', sa.BigInteger()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'orders_id_seq\')')),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', sa.String(50), server_default='Принят'),
        sa.Column('delivery_type', sa.String(50)),
        sa.Column('delivery_address', sa.Text()),
        sa.Column('delivery_price', sa.Numeric(10, 2), server_default='0'),
        sa.Column('delivery_point_id', sa.String(255)),
        sa.Column('delivery_info', postgresql.JSONB),
        sa.Column('payment_url', sa.Text()),
        sa.Column('cancellation_reason', sa.Text()),
        sa.Column('is_gift', sa.Boolean(), server_default='false'),
        sa.Column('gift_comment', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('issued_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('issued_by', sa.BigInteger()),
    )

    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'order_items_id_seq\')')),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE')),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        'settings',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('value', sa.Text()),
    )

    op.create_table(
        'bot_settings',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('value', sa.Text()),
    )

    op.create_table(
        'communication_threads',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'communication_threads_id_seq\')')),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default='true'),
        sa.Column('is_important', sa.Boolean(), server_default='false'),
        sa.Column('last_message_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    op.create_table(
        'thread_messages',
        sa.Column('id', sa.Integer(), primary_key=True, server_default=sa.text('nextval(\'thread_messages_id_seq\')')),
        sa.Column('thread_id', sa.Integer(), sa.ForeignKey('communication_threads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('sender_role', sa.String(50), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    op.create_index('idx_users_telegram_id', 'users', ['telegram_id'])
    op.create_index('idx_orders_user_id', 'orders', ['user_id'])
    op.create_index('idx_orders_status', 'orders', ['status'])
    op.create_index('idx_product_variants_product_id', 'product_variants', ['product_id'])
    op.create_index('idx_thread_messages_thread_id', 'thread_messages', ['thread_id'])


def downgrade() -> None:
    op.drop_table('thread_messages')
    op.drop_table('communication_threads')
    op.drop_table('bot_settings')
    op.drop_table('settings')
    op.drop_table('order_items')
    op.drop_table('orders')
    op.drop_table('users')
    op.drop_table('product_variants')
    op.drop_table('products')
    op.drop_table('sync_metadata')

    op.execute('DROP SEQUENCE IF EXISTS thread_messages_id_seq')
    op.execute('DROP SEQUENCE IF EXISTS communication_threads_id_seq')
    op.execute('DROP SEQUENCE IF EXISTS order_items_id_seq')
    op.execute('DROP SEQUENCE IF EXISTS orders_id_seq')
    op.execute('DROP SEQUENCE IF EXISTS users_id_seq')
    op.execute('DROP SEQUENCE IF EXISTS product_variants_id_seq')
    op.execute('DROP SEQUENCE IF EXISTS products_id_seq')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
