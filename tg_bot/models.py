# Tg_bot/models.py
import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# Enums
class UserStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"

class UserRole(str, Enum):
    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"

# Enum для статусов заказа
class OrderStatus(str, Enum):
    ACCEPTED = "Принят"
    AWAITING_PAYMENT = "Ожидает оплаты"
    PAID = "Оплачен"
    ASSEMBLING = "Комплектуется"
    READY_FOR_PICKUP = "Готов к выдаче"
    SHIPPED = "Передан в доставку"
    COMPLETED = "Завершён"
    CANCELLED = "Отменён"

# Enum для ролей в чате
class SenderRole(str, Enum):
    USER = "user"
    STAFF = "staff"

# Database Models
class User(BaseModel):
    id: int
    telegram_id: int
    fio: str
    phone: str
    email: str
    status: UserStatus = UserStatus.PENDING
    role: UserRole = UserRole.USER
    moderator_id: Optional[int] = None
    registration_message_id: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

class Variant(BaseModel):
    id: int
    product_id: int
    name: str
    price: str
    weight_grams: Optional[int] = None
    volume_ml: Optional[int] = None

class Product(BaseModel):
    id: int
    name: str
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    search_variants: Optional[str] = None
    images: List[str] = []
    chapters: List[str] = []
    variants: List[Variant] = []
    is_available: bool = True

class Order(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: OrderStatus = Field(default=OrderStatus.ACCEPTED)
    payment_url: Optional[str] = None
    cancellation_reason: Optional[str] = None

    # Поля доставки
    delivery_type: Optional[str] = "pickup"
    delivery_address: Optional[str] = None
    delivery_price: float = 0.0
    delivery_point_id: Optional[str] = None
    delivery_info: Optional[dict[str, Any]] = None

    # Поля для подарка
    is_gift: bool = False
    gift_comment: Optional[str] = None

    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    issued_at: Optional[datetime.datetime] = None
    issued_by: Optional[int] = None

    # Поля рейтинга
    rating: Optional[int] = None
    rating_comment: Optional[str] = None

class OrderItem(BaseModel):
    id: int
    order_id: int
    product_id: int
    quantity: int
    price: float

class Setting(BaseModel):
    key: str
    value: str


class CommunicationThread(BaseModel):
    id: int
    order_id: int
    is_read: bool = False
    is_important: bool = False
    last_message_at: datetime.datetime

class ThreadMessage(BaseModel):
    id: int
    thread_id: int
    sender_telegram_id: int
    sender_role: SenderRole
    text: str
    created_at: datetime.datetime
