# Tests/test_cart_service.py
import asyncio
import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.cart_service import CartService, CartValidationResult


class TestCartService:
    @pytest.fixture
    def mock_pool(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        return pool, conn

    @pytest.mark.asyncio
    async def test_update_item_executes_query(self, mock_pool) -> Any:
        pool, conn = mock_pool
        service = CartService(pool)
        await service.update_item(user_id=123, product_id=456, quantity=2)
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_item_single_product(self, mock_pool) -> Any:
        pool, conn = mock_pool
        service = CartService(pool)
        await service.remove_item(123, 456)
        conn.execute.assert_awaited_once()
        call_args = conn.execute.call_args
        assert "DELETE FROM cart_items" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_clear_cart_deletes_all(self, mock_pool) -> Any:
        pool, conn = mock_pool
        service = CartService(pool)
        await service.clear_cart(123)
        conn.execute.assert_awaited_once()
        call_args = conn.execute.call_args
        assert "DELETE FROM cart_items" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_is_cart_empty_true(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=False)
        service = CartService(pool)
        result = await service.is_cart_empty(123)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_cart_empty_false(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=True)
        service = CartService(pool)
        result = await service.is_cart_empty(123)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_cart_returns_ok_when_empty(self, mock_pool) -> Any:
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        service = CartService(pool)
        result, message = await service.validate_cart(123)
        assert result == CartValidationResult.OK
        assert message is None

    @pytest.mark.asyncio
    async def test_validate_cart_returns_ok_when_fresh(self, mock_pool) -> Any:
        pool, conn = mock_pool
        now = datetime.datetime.now(datetime.timezone.utc)
        fresh_row = {
            'product_id': 1, 'saved_price': 100.0, 'created_at': now,
            'name': 'Кофе', 'is_available': True, 'current_price': 100.0
        }
        conn.fetch = AsyncMock(return_value=[fresh_row])
        service = CartService(pool)
        result, message = await service.validate_cart(123)
        assert result == CartValidationResult.OK
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_cart_removes_only_stale_changed_items(self, mock_pool) -> Any:
        pool, conn = mock_pool
        now = datetime.datetime.now(datetime.timezone.utc)
        stale_ago = now - datetime.timedelta(hours=25)
        stale_row = {
            'product_id': 1, 'saved_price': 100.0, 'created_at': stale_ago,
            'name': 'Кофе', 'is_available': True, 'current_price': 120.0
        }
        fresh_row = {
            'product_id': 2, 'saved_price': 50.0, 'created_at': now,
            'name': 'Чай', 'is_available': True, 'current_price': 50.0
        }
        conn.fetch = AsyncMock(return_value=[stale_row, fresh_row])
        conn.execute = AsyncMock(return_value="DELETE 1")

        service = CartService(pool)
        result, message = await service.validate_cart(123)
        assert result == CartValidationResult.CLEARED_OLD
        assert "Кофе" in message
        assert "Чай" not in message
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_cart_blocks_unavailable(self, mock_pool) -> Any:
        pool, conn = mock_pool
        now = datetime.datetime.now(datetime.timezone.utc)
        unavailable_row = {
            'product_id': 1, 'saved_price': 100.0, 'created_at': now,
            'name': 'Кофе', 'is_available': False, 'current_price': 100.0
        }
        conn.fetch = AsyncMock(return_value=[unavailable_row])
        service = CartService(pool)
        result, message = await service.validate_cart(123)
        assert result == CartValidationResult.ITEM_UNAVAILABLE
        assert "Кофе" in message

    @pytest.mark.asyncio
    async def test_get_cart_returns_dict(self, mock_pool) -> Any:
        pool, conn = mock_pool
        row = {'product_id': 1, 'quantity': 2, 'price': 100.0}
        conn.fetch = AsyncMock(return_value=[row])
        service = CartService(pool)
        cart = await service.get_cart(123)
        assert "1" in cart
        assert cart["1"]["quantity"] == 2
        assert cart["1"]["price"] == 100.0


class TestCartConcurrent:
    @pytest.mark.asyncio
    async def test_concurrent_update_same_product(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        service = CartService(pool)

        async def fast_click():
            await service.update_item(user_id=123, product_id=456, quantity=1)

        tasks = [fast_click() for _ in range(5)]
        await asyncio.gather(*tasks)

        assert conn.execute.call_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_updates_different_products(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        service = CartService(pool)

        async def add_product(pid):
            await service.update_item(user_id=123, product_id=pid, quantity=1)

        tasks = [add_product(i) for i in range(10)]
        await asyncio.gather(*tasks)

        assert conn.execute.call_count == 10

    @pytest.mark.asyncio
    async def test_rapid_validate_cart_no_double_remove(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()

        now = datetime.datetime.now(datetime.timezone.utc)
        conn.fetch = AsyncMock(return_value=[{
            'product_id': 1, 'saved_price': 100.0, 'created_at': now,
            'name': 'Товар', 'is_available': True, 'current_price': 120.0
        }])
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()

        service = CartService(pool)

        async def double_validate():
            return await service.validate_cart(123)

        tasks = [double_validate() for _ in range(3)]
        await asyncio.gather(*tasks)

        assert conn.fetch.call_count == 3

    @pytest.mark.asyncio
    async def test_double_click_add_same_product(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        service = CartService(pool)

        async def double_click_add():
            await service.update_item(user_id=123, product_id=1, quantity=1)

        tasks = [double_click_add() for _ in range(2)]
        await asyncio.gather(*tasks)

        assert conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_rapid_clear_and_add_cart(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        service = CartService(pool)

        async def clear_cart():
            return await service.clear_cart(123)

        async def add_item():
            return await service.update_item(user_id=123, product_id=1, quantity=1)

        await asyncio.gather(clear_cart(), add_item())
        assert conn.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_concurrent_remove_item(self) -> Any:
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        pool.acquire.return_value.__aexit__.return_value = AsyncMock()
        service = CartService(pool)

        async def remove_item():
            return await service.update_item(user_id=123, product_id=1, quantity=0)

        tasks = [remove_item() for _ in range(3)]
        await asyncio.gather(*tasks)

        assert conn.execute.call_count == 3
