"""Shared fixtures for handler unit tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Message, Update, User
from telegram.ext import ContextTypes


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 123456
    user.first_name = "Test"
    user.username = "testuser"
    return user


@pytest.fixture
def mock_update(mock_user):
    update = MagicMock(spec=Update)
    update.effective_user = mock_user
    update.callback_query = None
    update.message = None
    return update


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    context.bot_data = {}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.answer_callback_query = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.di = None  # явно сбрасываем, чтобы между тестами не переиспользовался
    return context


@pytest.fixture
def mock_update_with_callback(mock_update, mock_user):
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "action:123"
    cq.answer = AsyncMock()
    mock_update.callback_query = cq
    mock_update.effective_user = mock_user
    return mock_update


@pytest.fixture
def mock_update_with_message(mock_update, mock_user):
    msg = MagicMock(spec=Message)
    msg.text = "test input"
    msg.message_id = 999
    mock_update.message = msg
    mock_update.effective_user = mock_user
    return mock_update


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def mock_cart_service():
    svc = MagicMock()
    svc.get_cart = AsyncMock(return_value={})
    svc.validate_cart = AsyncMock(return_value=(MagicMock(), None))
    svc.update_item = AsyncMock()
    svc.clear_cart = AsyncMock()
    svc.remove_item = AsyncMock()
    return svc


@pytest.fixture
def mock_order_service():
    svc = MagicMock()
    svc.create_order = AsyncMock(return_value=MagicMock(id=1, total_amount=100.0))
    svc.get_order = AsyncMock(return_value=None)
    svc.get_user_orders = AsyncMock(return_value=[])
    svc.update_order_status = AsyncMock()
    return svc


@pytest.fixture
def mock_payment_service():
    svc = MagicMock()
    svc.create_payment_url = AsyncMock(return_value="https://pay.example.com/123")
    return svc


@pytest.fixture
def mock_product_service():
    svc = MagicMock()
    svc.get_product = AsyncMock(return_value=None)
    svc.get_available_products = AsyncMock(return_value=[])
    svc.get_category_products = AsyncMock(return_value=[])
    return svc
