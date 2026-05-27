"""Add missing tables and their indexes

Revision ID: 003_missing_tables
Revises: 001_initial, 002_indexes
Create Date: 2026-04-26

NOTE: This migration creates tables and indexes that depend on them.
      Indexes for tables from 001_initial are in 002_indexes.py
"""
from alembic import op
import sqlalchemy as sa
from typing import Any, Optional

revision = '003_missing_tables'
down_revision = ('001_initial', '002_indexes')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cart Items
    op.create_table(
        'cart_items',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('saved_price', sa.Numeric(10, 2)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('user_id', 'product_id'),
    )
    # Cart Items Indexes (AFTER Table Creation)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cart_items_product ON cart_items(product_id)")
    
    # User Favorites (renamed From Favorites To User_favorites)
    op.create_table(
        'user_favorites',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('notify_on_restock', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('user_id', 'product_id'),
    )
    # Favorites Indexes (AFTER Table Creation)
    op.create_index('idx_fav_user', 'user_favorites', ['user_id'])
    op.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user_product ON user_favorites(user_id, product_id)")
    
    # User Favorite Recipes
    op.create_table(
        'user_favorite_recipes',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('user_id', 'recipe_id'),
    )
    
    # Info Pages
    op.create_table(
        'info_pages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('info_pages.id', ondelete='CASCADE')),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body_text', sa.Text()),
        sa.Column('image_id', sa.String(255)),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
    )
    
    # User Saved Addresses
    op.create_table(
        'user_saved_addresses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('point_id', sa.String(100), nullable=False),
        sa.Column('address_text', sa.Text(), nullable=False),
        sa.Column('custom_name', sa.String(100)),
        sa.Column('is_default', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'provider', 'point_id', name='uq_user_saved_addresses'),
    )
    op.create_index('idx_usa_user', 'user_saved_addresses', ['user_id'])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cart_items_user")
    op.execute("DROP INDEX IF EXISTS idx_cart_items_product")
    op.execute("DROP INDEX IF EXISTS idx_favorites_user_product")
    
    op.drop_table('user_saved_addresses')
    op.drop_table('info_pages')
    op.drop_table('user_favorite_recipes')
    op.drop_table('user_favorites')
    op.drop_table('cart_items')