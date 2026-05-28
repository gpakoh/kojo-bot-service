"""Add performance indexes for existing tables

Revision ID: 002_indexes
Revises: 001_initial
Create Date: 2026-04-26

NOTE: Indexes for cart_items, favorites, and other tables created in 003_missing_tables
      are in migration 003 or later to avoid dependency issues.
"""


from alembic import op

revision = '002_indexes'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Orders Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")

    # Products Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_available ON products(is_available) WHERE is_available = TRUE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")

    # Product Variants Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_product_variants_product ON product_variants(product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_product_variants_price ON product_variants(price)")

    # Users Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")

    # Settings Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bot_settings_key ON bot_settings(key)")

    # Communication Threads Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_communication_threads_order ON communication_threads(order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_thread_messages_thread ON thread_messages(thread_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_thread_messages_created ON thread_messages(created_at DESC)")

    # Sync Metadata Indexes (table Exists In 001_initial)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sync_metadata_folder ON sync_metadata(product_folder)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_orders_user_status")
    op.execute("DROP INDEX IF EXISTS idx_orders_created_at")
    op.execute("DROP INDEX IF EXISTS idx_orders_status")

    op.execute("DROP INDEX IF EXISTS idx_products_available")
    op.execute("DROP INDEX IF EXISTS idx_products_name")

    op.execute("DROP INDEX IF EXISTS idx_product_variants_product")
    op.execute("DROP INDEX IF EXISTS idx_product_variants_price")

    op.execute("DROP INDEX IF EXISTS idx_users_telegram")
    op.execute("DROP INDEX IF EXISTS idx_users_status")

    op.execute("DROP INDEX IF EXISTS idx_settings_key")
    op.execute("DROP INDEX IF EXISTS idx_bot_settings_key")

    op.execute("DROP INDEX IF EXISTS idx_communication_threads_order")
    op.execute("DROP INDEX IF EXISTS idx_thread_messages_thread")
    op.execute("DROP INDEX IF EXISTS idx_thread_messages_created")

    op.execute("DROP INDEX IF EXISTS idx_sync_metadata_folder")
