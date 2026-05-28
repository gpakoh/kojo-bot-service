"""Tests for OrderRepository abstract class."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytest

from tg_bot.domain.order import Order, OrderItem, OrderStatus
from tg_bot.domain.order_repository import OrderRepository


class MockOrderRepository(OrderRepository):
    """Concrete implementation for testing abstract class."""
    def __init__(self) -> None:
        self.orders: Dict[int, Order] = {}
        self.next_id = 1

    @property
    def pool(self):
        return None

    async def create(self, order: Order) -> Order:
        order.id = self.next_id
        self.orders[self.next_id] = order
        self.next_id += 1
        return order

    async def get_by_id(self, order_id: int) -> Optional[Order]:
        return self.orders.get(order_id)

    async def get_by_id_with_items(self, order_id: int) -> Optional[Tuple[Order, List[OrderItem]]]:
        order = self.orders.get(order_id)
        if order:
            return (order, order.items)
        return None

    async def get_orders_by_user_id(self, user_id: int) -> List[Order]:
        return [o for o in self.orders.values() if o.user_id == user_id]

    async def get_by_user_id_with_clear_check(self, user_id: int, cleared_at: Optional[datetime]) -> list[Order]:
        return [o for o in self.orders.values() if o.user_id == user_id]

    async def get_by_user_id_after_timestamp(self, user_id: int, timestamp: datetime) -> list[Order]:
        return [o for o in self.orders.values() if o.user_id == user_id]

    async def update_status(self, order_id: int, new_status: OrderStatus) -> Optional[Order]:
        if order_id in self.orders:
            self.orders[order_id].transition_to(new_status)
            return self.orders[order_id]
        return None

    async def cancel(self, order_id: int, reason: str) -> Optional[Order]:
        if order_id in self.orders:
            self.orders[order_id].cancel(reason)
            return self.orders[order_id]
        return None

    async def update_delivery(self, order_id: int, **kwargs) -> Optional[Order]:
        return self.orders.get(order_id)

    async def update_comment(self, order_id: int, comment: str) -> None:
        pass

    async def set_payment_url(self, order_id: int, url: str) -> None:
        pass

    async def get_by_statuses(self, statuses: list[OrderStatus]) -> list[Order]:
        return [o for o in self.orders.values() if o.status in statuses]

    async def get_last_active_for_user(self, user_id: int) -> Optional[Order]:
        return None

    async def get_staff_view_orders(self, statuses: List[OrderStatus]) -> List[dict[str, Any]]:
        return []

    async def get_counts_by_status(self) -> Dict[OrderStatus, int]:
        return {}


class TestOrderRepository:
    @pytest.fixture
    def repo(self) -> MockOrderRepository:
        return MockOrderRepository()

    @pytest.fixture
    def sample_order(self) -> Order:
        return Order.create(
            user_id=123,
            items_data=[{"product_id": 1, "quantity": 2, "price": 100.0, "name": "Test"}]
        )

    @pytest.mark.asyncio
    async def test_create_order(self, repo, sample_order) -> None:
        created = await repo.create(sample_order)
        assert created.id == 1
        assert created.user_id == 123

    @pytest.mark.asyncio
    async def test_get_by_id(self, repo, sample_order) -> None:
        created = await repo.create(sample_order)
        retrieved = await repo.get_by_id(created.id)
        assert retrieved is not None
        assert retrieved.user_id == 123

    @pytest.mark.asyncio
    async def test_get_nonexistent_order(self, repo) -> None:
        result = await repo.get_by_id(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_orders_by_user_id(self, repo, sample_order) -> None:
        await repo.create(sample_order)
        sample2 = Order.create(
            user_id=456,
            items_data=[{"product_id": 2, "quantity": 1, "price": 200.0, "name": "Test2"}]
        )
        await repo.create(sample2)

        orders = await repo.get_orders_by_user_id(123)
        assert len(orders) == 1
        assert orders[0].user_id == 123

    @pytest.mark.asyncio
    async def test_update_status_valid_transition(self, repo, sample_order) -> None:
        created = await repo.create(sample_order)
        # Valid Transition: ACCEPTED -> AWAITING_PAYMENT
        updated = await repo.update_status(created.id, OrderStatus.AWAITING_PAYMENT)
        assert updated is not None
        assert updated.status == OrderStatus.AWAITING_PAYMENT

    @pytest.mark.asyncio
    async def test_cancel_order(self, repo, sample_order) -> None:
        created = await repo.create(sample_order)
        cancelled = await repo.cancel(created.id, "Customer request")
        assert cancelled is not None
        assert cancelled.status == OrderStatus.CANCELLED
        assert cancelled.cancellation_reason == "Customer request"

    @pytest.mark.asyncio
    async def test_get_by_statuses(self, repo, sample_order) -> None:
        await repo.create(sample_order)
        orders = await repo.get_by_statuses([OrderStatus.ACCEPTED])
        assert len(orders) == 1

        orders = await repo.get_by_statuses([OrderStatus.PAID])
        assert len(orders) == 0


class TestOrderRepositoryContract:
    """Coverage for abstract OrderRepository itself."""

    def test_cannot_instantiate_abstract(self) -> None:
        from tg_bot.domain.order_repository import OrderRepository
        with pytest.raises(TypeError):
            OrderRepository()

    def test_all_abstract_methods_exist(self) -> None:

        from tg_bot.domain.order_repository import OrderRepository
        abstract_methods = [
            'create', 'get_by_id', 'get_by_id_with_items', 'get_orders_by_user_id',
            'get_by_user_id_with_clear_check', 'get_by_user_id_after_timestamp',
            'update_status', 'cancel', 'update_delivery', 'update_comment',
            'set_payment_url', 'get_by_statuses', 'get_last_active_for_user',
            'get_staff_view_orders', 'get_counts_by_status',
        ]
        for m in abstract_methods:
            assert hasattr(OrderRepository, m), f"Missing {m}"
            assert getattr(OrderRepository, m).__isabstractmethod__
