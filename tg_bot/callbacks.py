# Tg_bot/callbacks.py
# Central Protocol Registry — Breaks Circular Imports Between Handlers.
# Defines The Interface Each Handler Subdomain Must Expose.

from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


class OrderActions(Protocol):
    """Protocol for order-related actions callable from other handlers."""
    async def show_order_details(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE", order_id_override: Optional[int] = None) -> None: ...
    async def show_orders_menu(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...
    async def show_order_list_by_status(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...
    async def handle_order_action(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...


class CommunicationActions(Protocol):
    """Protocol for communication/chat actions."""
    async def show_communication_center(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...
    async def show_thread_view(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...
    async def handle_thread_action(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...
    async def staff_reply_handler(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...


class PickupActions(Protocol):
    """Protocol for pickup point management."""
    async def show_pickup_mgmt(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...


class LogoActions(Protocol):
    """Protocol for logo management."""
    async def show_logo_mgmt(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...


class ProxyActions(Protocol):
    """Protocol for proxy management."""
    async def show_proxy_mgmt(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...


class CourierActions(Protocol):
    """Protocol for courier management."""
    async def show_courier_mgmt(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None: ...


class AdminDispatch:
    """
    Центральный диспетчер для админ-подсистем.
    Регистрирует обработчики после инициализации, разрывает циклические импорты.
    """
    orders: OrderActions | None = None
    communication: CommunicationActions | None = None
    pickup: PickupActions | None = None
    logo: LogoActions | None = None
    proxy: ProxyActions | None = None
    courier: CourierActions | None = None


admin_dispatch = AdminDispatch()
