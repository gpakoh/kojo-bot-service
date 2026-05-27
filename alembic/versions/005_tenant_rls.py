"""Add tenant_id and RLS policies for SaaS isolation.

Revision ID: 005_tenant_rls
Revises: 004_event_store
Create Date: 2026-05-07

"""
from alembic import op
import sqlalchemy as sa

revision = '005_tenant_rls'
down_revision = '004_event_store'
branch_labels = None
depends_on = None

TABLES = [
    'users', 'orders', 'order_items', 'products', 'product_variants',
    'cart_items', 'user_favorites', 'user_favorite_recipes',
    'info_pages', 'user_saved_addresses', 'settings', 'bot_settings',
    'communication_threads', 'thread_messages', 'sync_metadata', 'event_store',
]


def upgrade() -> None:
    # 1. Add Tenant_id To All Tables
    for table in TABLES:
        op.add_column(
            table,
            sa.Column('tenant_id', sa.String(50), nullable=False, server_default='kojo')
        )
        op.create_index(f'idx_{table}_tenant', table, ['tenant_id'])

    # 2. Fix Unique Constraints To Be Per-tenant
    # Users: (tenant_id, Telegram_id)
    op.drop_constraint('users_telegram_id_key', 'users', type_='unique')
    op.create_unique_constraint('uq_users_tenant_telegram', 'users', ['tenant_id', 'telegram_id'])

    # Products: (tenant_id, Name)
    op.drop_constraint('products_name_key', 'products', type_='unique')
    op.create_unique_constraint('uq_products_tenant_name', 'products', ['tenant_id', 'name'])

    # Settings: (tenant_id, Key)
    op.drop_constraint('settings_key_key', 'settings', type_='unique')
    op.create_unique_constraint('uq_settings_tenant_key', 'settings', ['tenant_id', 'key'])

    # Bot_settings: (tenant_id, Key)
    op.drop_constraint('bot_settings_key_key', 'bot_settings', type_='unique')
    op.create_unique_constraint('uq_bot_settings_tenant_key', 'bot_settings', ['tenant_id', 'key'])

    # 3. Enable RLS
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')

    # 4. Create RLS Policies
    for table in TABLES:
        op.execute(f'''
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (tenant_id = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true))
        ''')

    # 5. Helper Function For Setting Tenant Context
    op.execute('''
        CREATE OR REPLACE FUNCTION set_tenant_context(tenant text) RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', tenant, false);
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    ''')


def downgrade() -> None:
    op.execute('DROP FUNCTION IF EXISTS set_tenant_context(text)')

    for table in TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}')
        op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')

    # Restore Old Unique Constraints
    op.drop_constraint('uq_users_tenant_telegram', 'users', type_='unique')
    op.create_unique_constraint('users_telegram_id_key', 'users', ['telegram_id'])

    op.drop_constraint('uq_products_tenant_name', 'products', type_='unique')
    op.create_unique_constraint('products_name_key', 'products', ['name'])

    op.drop_constraint('uq_settings_tenant_key', 'settings', type_='unique')
    op.create_unique_constraint('settings_key_key', 'settings', ['key'])

    op.drop_constraint('uq_bot_settings_tenant_key', 'bot_settings', type_='unique')
    op.create_unique_constraint('bot_settings_key_key', 'bot_settings', ['key'])

    for table in TABLES:
        op.drop_index(f'idx_{table}_tenant', table_name=table)
        op.drop_column(table, 'tenant_id')
