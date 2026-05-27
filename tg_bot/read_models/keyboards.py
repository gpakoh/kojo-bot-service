# Tg_bot/read_models/keyboards.py
# CQRS Keyboard Builders — Consume Readmodels, Return Telegram Inlinekeyboardmarkup.
# All Functions Are Pure: Input Readmodel → Telegram Keyboard. No DB, No Business Logic.


from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from tg_bot.keyboards import (
    CB_ADMIN_BACK_TO_MAIN,
    CB_ADMIN_COMMUNICATION_CENTER,
    CB_ADMIN_COURIER_MGMT,
    CB_ADMIN_COURIER_TOGGLE,
    CB_ADMIN_LOGO_MGMT,
    CB_ADMIN_LOGO_SET,
    CB_ADMIN_ORDERS,
    CB_ADMIN_PICKUP_ADD,
    CB_ADMIN_PICKUP_MGMT,
    CB_ADMIN_PROXY_MGMT,
    CB_ADMIN_PROXY_SET,
    CB_ADMIN_PROXY_TOGGLE,
    CB_ADMIN_SETTINGS,
    CB_ADMIN_SETUP_YANDEX,
    CB_ADMIN_STATS,
    CB_ADMIN_SYNC_PRODUCTS,
    CB_ADMIN_TOGGLE_AUTO_APPROVE,
    CB_ADMIN_USERS,
    CB_ADMIN_WELCOME_TEXT_EDIT,
    CB_CLOSE_GENERIC,
    CB_PREFIX_ORDER_ACTION,
    CB_PREFIX_ORDER_DETAILS,
    CB_PREFIX_ORDERS_BY_STATUS,
    CB_PREFIX_USER_ACTION,
    CB_PREFIX_USER_DETAILS,
    CB_PREFIX_USERS_BY_ROLE,
    CB_PREFIX_USERS_BY_STATUS,
    CB_USER_SHOW_MAIN_MENU,
)
from tg_bot.read_models.admin import (
    AdminMainMenuView,
    CourierMenuView,
    LogoSettingsView,
    OrderListView,
    OrdersMenuView,
    PickupMenuView,
    PickupPointView,
    ProxySettingsView,
    SettingsMenuView,
    UserDetailsView,
    UserListView,
    UsersMenuView,
)


def build_admin_main_menu(view: AdminMainMenuView) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("👥 Пользователи", callback_data=CB_ADMIN_USERS)],
        [InlineKeyboardButton("📦 Заказы", callback_data=CB_ADMIN_ORDERS)],
        [InlineKeyboardButton(f"💬 Чаты {f'({view.unread_messages_count})' if view.unread_messages_count else ''}", callback_data=CB_ADMIN_COMMUNICATION_CENTER)],
        [InlineKeyboardButton("⚙️ Настройки", callback_data=CB_ADMIN_SETTINGS)],
        [InlineKeyboardButton("🔄 Синхронизировать товары", callback_data=CB_ADMIN_SYNC_PRODUCTS)],
        [InlineKeyboardButton("📊 Статистика", callback_data=CB_ADMIN_STATS)],
        [InlineKeyboardButton("🏠 В меню", callback_data=CB_USER_SHOW_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(rows)


def build_users_menu(view: UsersMenuView) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"⏳ В ожидании ({view.pending_count})", callback_data=f"{CB_PREFIX_USERS_BY_STATUS}pending")],
        [InlineKeyboardButton(f"✅ Авторизованные ({view.approved_count})", callback_data=f"{CB_PREFIX_USERS_BY_STATUS}approved")],
        [InlineKeyboardButton(f"🚫 Заблокированные ({view.blocked_count})", callback_data=f"{CB_PREFIX_USERS_BY_STATUS}blocked")],
        [InlineKeyboardButton(f"👤 Пользователи ({view.user_count})", callback_data=f"{CB_PREFIX_USERS_BY_ROLE}user")],
        [InlineKeyboardButton(f"👨‍💼 Менеджеры ({view.manager_count})", callback_data=f"{CB_PREFIX_USERS_BY_ROLE}manager")],
        [InlineKeyboardButton(f"👑 Администраторы ({view.admin_count})", callback_data=f"{CB_PREFIX_USERS_BY_ROLE}admin")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_USERS)],
    ]
    return InlineKeyboardMarkup(rows)


