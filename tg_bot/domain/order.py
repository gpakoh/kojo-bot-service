# Domain Model For Order Aggregate
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Optional


class OrderStatus(str, Enum):
    ACCEPTED = "Принят"
    AWAITING_PAYMENT = "Ожидает оплаты"
    PAID = "Оплачен"
    ASSEMBLING = "Комплектуется"
    READY_FOR_PICKUP = "Готов к выдаче"
    SHIPPED = "Передан в доставку"
    COMPLETED = "Завершён"
    CANCELLED = "Отменён"


class InvalidStateTransition(Exception):
    """Raised when an invalid order status transition is attempted."""
    pass


class OrderError(Exception):
    """Base exception for order domain errors."""
    pass


@dataclass(frozen=True)
class Money:
    """Value object for money amounts."""
    amount: float

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise OrderError("Money amount cannot be negative")
        object.__setattr__(self, 'amount', round(self.amount, 2))

    def __add__(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)

    def __mul__(self, multiplier: int) -> "Money":
        return Money(self.amount * multiplier)


@dataclass(frozen=True)
class Address:
    """Value object for delivery address."""
    delivery_type: str
    address: Optional[str] = None
    point_id: Optional[str] = None
    info: Optional[dict[str, Any]] = None


@dataclass
class OrderItem:
    """Entity representing a single item in an order."""
    product_id: int
    quantity: int
    price: Money
    name: str = ""

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise OrderError("Item quantity must be positive")
        if self.price.amount < 0:
            raise OrderError("Item price cannot be negative")

    @property
    def subtotal(self) -> "Money":
        return self.price * self.quantity


