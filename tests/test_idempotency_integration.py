"""Tests for idempotency integration (§3.3 manifest)."""
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.payment_service import PaymentService
from tg_bot.domain.order import OrderStatus


def make_order_row(order_id: int = 1, user_id: int = 123, status: str = 'Принят',
                   total_amount: float = 200.0) -> dict[str, Any]:
    return {
        'id': order_id, 'user_id': user_id, 'total_amount': total_amount, 'status': status,
        'delivery_type': 'pickup', 'delivery_address': None, 'delivery_price': 0.0,
        'delivery_point_id': None, 'delivery_info': None, 'is_gift': False,
        'gift_comment': None, 'payment_url': None, 'idempotency_key': '',
        'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def mock_idempotency() -> MagicMock:
    store = MagicMock()
    store.check = AsyncMock(return_value=None)
    store.start = AsyncMock()
    store.complete = AsyncMock()
    return store


class TestOrderServiceIdempotency:
    """Idempotency integration for OrderService.update_order_status."""

    @pytest.fixture
    def service(self, mock_idempotency: MagicMock) -> OrderService:
        pool = MagicMock()
        return OrderService(pool, idempotency_store=mock_idempotency)

    @pytest.mark.asyncio
    async def test_idempotency_hit_returns_early(self, service: OrderService, mock_idempotency: MagicMock) -> None:
        """When idempotency key exists, skip processing."""
        mock_idempotency.check.return_value = {"status": "completed", "order_id": 1}

        result = await service.update_order_status(1, OrderStatus.AWAITING_PAYMENT, idempotency_key="dup-key")

        assert result is None
        mock_idempotency.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotency_miss_proceeds(self, service: OrderService, mock_idempotency: MagicMock) -> None:
        """When idempotency key is new, proceed with status update."""
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            make_order_row(status='Принят'),
            make_order_row(status='Ожидает оплаты'),
        ])
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await service.update_order_status(1, OrderStatus.AWAITING_PAYMENT, idempotency_key="new-key")

        assert result is not None
        mock_idempotency.start.assert_awaited_once_with("order:status", "new-key")
        mock_idempotency.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_idempotency_key_skips_check(self, service: OrderService, mock_idempotency: MagicMock) -> None:
        """When no idempotency key, skip check entirely."""
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            make_order_row(status='Принят'),
            make_order_row(status='Ожидает оплаты'),
        ])
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await service.update_order_status(1, OrderStatus.AWAITING_PAYMENT)

        assert result is not None
        mock_idempotency.check.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_idempotency_store_skips_check(self) -> None:
        """When idempotency_store is None, skip idempotency."""
        pool = MagicMock()
        service = OrderService(pool, idempotency_store=None)

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            make_order_row(status='Принят'),
            make_order_row(status='Ожидает оплаты'),
        ])
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await service.update_order_status(1, OrderStatus.AWAITING_PAYMENT, idempotency_key="key")

        assert result is not None


