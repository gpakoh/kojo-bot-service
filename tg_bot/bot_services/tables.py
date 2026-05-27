# Tg_bot/bot_services/tables.py
# Sqlalchemy Core Table Definitions
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text

metadata = MetaData()

# Products Table
products = Table(
    'products', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('is_available', Boolean, default=True),
    Column('created_at', DateTime, nullable=False),
    Column('updated_at', DateTime),
)

# Product Variants Table
product_variants = Table(
    'product_variants', metadata,
    Column('id', Integer, primary_key=True),
    Column('product_id', Integer, ForeignKey('products.id'), nullable=False),
    Column('weight_grams', Float),
    Column('volume_ml', Float),
    Column('attribute', String(255)),
    Column('price', Float, nullable=False),
)

# Users Table
users = Table(
    'users', metadata,
    Column('telegram_id', Integer, primary_key=True),
    Column('fio', String(255)),
    Column('phone', String(20)),
    Column('email', String(255)),
    Column('status', String(50), default='pending'),
    Column('role', String(50), default='user'),
    Column('created_at', DateTime, nullable=False),
    Column('updated_at', DateTime),
)

# Orders Table
orders = Table(
    'orders', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, nullable=False),
    Column('total_amount', Float, nullable=False),
    Column('status', String(50), nullable=False),
    Column('delivery_type', String(50)),
    Column('delivery_address', Text),
    Column('delivery_price', Float, default=0.0),
    Column('delivery_point_id', String(255)),
    Column('delivery_info', Text),
    Column('is_gift', Boolean, default=False),
    Column('gift_comment', Text),
    Column('payment_url', Text),
    Column('cancellation_reason', Text),
    Column('created_at', DateTime, nullable=False),
    Column('updated_at', DateTime),
)

# Bot Settings Table
settings = Table(
    'bot_settings', metadata,
    Column('key', String(255), primary_key=True),
    Column('value', Text, nullable=False),
)
