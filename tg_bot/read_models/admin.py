# Tg_bot/read_models/admin.py
# CQRS Read Models For Admin Subdomain — Pure Data, No Business Logic, No DB Access.
# These Are Plain Dataclasses Consumed By Keyboard Builders And Handler Response Text.

from dataclasses import dataclass, field
from typing import Optional

from tg_bot.domain.order import Order


@dataclass(frozen=True)
class UserListView:
    """Read model: paginated user list (by role or status)."""
    user_id: int
    db_id: int
    fio: str
    status: str
    role: str
    registered_at: str


@dataclass(frozen=True)
class UserDetailsView:
    """Read model: full user card."""
    db_id: int
    telegram_id: int
    fio: str
    phone: str
    email: str
    status_label: str
    role_label: str
    is_blocked: bool
    is_manager: bool
    is_admin: bool


@dataclass(frozen=True)
class UsersMenuView:
    """Read model: aggregate counts for users management menu."""
    pending_count: int
    approved_count: int
    blocked_count: int
    user_count: int
    manager_count: int
    admin_count: int


@dataclass(frozen=True)
class OrderListView:
    """Read model: paginated order list (by status)."""
    order_id: int
    user_fio: str
    total_amount: float
    status: str
    created_at: str
    item_count: int


@dataclass(frozen=True)
class OrderDetailsView:
    """Read model: full order card."""
    order_id: int
    user_id: int
    user_fio: str
    user_phone: str
    total_amount: float
    status: str
    status_label: str
    payment_url: Optional[str]
    delivery_type: str
    delivery_address: Optional[str]
    delivery_price: float
    items: list[object] = field(default_factory=list)
    is_gift: bool = False
    gift_comment: Optional[str] = None


@dataclass(frozen=True)
class OrdersMenuView:
    """Read model: aggregate counts for orders menu."""
    counts: dict[str, object]


@dataclass(frozen=True)
class OrderStatsView:
    """Read model: order statistics for analytics."""
    today_orders: int
    today_revenue: float
    week_orders: int
    week_revenue: float
    month_orders: int
    month_revenue: float
    total_orders: int
    total_revenue: float
    avg_order_value: float


@dataclass(frozen=True)
class PickupPointView:
    """Read model: single pickup point."""
    idx: int
    name: str
    address: str
    schedule: str
    is_active: bool
    editable_fields: list[object]


@dataclass(frozen=True)
class PickupMenuView:
    """Read model: all pickup points."""
    points: list[object]
    add_button_label: str = "➕ Добавить точку самовывоза"


@dataclass(frozen=True)
class CourierMenuView:
    """Read model: courier service status + city list."""
    is_enabled: bool
    cities: list[object]  # [{"name": str, "cost": float, "days": str}]


@dataclass(frozen=True)
class LogoSettingsView:
    """Read model: logo management state."""
    has_logo: bool
    logo_type: str  # "photo" | "video" | "animation"
    logo_id: Optional[str] = None


@dataclass(frozen=True)
class ProxySettingsView:
    """Read model: proxy management state."""
    has_proxy_url: bool
    proxy_url: Optional[str] = None
    is_enabled: bool = True


@dataclass(frozen=True)
class CommunicationThreadView:
    """Read model: thread preview in list."""
    thread_id: int
    order_id: int
    is_read: bool
    is_important: bool
    last_message_at: str
    message_preview: str


@dataclass(frozen=True)
class ThreadChatView:
    """Read model: messages in a thread."""
    thread_id: int
    order_id: int
    messages: list[object]  # [{sender: str, text: str, created_at: str, is_staff: bool}]


@dataclass(frozen=True)
class YandexStationView:
    """Read model: Yandex delivery station config."""
    station_id: Optional[str]
    address: Optional[str]


@dataclass(frozen=True)
class ProductSyncView:
    """Read model: product sync status."""
    last_sync: Optional[str]
    products_count: int
    is_syncing: bool = False


@dataclass(frozen=True)
class SettingsMenuView:
    """Read model: settings menu state."""
    is_auto_approve_enabled: bool
    is_proxy_enabled: bool
    is_courier_enabled: bool
    unread_messages_count: int = 0


@dataclass(frozen=True)
class AdminMainMenuView:
    """Read model: main admin panel entry."""
    unread_messages_count: int = 0


def build_user_list_view(user: object) -> UserListView:
    """Build UserListView from user object."""
    return UserListView(
        user_id=user.telegram_id if hasattr(user, 'telegram_id') else 0,
        db_id=user.id if hasattr(user, 'id') else 0,
        fio=user.fio if hasattr(user, 'fio') else "",
        status=user.status.value if hasattr(user, 'status') and hasattr(user.status, 'value') else str(user.status) if hasattr(user, 'status') else "",
        role=user.role.value if hasattr(user, 'role') and hasattr(user.role, 'value') else str(user.role) if hasattr(user, 'role') else "",
        registered_at=user.created_at.strftime("%d.%m.%Y") if hasattr(user, 'created_at') and hasattr(user.created_at, 'strftime') else str(user.created_at) if hasattr(user, 'created_at') else "",
    )


def build_order_list_view(order: Order) -> OrderListView:
    """Build OrderListView from order object."""
    return OrderListView(
        order_id=order.id if order.id is not None else 0,
        user_fio=order.user_fio if hasattr(order, 'user_fio') else str(order.user_id),
        total_amount=float(order.total_amount.amount) if order.total_amount else 0.0,
        status=order.status.value if hasattr(order.status, 'value') else str(order.status),
        created_at=order.created_at.strftime("%d.%m.%Y %H:%M") if order.created_at and order.created_at and hasattr(order.created_at, 'strftime') else str(order.created_at),
        item_count=len(order.items) if hasattr(order, 'items') else 0,
    )