class TestOrderServiceCreateIdempotency:
    """Idempotency integration for OrderService.create_order."""

    @pytest.fixture
    def service(self, mock_idempotency: MagicMock) -> OrderService:
        pool = MagicMock()
        return OrderService(pool, idempotency_store=mock_idempotency)

    @pytest.mark.asyncio
    async def test_create_hit_completed(self, service: OrderService, mock_idempotency: MagicMock) -> None:
        """When idempotency returns completed, return existing order."""
        mock_idempotency.check.return_value = {"status": "completed", "order_id": 1}

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=make_order_row(order_id=1))
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        cart = {"1": {"quantity": 1, "price": 100.0}}
        order = await service.create_order(user_id=123, cart=cart, idempotency_key="existing-key")

        assert order is not None
        assert order.id == 1

    @pytest.mark.asyncio
    async def test_create_hit_processing_raises(self, service: OrderService, mock_idempotency: MagicMock) -> None:
        """When idempotency returns processing, raise error."""
        mock_idempotency.check.return_value = {"status": "processing"}

        cart = {"1": {"quantity": 1, "price": 100.0}}
        with pytest.raises(ValueError, match="Duplicate request in progress"):
            await service.create_order(user_id=123, cart=cart, idempotency_key="in-flight")

    @pytest.mark.asyncio
    async def test_create_miss_creates(self, service: OrderService, mock_idempotency: MagicMock) -> None:
        """When idempotency key is new, create order normally."""
        mock_conn = MagicMock()
        mock_tx = AsyncMock()
        mock_conn.transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.fetchrow = AsyncMock(return_value=make_order_row(order_id=1, total_amount=200.0))
        mock_conn.execute = AsyncMock()
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        cart = {"1": {"quantity": 2, "price": 100.0}}
        order = await service.create_order(user_id=123, cart=cart, idempotency_key="new-key")

        assert order is not None
        mock_idempotency.start.assert_awaited_once_with("order:create", "new-key")
        mock_idempotency.complete.assert_awaited_once()


class TestPaymentServiceIdempotency:
    """Idempotency integration for PaymentService.create_payment_url."""

    @pytest.fixture
    def service(self, mock_idempotency: MagicMock) -> PaymentService:
        return PaymentService(
            quart_url="http://test.integration",
            bot_id="test-bot",
            idempotency_store=mock_idempotency,
        )

    @pytest.mark.asyncio
    async def test_payment_hit_returns_cached(self, service: PaymentService, mock_idempotency: MagicMock) -> None:
        """When idempotency key exists, return cached URL."""
        mock_idempotency.check.return_value = {
            "status": "completed", "payment_url": "https://pay.example.com/123"
        }

        url = await service.create_payment_url(
            order_id=1, total_amount=100.0, cart={}, products={}, user_fio="Test",
            idempotency_key="pay-key"
        )

        assert url == "https://pay.example.com/123"
        mock_idempotency.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_payment_hit_processing_raises(self, service: PaymentService, mock_idempotency: MagicMock) -> None:
        """When idempotency returns processing, raise error."""
        mock_idempotency.check.return_value = {"status": "processing"}

        with pytest.raises(ValueError, match="Duplicate payment request in progress"):
            await service.create_payment_url(
                order_id=1, total_amount=100.0, cart={}, products={}, user_fio="Test",
                idempotency_key="in-flight"
            )

    @pytest.mark.asyncio
    async def test_payment_no_idempotency_store(self) -> None:
        """When idempotency_store is None, skip idempotency."""
        service = PaymentService(quart_url="http://test.integration", bot_id="test-bot")

        with patch.object(service, '_post_request') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"payment_url": "https://pay.example.com"}
            mock_post.return_value = mock_response

            url = await service.create_payment_url(
                order_id=1, total_amount=100.0, cart={}, products={}, user_fio="Test",
                idempotency_key="key"
            )

            assert url == "https://pay.example.com"


class TestIdempotencyStoreFallback:
    """IdempotencyStore with None redis_client."""

    @pytest.mark.asyncio
    async def test_none_redis_returns_none(self) -> None:
        """When redis_client is None, check returns None."""
        from tg_bot.infrastructure.idempotency import IdempotencyStore
        store = IdempotencyStore(redis_client=None)

        result = await store.check("order:create", "key")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_redis_start_noop(self) -> None:
        """When redis_client is None, start is a no-op."""
        from tg_bot.infrastructure.idempotency import IdempotencyStore
        store = IdempotencyStore(redis_client=None)

        await store.start("order:create", "key")

    @pytest.mark.asyncio
    async def test_none_redis_complete_noop(self) -> None:
        """When redis_client is None, complete is a no-op."""
        from tg_bot.infrastructure.idempotency import IdempotencyStore
        store = IdempotencyStore(redis_client=None)

        await store.complete("order:create", "key", {"status": "done"})