def build_user_list_keyboard(items: list[UserListView], source: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        f"{item.fio} ({item.status})",
        callback_data=f"{CB_PREFIX_USER_DETAILS}{item.db_id}_{source}"
    )] for item in items]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_USERS)])
    return InlineKeyboardMarkup(rows)


def build_user_details_keyboard(view: UserDetailsView, source: str) -> InlineKeyboardMarkup:
    rows = []
    action = f"approve_{view.db_id}"
    rows.append([InlineKeyboardButton("✅ Одобрить", callback_data=f"{CB_PREFIX_USER_ACTION}{action}")])

    if not view.is_blocked:
        rows.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"{CB_PREFIX_USER_ACTION}block_{view.db_id}")])

    if view.is_admin:
        rows.append([InlineKeyboardButton("⬇️ Понизить до менеджера", callback_data=f"{CB_PREFIX_USER_ACTION}demote_manager_{view.db_id}")])
    elif view.is_manager:
        rows.append([InlineKeyboardButton("⬆️ Повысить до админа", callback_data=f"{CB_PREFIX_USER_ACTION}promote_admin_{view.db_id}")])
        rows.append([InlineKeyboardButton("⬇️ Понизить до пользователя", callback_data=f"{CB_PREFIX_USER_ACTION}demote_user_{view.db_id}")])
    else:
        rows.append([InlineKeyboardButton("⬆️ Повысить до менеджера", callback_data=f"{CB_PREFIX_USER_ACTION}promote_manager_{view.db_id}")])

    rows.append([InlineKeyboardButton("🔄 Сбросить регистрацию", callback_data=f"{CB_PREFIX_USER_ACTION}reset_{view.db_id}")])
    rows.append([InlineKeyboardButton("⬅️ К списку", callback_data=f"{CB_PREFIX_USER_DETAILS}{view.db_id}_{source}")])
    rows.append([InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)])
    return InlineKeyboardMarkup(rows)


def build_orders_menu(view: OrdersMenuView) -> InlineKeyboardMarkup:
    rows = []
    for status, count in view.counts.items():
        label = f"{status} ({count})"
        rows.append([InlineKeyboardButton(label, callback_data=f"{CB_PREFIX_ORDERS_BY_STATUS}{status}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_ORDERS)])
    return InlineKeyboardMarkup(rows)


def build_order_list_keyboard(items: list[OrderListView], status: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        f"#{item.order_id} — {item.user_fio} — {item.total_amount:.0f}₽",
        callback_data=f"{CB_PREFIX_ORDER_DETAILS}{item.order_id}_{status}"
    )] for item in items]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_ORDERS)])
    return InlineKeyboardMarkup(rows)


def build_order_details_keyboard(order_id: int, status: str, source: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📍 Принять в работу", callback_data=f"{CB_PREFIX_ORDER_ACTION}accept_{order_id}_{source}")],
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"{CB_PREFIX_ORDER_ACTION}confirm_{order_id}_{source}")],
        [InlineKeyboardButton("📦 В сборку", callback_data=f"{CB_PREFIX_ORDER_ACTION}assemble_{order_id}_{source}")],
        [InlineKeyboardButton("🏃 Готов к выдаче", callback_data=f"{CB_PREFIX_ORDER_ACTION}ready_{order_id}_{source}")],
        [InlineKeyboardButton("🚫 Отменить", callback_data=f"{CB_PREFIX_ORDER_ACTION}cancel_{order_id}_{source}")],
        [InlineKeyboardButton("⬅️ К списку", callback_data=f"{CB_PREFIX_ORDER_DETAILS}{order_id}_{source}")],
        [InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)],
    ]
    return InlineKeyboardMarkup(rows)


