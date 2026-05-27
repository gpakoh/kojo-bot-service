"""E2E conftest — mock Telegram Application + all services."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update, User
from telegram.ext import ContextTypes

from tg_bot.models import User as UserModel, UserStatus


@pytest.fixture
def mock_bot_data():
    mock = MagicMock()
    mock.send_message = AsyncMock()
    mock.edit_message_text = AsyncMock()
    mock.answer_callback_query = AsyncMock()
    mock.delete_message = AsyncMock()
    return mock


@pytest.fixture
def mock_e2e_context(mock_bot_data):
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = mock_bot_data
    context.bot_data = {}
    context.user_data = {}
    return context


@pytest.fixture
def mock_e2e_user():
    user = MagicMock(spec=User)
    user.id = 99999
    user.first_name = "E2E"
    user.username = "e2e_user"
    return user


@pytest.fixture
def mock_e2e_update(mock_e2e_user):
    update = MagicMock(spec=Update)
    update.effective_user = mock_e2e_user
    update.effective_chat = MagicMock()
    update.effective_chat.id = 99999
    update.callback_query = None
    update.message = None
    update.inline_query = None
    return update


@pytest.fixture
def mock_services():
    user_svc = MagicMock()
    user_svc.get_user = AsyncMock(return_value=None)
    user_svc.register_new_user = AsyncMock(return_value=UserModel(
        id=1, telegram_id=99999, fio="E2E User", phone="+79999999999",
        email="e2e@test.com", status=UserStatus.PENDING,
        created_at=MagicMock(), updated_at=MagicMock(),
    ))
    user_svc.approve_user = AsyncMock(return_value=UserModel(
        id=1, telegram_id=99999, fio="E2E User", phone="+79999999999",
        email="e2e@test.com", status=UserStatus.APPROVED,
        created_at=MagicMock(), updated_at=MagicMock(),
    ))

    product_svc = MagicMock()
    product_svc.get_category_tree = AsyncMock(return_value={"coffee": ["espresso", "filter"]})
    product_svc.get_available_products = AsyncMock(return_value=[])
    product_svc.get_product = AsyncMock(return_value=None)

    cart_svc = MagicMock()
    cart_svc.get_cart = AsyncMock(return_value={})
    cart_svc.validate_cart = AsyncMock(return_value=(MagicMock(), None))
    cart_svc.update_item = AsyncMock()
    cart_svc.clear_cart = AsyncMock()
    cart_svc.remove_item = AsyncMock()

    order_svc = MagicMock()
    order_svc.create_order = AsyncMock(return_value=MagicMock(id=1, total_amount=1500.0))
    order_svc.set_payment_url = AsyncMock()

    payment_svc = MagicMock()
    payment_svc.create_payment_url = AsyncMock(return_value="https://pay.example.com/order_1")

    settings_svc = MagicMock()
    settings_svc.get_setting = AsyncMock(return_value=None)

    return {
        'user_service': user_svc,
        'product_service': product_svc,
        'cart_service': cart_svc,
        'order_service': order_svc,
        'payment_service': payment_svc,
        'settings_service': settings_svc,
    }


@pytest.fixture
def mock_approved_user(mock_e2e_update, mock_e2e_context, mock_services):
    mock_e2e_context.bot_data.update(mock_services)
    user = UserModel(
        id=1, telegram_id=99999, fio="E2E User", phone="+79999999999",
        email="e2e@test.com", status=UserStatus.APPROVED,
        created_at=MagicMock(), updated_at=MagicMock(),
    )
    mock_services['user_service'].get_user = AsyncMock(return_value=user)
    return mock_e2e_update, mock_e2e_context, mock_services
