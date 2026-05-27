# Tg_bot/domain/order_repository.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import asyncpg

from tg_bot.domain.order import Order, OrderItem, OrderStatus


class OrderRepository(ABC):
    """
    Abstract repository for Order aggregate.

    Defines the interface for persisting and retrieving orders.
    Implementation-specific details (SQL, ORM, etc.) are in infrastructure/.
    """

    @property
    @abstractmethod
    def pool(self) -> asyncpg.Pool:
        """Database connection pool."""
        pass

    @abstractmethod
    async def create(self, order: Order) -> Order:
        """Create a new order in persistence."""
        pass

    @abstractmethod
    async def get_by_id(self, order_id: int) -> Optional[Order]:
        """Get order by ID."""
        pass

    @abstractmethod
    async def get_by_id_with_items(self, order_id: int) -> Optional[Tuple[Order, List[OrderItem]]]:
        """Get order with its items."""
        pass

    @abstractmethod
    async def get_orders_by_user_id(self, user_id: int) -> List[Order]:
        """Get all orders for a user."""
        pass

    @abstractmethod
    async def get_by_user_id_with_clear_check(self, user_id: int, cleared_at: Optional[datetime]) -> list[Order]:
        """Get orders for user, excluding those before a clear date."""
        pass

    @abstractmethod
    async def get_by_user_id_after_timestamp(self, user_id: int, timestamp: datetime) -> list[Order]:
        """Get orders for user after a specific timestamp."""
        pass

    @abstractmethod
    async def update_status(self, order_id: int, new_status: OrderStatus) -> Optional[Order]:
        """Update order status."""
        pass

    @abstractmethod
    async def cancel(self, order_id: int, reason: str) -> Optional[Order]:
        """Cancel order with reason."""
        pass

    @abstractmethod
    async def update_delivery(
        self,
        order_id: int,
        total_amount: float,
        delivery_type: str,
        delivery_address: str,
        delivery_price: float,
        delivery_point_id: str,
        delivery_info: dict[str, object],
        is_gift: bool,
        gift_comment: str,
    ) -> Optional[Order]:
        """Update order delivery info."""
        pass

    @abstractmethod
    async def update_comment(self, order_id: int, comment: str) -> None:
        """Update order comment."""
        pass

    @abstractmethod
    async def set_payment_url(self, order_id: int, url: str) -> None:
        """Set payment URL and update status."""
        pass

    @abstractmethod
    async def get_by_statuses(self, statuses: list[OrderStatus]) -> list[Order]:
        """Get orders by statuses."""
        pass

    @abstractmethod
    async def get_last_active_for_user(self, user_id: int) -> Optional[Order]:
        """Get last active (non-completed) order for user."""
        pass

    @abstractmethod
    async def get_staff_view_orders(self, statuses: list[OrderStatus]) -> list[dict[str, object]]:
        """Get aggregated staff view data."""
        pass

    @abstractmethod
    async def get_counts_by_status(self) -> Dict[OrderStatus, int]:
        """Get order counts grouped by status."""
        pass


__all__ = ['OrderRepository']