def build_settings_menu(view: SettingsMenuView) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"{'🔴' if view.is_auto_approve_enabled else '⚪'} Авто-одобрение",
            callback_data=CB_ADMIN_TOGGLE_AUTO_APPROVE
        )],
        [InlineKeyboardButton("📦 Пункты самовывоза", callback_data=CB_ADMIN_PICKUP_MGMT)],
        [InlineKeyboardButton("🚚 Курьерская доставка", callback_data=CB_ADMIN_COURIER_MGMT)],
        [InlineKeyboardButton("🖼 Логотип визитки", callback_data=CB_ADMIN_LOGO_MGMT)],
        [InlineKeyboardButton("🔗 Прокси", callback_data=CB_ADMIN_PROXY_MGMT)],
        [InlineKeyboardButton("📍 Яндекс доставка", callback_data=CB_ADMIN_SETUP_YANDEX)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_BACK_TO_MAIN)],
    ]
    return InlineKeyboardMarkup(rows)


def build_pickup_menu(view: PickupMenuView) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📍 {p.name}", callback_data=f"apv_{p.idx}")] for p in view.points]  # type: ignore[attr-defined]
    rows.append([InlineKeyboardButton(view.add_button_label, callback_data=CB_ADMIN_PICKUP_ADD)])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(rows)


def build_pickup_item_edit(view: PickupPointView) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"✏️ {f}", callback_data=f"ape_{view.idx}_{f}")] for f in view.editable_fields]
    rows.append([InlineKeyboardButton(
        f"{'🔴 Отключить' if view.is_active else '🟢 Включить'}",
        callback_data=f"apt_{view.idx}"
    )])
    rows.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"apd_{view.idx}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_PICKUP_MGMT)])
    return InlineKeyboardMarkup(rows)


def build_courier_menu(view: CourierMenuView) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"{'🔴 Отключить' if view.is_enabled else '🟢 Включить'} курьерскую доставку",
            callback_data=CB_ADMIN_COURIER_TOGGLE
        )]
    ]
    for city in view.cities:
        rows.append([InlineKeyboardButton(
            f"🌆 {city['name']} — {city['cost']}₽ — {city['days']}дн.",  # type: ignore[index]
            callback_data=f"acc_{city['name']}"  # type: ignore[index]
        )])
    rows.append([InlineKeyboardButton("➕ Добавить город", callback_data="add_city")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(rows)


def build_logo_mgmt(view: LogoSettingsView) -> InlineKeyboardMarkup:
    rows = []
    if view.has_logo:
        rows.append([InlineKeyboardButton("🖼 Заменить фото", callback_data=CB_ADMIN_LOGO_SET)])
        rows.append([InlineKeyboardButton("🗑 Удалить", callback_data="logo_del")])
    else:
        rows.append([InlineKeyboardButton("🖼 Загрузить", callback_data=CB_ADMIN_LOGO_SET)])
    rows.append([InlineKeyboardButton("📝 Текст приветствия", callback_data=CB_ADMIN_WELCOME_TEXT_EDIT)])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(rows)


def build_proxy_mgmt(view: ProxySettingsView) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"{'🔴 Отключить' if view.is_enabled else '🟢 Включить'} прокси",
            callback_data=CB_ADMIN_PROXY_TOGGLE
        )]
    ]
    if view.has_proxy_url:
        rows.append([InlineKeyboardButton("🔗 Изменить URL", callback_data=CB_ADMIN_PROXY_SET)])
        rows.append([InlineKeyboardButton("🗑 Удалить", callback_data="proxy_del")])
    else:
        rows.append([InlineKeyboardButton("🔗 Добавить прокси", callback_data=CB_ADMIN_PROXY_SET)])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(rows)