@dataclass
class Order:
    """
    Aggregate Root for Order.
    Encapsulates all business rules and state transitions.
    """
    user_id: int
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.ACCEPTED
    delivery: Optional[Address] = None
    delivery_price: Money = field(default_factory=lambda: Money(0.0))
    is_gift: bool = False
    gift_comment: Optional[str] = None
    payment_url: Optional[str] = None
    cancellation_reason: Optional[str] = None
    idempotency_key: str = ""

    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    _version: int = 0
    _total_amount: Optional[Money] = None  # Stored total from DB, if available

    VALID_TRANSITIONS: ClassVar[dict[str, Any]] = {
        OrderStatus.ACCEPTED: {OrderStatus.AWAITING_PAYMENT, OrderStatus.CANCELLED},
        OrderStatus.AWAITING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
        OrderStatus.PAID: {OrderStatus.ASSEMBLING, OrderStatus.CANCELLED},
        OrderStatus.ASSEMBLING: {OrderStatus.READY_FOR_PICKUP, OrderStatus.SHIPPED, OrderStatus.CANCELLED},
        OrderStatus.READY_FOR_PICKUP: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
        OrderStatus.SHIPPED: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
        OrderStatus.COMPLETED: set[Any](),
        OrderStatus.CANCELLED: set[Any](),
    }

    def __post_init__(self) -> None:
        if not self.items:
            raise OrderError("Order must contain at least one item")
        if self.user_id <= 0:
            raise OrderError("Invalid user_id")
        if self.is_gift and not self.gift_comment:
            raise OrderError("Gift orders require a comment")

    @property
    def items_total(self) -> Money:
        """Calculate total cost of all items."""
        total = sum((item.subtotal.amount for item in self.items), 0.0)
        return Money(total)

    @property
    def total_amount(self) -> Money:
        """Calculate total including delivery. Use stored value if available (from DB)."""
        if self._total_amount is not None:
            return self._total_amount
        return self.items_total + self.delivery_price

    @property
    def can_cancel(self) -> bool:
        """Check if order can be cancelled."""
        return OrderStatus.CANCELLED in self.VALID_TRANSITIONS.get(self.status, set[Any]())

    @property
    def is_paid(self) -> bool:
        return self.status == OrderStatus.PAID

    @property
    def is_finalized(self) -> bool:
        return self.status in {OrderStatus.COMPLETED, OrderStatus.CANCELLED}

    def _can_transition_to(self, new_status: OrderStatus) -> bool:
        """Check if transition to new status is valid."""
        return new_status in self.VALID_TRANSITIONS.get(self.status, set[Any]())

    @staticmethod
    def can_transition(current: OrderStatus, new: OrderStatus) -> bool:
        """Static check if transition is valid."""
        return current in Order.VALID_TRANSITIONS and new in Order.VALID_TRANSITIONS[current]

    @staticmethod
    def validate_transition(current: OrderStatus, new: OrderStatus) -> None:
        """Static validation of status transition."""
        if not Order.can_transition(current, new):
            raise InvalidStateTransition(
                f"Invalid status transition: {current.value} → {new.value}"
            )

    def transition_to(self, new_status: OrderStatus) -> None:
        """
        Validate and perform state transition.
        Raises InvalidStateTransition if not allowed.
        """
        if not self._can_transition_to(new_status):
            raise InvalidStateTransition(
                f"Cannot transition from {self.status.value} to {new_status.value}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

    def set_delivery(self, delivery: Address, price: Money) -> None:
        """Set delivery information. Only allowed before payment."""
        if self.is_paid:
            raise OrderError("Cannot change delivery after payment")
        self.delivery = delivery
        self.delivery_price = price

    def mark_as_paid(self, payment_url: Optional[str] = None) -> None:
        """Mark order as paid."""
        self.transition_to(OrderStatus.PAID)
        self.payment_url = payment_url

    def cancel(self, reason: str) -> None:
        """Cancel the order with a reason."""
        if not self.can_cancel:
            raise OrderError(f"Cannot cancel order in status {self.status.value}")
        self.transition_to(OrderStatus.CANCELLED)
        self.cancellation_reason = reason

    def add_item(self, product_id: int, quantity: int, price: float, name: str = "") -> None:
        """Add an item to the order."""
        if self.is_finalized:
            raise OrderError("Cannot modify finalized order")
        item = OrderItem(
            product_id=product_id,
            quantity=quantity,
            price=Money(price),
            name=name
        )
        self.items.append(item)

    def remove_item(self, product_id: int) -> None:
        """Remove an item from the order."""
        if self.is_finalized:
            raise OrderError("Cannot modify finalized order")
        self.items = [item for item in self.items if item.product_id != product_id]
        if not self.items:
            raise OrderError("Order must contain at least one item")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'total_amount': self.total_amount.amount,
            'status': self.status.value,
            'delivery_type': self.delivery.delivery_type if self.delivery else None,
            'delivery_address': self.delivery.address if self.delivery else None,
            'delivery_price': self.delivery_price.amount,
            'delivery_point_id': self.delivery.point_id if self.delivery else None,
            'delivery_info': self.delivery.info if self.delivery else None,
            'is_gift': self.is_gift,
            'gift_comment': self.gift_comment,
            'payment_url': self.payment_url,
            'cancellation_reason': self.cancellation_reason,
            'idempotency_key': self.idempotency_key,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Order":
        """Reconstruct order from dictionary (e.g. from cache/serialized)."""
        order = cls.__new__(cls)
        order.id = data.get('id')
        order.user_id = data['user_id']
        order.status = OrderStatus(data['status'])
        order.delivery = Address(
            delivery_type=data.get('delivery_type', 'pickup'),
            address=data.get('delivery_address'),
            point_id=data.get('delivery_point_id'),
            info=data.get('delivery_info'),
        ) if data.get('delivery_type') else None
        order.delivery_price = Money(data.get('delivery_price', 0.0))
        order.is_gift = data.get('is_gift', False)
        order.gift_comment = data.get('gift_comment')
        order.payment_url = data.get('payment_url')
        order.cancellation_reason = data.get('cancellation_reason')
        order.idempotency_key = data.get('idempotency_key', "")
        order.created_at = data.get('created_at')
        order.updated_at = data.get('updated_at')
        order._version = 0
        order.items = []
        if 'total_amount' in data:
            order._total_amount = Money(float(data['total_amount']))
        return order

    @classmethod
    def create(
        cls,
        user_id: int,
        items_data: list[dict[str, Any]],
        delivery: Optional[Address] = None,
        delivery_price: float = 0.0,
        is_gift: bool = False,
        gift_comment: Optional[str] = None,
    ) -> "Order":
        """
        Factory method to create a new order.
        Calculates total server-side from items.
        """
        items = []
        for item_data in items_data:
            items.append(OrderItem(
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                price=Money(item_data['price']),
                name=item_data.get('name', '')
            ))

        order = cls(
            user_id=user_id,
            items=items,
            delivery=delivery,
            delivery_price=Money(delivery_price),
            is_gift=is_gift,
            gift_comment=gift_comment,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return order

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Order":
        """Reconstruct order from database row. Items must be loaded separately."""
        order = cls.__new__(cls)
        order.id = row.get('id')
        order.user_id = row['user_id']
        order.status = OrderStatus(row['status'])
        order.delivery = Address(
            delivery_type=row.get('delivery_type', 'pickup'),
            address=row.get('delivery_address'),
            point_id=row.get('delivery_point_id'),
            info=row.get('delivery_info'),
        ) if row.get('delivery_type') else None
        order.delivery_price = Money(row.get('delivery_price', 0.0))
        order.is_gift = row.get('is_gift', False)
        order.gift_comment = row.get('gift_comment')
        order.payment_url = row.get('payment_url')
        order.cancellation_reason = row.get('cancellation_reason')
        order.created_at = row.get('created_at') or datetime.now(timezone.utc)
        order.updated_at = row.get('updated_at') or datetime.now(timezone.utc)
        order._version = 0
        order.items = []
        # Store The Total_amount From DB
        if 'total_amount' in row:
            order._total_amount = Money(float(row['total_amount']))
        return order
