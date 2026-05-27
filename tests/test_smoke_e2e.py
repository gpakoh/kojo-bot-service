from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_full_order_flow_smoke() -> None:
    """Smoke: create → status update → cart validate. All external mocked."""
    mock_conn = MagicMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': 1, 'user_id': 123, 'status': 'Принят', 'total_amount': 100.0,
        'delivery_type': 'pickup', 'delivery_address': None, 'delivery_price': 0.0,
        'delivery_point_id': None, 'delivery_info': None, 'is_gift': False,
        'gift_comment': None, 'payment_url': None, 'cancellation_reason': None,
        'created_at': '2025-01-01', 'updated_at': '2025-01-01',
    })
    mock_conn.execute = AsyncMock()
    mock_conn.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    mock_conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    from tg_bot.bot_services.cart_service import CartService, CartValidationResult
    from tg_bot.bot_services.order_service import OrderService
    from tg_bot.domain.order import OrderStatus

    order_svc = OrderService(mock_pool)
    cart_svc = CartService(mock_pool)

    # 1. Create Order
    cart = {"1": {"quantity": 1, "price": 100.0}}
    order = await order_svc.create_order(user_id=123, cart=cart, delivery_type='pickup')
    assert order.user_id == 123
    assert order.total_amount.amount == 100.0

    # 2. Update Status
    mock_conn.fetchrow = AsyncMock(side_effect=[
        {'status': 'Принят'},
        {'id': 1, 'user_id': 123, 'status': 'Ожидает оплаты', 'total_amount': 100.0,
         'delivery_type': 'pickup', 'delivery_address': None, 'delivery_price': 0.0,
         'delivery_point_id': None, 'delivery_info': None, 'is_gift': False,
         'gift_comment': None, 'payment_url': None, 'cancellation_reason': None,
         'created_at': '2025-01-01', 'updated_at': '2025-01-01'},
    ])
    updated = await order_svc.update_order_status(1, OrderStatus.AWAITING_PAYMENT)
    assert updated is not None

    # 3. Validate Empty Cart
    mock_conn.fetch = AsyncMock(return_value=[])
    result, msg = await cart_svc.validate_cart(123)
    assert result == CartValidationResult.OK
