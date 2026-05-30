# Tg_bot/handlers/admin_panel.py
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional, cast

import httpx
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import tg_bot.bot_services.product_sync_service as sync_service
from tg_bot.bot_services.base_integration import BaseIntegrationService
from tg_bot.bot_services.communication_service import CommunicationService
from tg_bot.bot_services.notification_service import NotificationService
from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.settings_service import SettingsService
from tg_bot.bot_services.user_service import UserService

# Сервисы
from tg_bot.callback_validator import validate_callback
from tg_bot.decorators import auth_guard
from tg_bot.domain.order import OrderStatus as DomainOrderStatus
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.handlers.order_notifications import notify_user_order_status_changed
from tg_bot.handlers.staff import show_stats

# Клавиатуры и коллбэк-префиксы
from tg_bot.keyboards import (
    CB_ADMIN_BACK_TO_MAIN,
    CB_ADMIN_COMMUNICATION_CENTER,
    CB_ADMIN_COURIER_ADD_CITY,
    CB_ADMIN_COURIER_DEL_CITY,
    CB_ADMIN_COURIER_MGMT,
    CB_ADMIN_COURIER_TOGGLE,
    CB_ADMIN_LOGO_DEL,
    CB_ADMIN_LOGO_MGMT,
    CB_ADMIN_LOGO_SET,
    CB_ADMIN_PICKUP_ADD,
    CB_ADMIN_PICKUP_BACK_TO_ADDR,
    CB_ADMIN_PICKUP_BACK_TO_NAME,
    CB_ADMIN_PICKUP_EDIT,
    CB_ADMIN_PICKUP_MGMT,
    CB_ADMIN_PROXY_DEL,
    CB_ADMIN_PROXY_MGMT,
    CB_ADMIN_PROXY_SET,
    CB_ADMIN_PROXY_TOGGLE,
    CB_ADMIN_SAVE_YANDEX,
    CB_ADMIN_SETTINGS,
    CB_ADMIN_SETUP_YANDEX,
    CB_ADMIN_STATS,
    CB_ADMIN_SYNC_PRODUCTS,
    CB_ADMIN_TOGGLE_AUTO_APPROVE,
    CB_ADMIN_USERS,
    CB_ADMIN_WELCOME_TEXT_EDIT,
    CB_CLOSE_GENERIC,
    CB_PREFIX_ADMIN_PICKUP_DEL,
    CB_PREFIX_ADMIN_PICKUP_TOGGLE,
    CB_PREFIX_ADMIN_PICKUP_VIEW,
    CB_PREFIX_ORDER_ACTION,
    CB_PREFIX_ORDER_DETAILS,
    CB_PREFIX_ORDERS_BY_STATUS,
    CB_PREFIX_THREAD_ACTION,
    CB_PREFIX_THREAD_DETAILS,
    CB_PREFIX_THREAD_PAGE,
    CB_PREFIX_USER_ACTION,
    CB_PREFIX_USER_CONTACT_SUPPORT,
    CB_PREFIX_USER_DETAILS,
    CB_PREFIX_USERS_BY_ROLE,
    CB_PREFIX_USERS_BY_STATUS,
    CB_USER_SHOW_MAIN_MENU,
    CB_USER_VIEW_THREAD,
    get_admin_courier_mgmt_keyboard,
    get_admin_logo_mgmt_keyboard,
    get_admin_main_keyboard,
    get_admin_orders_menu_keyboard,
    get_admin_pickup_mgmt_keyboard,
    get_admin_proxy_mgmt_keyboard,
    get_admin_settings_keyboard,
    get_admin_users_keyboard,
    get_logged_out_keyboard,
    get_order_details_keyboard,
    get_order_list_keyboard,
    get_pickup_item_edit_keyboard,
    get_pickup_wizard_keyboard,
    get_thread_view_keyboard,
    get_threads_list_keyboard,
    get_user_details_keyboard,
    get_user_list_keyboard,
    get_user_welcome_keyboard,
    get_yandex_confirm_keyboard,
)
from tg_bot.models import OrderStatus, SenderRole, UserRole, UserStatus
from utils.config_pusher import push_config_to_integration
from utils.env_utils import update_env_variable

# Состояния для настройки курьера
C_CITY, C_COST, C_DAYS = range(100, 103)
# Состояния для pickup crud (универсальные)
P_NAME, P_ADDR, P_SCHED, P_DAYS, P_EDIT_VAL = range(110, 115)
AWAITING_LOGO_PHOTO = 120
AWAITING_WELCOME_TEXT = 121
AWAITING_WELCOME_MEDIA = 122
AWAITING_PROXY_URL = 123
logger = logging.getLogger(__name__)
KOJO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ENV_PATH = KOJO_ROOT / "deploy" / ".env"


# Главные обработчики
async def _delete_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 5) -> Any:
    """Фоновая задача для удаления сообщения."""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

async def _render_thread_interface(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, thread_id: int, page: int = 0) -> Any:  # noqa: E501
    """
    Универсальная функция отрисовки интерфейса чата (история + кнопки).
    """
    # 1. инициализируем сервис
    comms_service: CommunicationService = context.bot_data['communication_service']

    # 2. получаем сообщения и сам тред
    messages = await comms_service.get_messages_for_thread(thread_id)
    thread = await comms_service.get_or_create_thread_by_id(thread_id)

    if not thread:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text="⚠️ Чат не найден в базе данных.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_COMMUNICATION_CENTER)]])  # noqa: E501
            )
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")
        return

    # Если сообщений нет, но тред есть — показываем пустой чат
    if not messages:
        # Можно показать просто заголовок
        pass

    # 3. форматирование сообщений (html)
    import html
    formatted_blocks = []

    # Если сообщений нет, добавим заглушку
    if not messages:
        formatted_blocks.append("<i>(История сообщений пуста)</i>")
    else:
        for msg in messages:
            sender = "Вы" if msg.sender_role == SenderRole.STAFF else "Клиент"
            icon = "👨‍💼" if msg.sender_role == SenderRole.STAFF else "👤"
            time_str = msg.created_at.strftime('%d.%m %H:%M')
            text_safe = html.escape(msg.text)
            formatted_blocks.append(f"<b>{icon} {sender}</b> <i>({time_str})</i>:\n{text_safe}\n\n")

    # 4. пагинация (разбивка на страницы)
    MAX_CHARS = 3800
    pages: list[str] = []
    current_page_blocks: list[str] = []
    current_len = 0

    # Идем с конца (от новых к старым)
    for block in reversed(formatted_blocks):
        if current_len + len(block) > MAX_CHARS:
            pages.append("".join(reversed(current_page_blocks)))
            current_page_blocks = [block]
            current_len = len(block)
        else:
            current_page_blocks.append(block)
            current_len += len(block)

    if current_page_blocks:
        pages.append("".join(reversed(current_page_blocks)))

    total_pages = len(pages)
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0

    # 5. сборка текста
    # Если страниц нет (пустой чат), создаем одну пустую страницу
    chat_text = pages[page] if pages else "<i>Сообщений нет.</i>"

    order_num = getattr(thread, 'order_id', '???')
    header = f"💬 <b>Заказ #{order_num}</b> (Стр. {page + 1}/{total_pages})\n────────────────\n"
    final_text = header + chat_text

    # Помечаем прочитанным при открытии первой страницы
    if page == 0:
        await comms_service.update_thread_status(thread_id, is_read=True)

    # 6. отправка
    reply_markup = get_thread_view_keyboard(thread, page, total_pages)

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=final_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Ошибка рендера чата: {e}")


@auth_guard(staff_only=True)
async def panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Главное меню админ-панели с защитой от ошибок рендера медиа."""
    if update.message is None:
        return
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    comms_service: CommunicationService = context.bot_data['communication_service']
    threads = await comms_service.get_all_threads_sorted()
    unread_count = sum(1 for t in threads if not t.is_read)

    user_data: dict[str, Any] = context.user_data or {}
    text = "<b>Панель управления ботом:</b>"
    reply_markup = get_admin_main_keyboard(unread_messages_count=unread_count)

    query = update.callback_query
    if query is None:
        return

    if query:
        await query.answer()
        msg = query.message
        if msg is None:
            return
        # Если переходим из видео/фото экрана — удаляем старое
        if msg.photo or msg.video or msg.animation:
            try:
                await msg.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

            await cleanup_previous_menu(context, user_id)
            sent_msg = await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

            user_data['last_global_menu_id'] = sent_msg.message_id
            await context.bot_data['user_service'].save_registration_message_id(user_id, sent_msg.message_id)
        else:
            # Обычный edit
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        # Если вызвано командой /panel
        if update.message:
            try:
                await update.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

        await cleanup_previous_menu(context, user_id)
        sent_msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        user_data['last_global_menu_id'] = sent_msg.message_id
        await context.bot_data['user_service'].save_registration_message_id(user_id, sent_msg.message_id)

@auth_guard(staff_only=True)
async def show_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает меню управления пользователями со всеми счетчиками."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user_service: UserService = context.bot_data['user_service']

    # Считаем количество пользователей в каждом статусе и роли
    pending_users = await user_service.get_users_by_criteria(status=UserStatus.PENDING)
    approved_users = await user_service.get_users_by_criteria(status=UserStatus.APPROVED)
    blocked_users = await user_service.get_users_by_criteria(status=UserStatus.BLOCKED)

    user_role_users = await user_service.get_users_by_criteria(role=UserRole.USER)
    manager_users = await user_service.get_users_by_criteria(role=UserRole.MANAGER)
    admin_users = await user_service.get_users_by_criteria(role=UserRole.ADMIN)

    text = "Раздел управления пользователями:"
    reply_markup = get_admin_users_keyboard(
        pending_count=len(pending_users),
        approved_count=len(approved_users),
        blocked_count=len(blocked_users),
        user_count=len(user_role_users),
        manager_count=len(manager_users),
        admin_count=len(admin_users)
    )
    await query.edit_message_text(text, reply_markup=reply_markup)


@auth_guard(staff_only=True)
async def show_user_list_by_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список пользователей по роли. Если пуст — редирект в меню."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    role_str = query.data.replace(CB_PREFIX_USERS_BY_ROLE, '')
    role = UserRole(role_str)

    user_service: UserService = context.bot_data['user_service']
    users = await user_service.get_users_by_criteria(role=role)

    if not users:
        logger.info(f"[Admin UI] Role list empty: {role.value}. Redirecting to main users menu.")
        # Показываем уведомление и сразу перекидываем в меню управления
        await query.answer(f"📭 Список «{role.value}» пуст.", show_alert=False)
        return await show_users_menu(update, context)

    await query.answer()
    text = f"Пользователи с ролью «{role.value}»:"
    reply_markup = get_user_list_keyboard(users, f"role_{role.value}")

    await query.edit_message_text(text, reply_markup=reply_markup)


@auth_guard(staff_only=True)
async def show_user_list_by_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список пользователей по статусу. Если пуст — редирект в меню."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    status_str = query.data.replace(CB_PREFIX_USERS_BY_STATUS, '')
    status = UserStatus(status_str)

    user_service: UserService = context.bot_data['user_service']
    users = await user_service.get_users_by_criteria(status=status)

    if not users:
        logger.info(f"[Admin UI] Status list empty: {status.value}. Redirecting.")
        # Показываем уведомление и возвращаем в корень управления
        await query.answer(f"📭 Категория «{status.value}» пуста.", show_alert=False)
        return await show_users_menu(update, context)

    await query.answer()
    text = f"Пользователи в статусе «{status.value}»:"
    reply_markup = get_user_list_keyboard(users, status.value)

    await query.edit_message_text(text, reply_markup=reply_markup)


@auth_guard(staff_only=True)
async def show_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_override: Optional[int] = None, source_override: Optional[str] = None) -> Any:  # noqa: E501
    """Показывает детальную карточку пользователя. Поддерживает прямой вызов и вызов через callback."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    user_data: dict[str, Any] = context.user_data or {}

    # 1. определяем id и источник (либо из аргументов, либо из callback_data)
    if user_id_override:
        user_id = user_id_override
        source_list = source_override or user_data.get('last_user_view_source', 'approved')
    else:
        payload = query.data.replace(CB_PREFIX_USER_DETAILS, '')
        try:
            user_id_str, source_list = payload.split('_', 1)
            user_id = int(user_id_str)
            # Запоминаем источник, чтобы действия над юзером не теряли навигацию
            user_data['last_user_view_source'] = source_list
        except (ValueError, IndexError):
            logger.error(f"Error parsing user details data: {query.data}")
            await query.edit_message_text("❌ Ошибка данных пользователя.")
            return

    # 2. получаем данные
    user_service: UserService = context.bot_data['user_service']
    user = await user_service.get_user_by_db_id(user_id)

    if not user:
        await query.edit_message_text("Ошибка: пользователь не найден.")
        return

    # 3. локализация для ui
    status_map = {
        UserStatus.APPROVED: "✅ Авторизован",
        UserStatus.PENDING: "⏳ В ожидании",
        UserStatus.BLOCKED: "🚫 Заблокирован"
    }
    role_map = {
        UserRole.USER: "👤 Пользователь",
        UserRole.MANAGER: "👨‍💼 Менеджер",
        UserRole.ADMIN: "👑 Администратор"
    }
    readable_status = status_map.get(user.status, user.status.value)
    readable_role = role_map.get(user.role, user.role.value)

    text = (
        f"👤 <b>Карточка пользователя</b>\n\n"
        f"<b>ФИО:</b> {user.fio}\n"
        f"<b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"<b>Телефон:</b> <code>{user.phone}</code>\n"
        f"<b>Email:</b> <code>{user.email}</code>\n\n"
        f"<b>Статус:</b> {readable_status}\n"
        f"<b>Роль:</b> {readable_role}"
    )

    admin_ids = context.bot_data.get('admin_ids', [])
    reply_markup = get_user_details_keyboard(user, source_list, super_admin_ids=admin_ids)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    logger.debug("Admin UI: Card refreshed for %s", user_id)


@auth_guard(staff_only=True)
@validate_callback
async def handle_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Ультимативный обработчик действий над пользователями.
    Реализует: иерархию ролей, защиту ADMIN_IDS и интерактивные уведомления.
    """
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    # 1. парсинг данных
    payload = query.data.replace(CB_PREFIX_USER_ACTION, '')
    try:
        # Используем rsplit, чтобы забрать id с самого конца строки
        action, user_id_str = payload.rsplit('_', 1)
        user_id = int(user_id_str)
        logger.debug("Admin Action Parsed: action='%s', user_id=%s", action, user_id)
    except (ValueError, IndexError):
        logger.error(f"Ошибка парсинга callback_data: {payload}")
        await query.answer("⚠️ Ошибка данных", show_alert=True)
        return

    user_service: UserService = context.bot_data['user_service']
    admin_ids = context.bot_data.get('admin_ids', [])
    user_to_update = await user_service.get_user_by_db_id(user_id)

    if not user_to_update:
        await query.answer("Пользователь не найден в базе данных.", show_alert=True)
        return

    # 2. [безопасность] защита супер-админов (тех, кто в admin_ids)
    if user_to_update.telegram_id in admin_ids and action != "approve":
        await query.answer("🛑 Критическая защита: Действия над владельцем системы запрещены.", show_alert=True)
        return

    notification_text = None
    reply_markup = None
    target_tg_id = user_to_update.telegram_id

    # Подготовка общих кнопок (импорты из keyboards)
    from tg_bot.keyboards import CB_CLOSE_GENERIC
    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]])
    menu_btn = get_user_welcome_keyboard() # Кнопка "Перейти в меню"
    login_btn = get_logged_out_keyboard()   # Кнопка "Войти заново"

    # 3. логика изменений и выбор кнопок для уведомления
    if action == "approve":
        await user_service.update_user_status_by_db_id(user_id, UserStatus.APPROVED)
        notification_text = "✅ Ваш аккаунт был одобрен администратором. Добро пожаловать!"
        reply_markup = menu_btn

    elif action == "block":
        await user_service.update_user_status_by_db_id(user_id, UserStatus.BLOCKED)
        notification_text = "🚫 Ваш аккаунт был заблокирован администратором. Свяжитесь с поддержкой для уточнения причин."  # noqa: E501
        reply_markup = close_btn

    elif action == "promote_manager":
        await user_service.update_user_role(user_id, UserRole.MANAGER)
        notification_text = "👨‍💼 Вам предоставлены права <b>Менеджера</b>. Теперь вам доступна панель управления персоналом."  # noqa: E501
        reply_markup = menu_btn

    elif action == "promote_admin":
        await user_service.update_user_role(user_id, UserRole.ADMIN)
        notification_text = "👑 Вам назначена роль <b>Администратора</b>. У вас есть полный доступ к настройкам бота."
        reply_markup = menu_btn

    elif action == "demote_manager":
        await user_service.update_user_role(user_id, UserRole.MANAGER)
        notification_text = "⚠️ Ваш уровень доступа изменен на <b>Менеджер</b>."
        reply_markup = menu_btn

    elif action == "demote_user":
        await user_service.update_user_role(user_id, UserRole.USER)
        notification_text = "👤 Ваши права персонала отозваны. Вы переведены в статус обычного <b>Пользователя</b>."
        reply_markup = menu_btn

    elif action == "reset":
        await user_service.logout_user(target_tg_id, clear_data=False)
        notification_text = "♻️ <b>Ваша регистрация была удалена администратором.</b>\n\nПожалуйста, пройдите авторизацию заново."  # noqa: E501
        reply_markup = login_btn

    elif action == "gdpr_delete":
        anonymized = await user_service.anonymize_user(target_tg_id, update.effective_user.id)  # type: ignore[union-attr]
        if anonymized:
            await query.answer(
                "✅ GDPR-анонимизация выполнена. Все PII удалены, заказы сохранены.",
                show_alert=True,
            )
            logger.info(
                f"GDPR delete completed for user {target_tg_id} "
                f"by admin {update.effective_user.id}"  # type: ignore[union-attr]
            )
            await show_user_details(update, context, user_id_override=user_id)
            return
        else:
            await query.answer("❌ Пользователь не найден.", show_alert=True)
            return

    # 4. отправка уведомления пользователю
    if notification_text:
        try:
            logger.info(f"[Admin] UI-Update for User {target_tg_id}: '{action}'")

            # Пытаемся удалить старое окно (якорь) пользователя
            if user_to_update.registration_message_id:
                try:
                    await context.bot.delete_message(
                        chat_id=target_tg_id,
                        message_id=user_to_update.registration_message_id
                    )
                    logger.debug(
                        "UI Cleanup: Deleted old anchor %s for user %s",
                        user_to_update.registration_message_id,
                        target_tg_id,
                    )
                except (ConnectionError, TimeoutError, OSError) as e:
                    logger.debug(f"Could not delete old anchor for user {target_tg_id}: {e}")

            # Отправляем новое уведомление
            sent_msg = await context.bot.send_message(
                chat_id=target_tg_id,
                text=notification_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

            # Сохраняем id нового сообщения как новый якорь в бд
            await user_service.save_registration_message_id(target_tg_id, sent_msg.message_id)

            await query.answer(f"Выполнено: {action}")

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"Не удалось уведомить пользователя {target_tg_id}: {e}")
            await query.answer("Действие выполнено, но не удалось зачистить окно пользователя.", show_alert=True)

    # 5. возврат в карточку (одно окно)
    logger.debug("Admin Action Completed: %s on DB_ID %s", action, user_id)
    # Передаем user_id явно, чтобы избежать ошибки парсинга query.data
    await show_user_details(update, context, user_id_override=user_id)


@auth_guard(staff_only=True)
async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Меню настроек. Исправлен переход из медиа-сообщений в текстовые."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    await query.answer()
    user_data: dict[str, Any] = context.user_data or {}

    settings_service: SettingsService = context.bot_data['settings_service']
    auto_approve_str = await settings_service.get_setting('auto_approve_new_users', 'false')

    text = "⚙️ <b>Настройки бота:</b>"
    reply_markup = get_admin_settings_keyboard(is_auto_approve_enabled=(auto_approve_str == 'true'))

    # [критично] проверяем, не пытаемся ли мы отредактировать видео/фото в текст
    msg = query.message
    if msg is None:
        return
    is_media = bool(msg.photo or msg.video or msg.animation)

    if is_media:
        # Если текущее окно — медиа, удаляем его и шлем новое текстовое
        try:
            await msg.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

        await cleanup_previous_menu(context, user_id)

        sent_msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        user_data['last_global_menu_id'] = sent_msg.message_id
        await context.bot_data['user_service'].save_registration_message_id(user_id, sent_msg.message_id)
    else:
        # Если это был текст — просто редактируем
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


@validate_callback
@auth_guard(staff_only=True)
async def toggle_auto_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Переключает флаг авто-одобрения."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    settings_service: SettingsService = context.bot_data['settings_service']
    current_value = await settings_service.get_setting('auto_approve_new_users', 'false')

    new_value = 'false' if current_value == 'true' else 'true'
    await settings_service.set_setting('auto_approve_new_users', new_value)

    # Обновляем меню, чтобы показать новое состояние
    await show_settings_menu(update, context)


@auth_guard(staff_only=True)
async def show_orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает меню управления заказами со счетчиками по статусам."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    order_service: OrderService = context.bot_data['order_service']
    counts = await order_service.get_order_counts_by_status()

    text = "🧾 Управление заказами:"
    reply_markup = get_admin_orders_menu_keyboard(counts)  # type: ignore[arg-type]

    await query.edit_message_text(text, reply_markup=reply_markup)


@auth_guard(staff_only=True)
async def show_order_list_by_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список заказов в выбранном статусе."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    status_name = query.data.replace(CB_PREFIX_ORDERS_BY_STATUS, '')
    status_enum = DomainOrderStatus[status_name]

    order_service: OrderService = context.bot_data['order_service']
    orders = await order_service.get_orders_by_statuses([status_enum])

    if not orders:
        await query.answer(f"Заказов в статусе «{status_enum.value}» нет.", show_alert=True)
        return

    text = f"Заказы в статусе «{status_enum.value}»:"
    reply_markup = get_order_list_keyboard(orders, status_name)  # type: ignore[arg-type]

    await query.edit_message_text(text, reply_markup=reply_markup)


@auth_guard(staff_only=True)
async def show_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id_override: Optional[int] = None) -> Any:  # noqa: E501
    """Показывает детальную информацию о заказе (Admin версия)."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    # Логика определения id заказа
    if order_id_override:
        order_id = order_id_override
        source_list = "PAID" # Фолбек для списка
    else:
        # Парсим из callback_data: admin_order_details_44_awaiting_payment
        payload = query.data.replace(CB_PREFIX_ORDER_DETAILS, '')
        try:
            # Используем rsplit, так как статус в конце тоже может содержать '_'
            order_id_str, source_list = payload.split('_', 1)
            order_id = int(order_id_str)
        except (ValueError, IndexError):
            logger.error(f"Failed to parse order ID from payload: {payload}")
            await query.edit_message_text("❌ Ошибка данных заказа.")
            return

    order_service: OrderService = context.bot_data['order_service']
    user_service: UserService = context.bot_data['user_service']

    details = await order_service.get_full_order_details(order_id)
    if not details:
        await query.edit_message_text("Ошибка: Заказ не найден.")
        return

    order, items = details
    customer = await user_service.get_user(order.user_id)

    # Формируем данные (html)
    customer_info = f"👤 <b>Клиент:</b> {customer.fio} (<code>{customer.telegram_id}</code>)" if customer else "👤 <b>Клиент:</b> Не найден"  # noqa: E501

    items_text = ""
    for item in items:
        items_text += f"  • ID:{item.product_id} | {item.quantity} шт. x {item.price}₽\n"

    delivery_info = f"🚚 <b>Способ:</b> {getattr(order, 'delivery_type', 'pickup')}\n"
    if getattr(order, 'delivery_point_id', None):
        delivery_info += f"📍 <b>ПВЗ:</b> <code>{getattr(order, 'delivery_point_id', '')}</code>\n"
    if getattr(order, 'delivery_address', None):
        delivery_info += f"🏢 <b>Адрес:</b> {getattr(order, 'delivery_address', '')}\n"
    if getattr(order, 'delivery_price', None):
        delivery_info += f"💸 <b>Доставка:</b> {getattr(order, 'delivery_price', 0)}₽\n"

    type_text = "🎁 <b>Тип:</b> Подарок" if getattr(order, "is_gift", False) else "🛍 <b>Тип:</b> Для себя"
    comment_text = f'\n💬 <b>Коммент:</b> {getattr(order, "gift_comment", "")}' if getattr(order, "gift_comment", "") else ""  # noqa: E501

    rating_text = ""
    order_rating = getattr(order, 'rating', None)
    if order_rating:
        rating_text = f"\n\n⭐️ <b>Оценка:</b> {'⭐' * order_rating}"
        order_rating_comment = getattr(order, 'rating_comment', None)
        if order_rating_comment:
            rating_text += f"\n<i>«{order_rating_comment}»</i>"

    text = (
        f"🧾 <b>Заказ #{order.id}</b>\n\n"
        f"{customer_info}\n"
        f"📅 <b>Дата:</b> {order.created_at.strftime('%d.%m.%Y %H:%M') if order.created_at else 'N/A'}\n"
        f"💰 <b>Сумма:</b> {order.total_amount}₽\n"
        f"⭐ <b>Статус:</b> <code>{order.status.value}</code>\n\n"
        f"{delivery_info}"
        f"{type_text}{comment_text}"
        f"{rating_text}\n\n"
        f"📋 <b>Состав:</b>\n{items_text}"
    )

    reply_markup = get_order_details_keyboard(order, source_list)  # type: ignore[arg-type]

    # Обновляем старое сообщение или шлем новое
    try:
        if query and query.message:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(update.effective_user.id, text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)  # noqa: E501
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Render Error: {e}")


# Tg_bot/handlers/admin_panel.py

@auth_guard(staff_only=True)
async def handle_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Обрабатывает смену статуса заказа менеджером."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    # 1. безопасный парсинг callback_data
    payload = query.data.replace(CB_PREFIX_ORDER_ACTION, '')
    try:
        # Используем rsplit, чтобы забрать id заказа с конца
        action, order_id_str = payload.rsplit('_', 1)
        order_id = int(order_id_str)
        logger.info(f"Admin action '{action}' for order #{order_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing admin action '{payload}': {e}")
        await query.answer("⚠️ Ошибка: неверный формат данных.", show_alert=True)
        return

    # 2. инициализация сервисов
    order_service: OrderService = context.bot_data['order_service']

    # Маппинг действий на статусы
    status_map = {
        "set_paid": OrderStatus.PAID,
        "set_shipped": OrderStatus.SHIPPED,
        "set_ready": OrderStatus.READY_FOR_PICKUP,
        "set_completed": OrderStatus.COMPLETED,
        "set_cancelled": OrderStatus.CANCELLED,
    }

    new_status = status_map.get(action)
    if not new_status:
        logger.warning(f"Unknown admin action: {action}")
        return

    # 3. получаем детали заказа до обновления (нужны для создания заявки в яндексе)
    order_data = await order_service.get_full_order_details(order_id)
    if not order_data:
        await query.answer("Заказ не найден в БД.")
        return
    current_order, items = order_data

    # 4. обновляем статус в базе
    updated_order = await order_service.update_order_status(order_id, new_status)  # type: ignore[arg-type]

    if updated_order:
        # 5. логика авто-доставки (яндекс / сдэк)
        # Если статус меняется на оплачен и это пвз
        if new_status == OrderStatus.PAID and getattr(updated_order, 'delivery_type', '') in ['cdek_point', 'yandex_point']:  # noqa: E501
            logger.info(f"🚀 Triggering automated delivery creation for order #{order_id}")
            # Запускаем в фоне, чтобы не тормозить ui админа
            asyncio.create_task(create_delivery_request(updated_order, items, context))

        # 6. уведомление пользователя
        await notify_user_order_status_changed(
            context=context,
            user_id=updated_order.user_id,
            order_id=order_id,
            new_status=new_status.value,
        )

        # 7. обновляем интерфейс админа (одно окно)
        await query.answer(f"Статус: {new_status.value}")
        await show_order_details(update, context, order_id_override=order_id)
    else:
        await query.answer("❌ Ошибка обновления статуса.", show_alert=True)


async def create_yandex_request(order_data: dict[str, Any], context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Принимает словарь с данными и отправляет в Integration Service."""
    try:
        integration_url = context.bot_data.get('integration_url')
        bot_id = context.bot_data.get('bot_id_for_quart')

        # Формируем payload, который ожидает наш интегратор (routes/yandex_routes.py)
        payload = {
            "bot_id": bot_id,
            "order_id": order_data["order_id"],
            "client_name": order_data["customer_name"],
            "client_phone": order_data["customer_phone"],
            "client_address": order_data["customer_address"], # <--- Передаем адрес
            "point_id": order_data["delivery_point_id"],
            "items": order_data["items"],
            "total_cost": order_data["total_amount"]
        }

        logger.info(f"🚀 Sending Order #{order_data['order_id']} to Integration Service...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{integration_url}/api/delivery/yandex-create-request",
                json=payload
            )

            if response.status_code in [200, 201]:
                result = response.json()
                logger.info(f"✅ Яндекс успешно создал Claim: {result.get('yandex_claim_id')}")
                return True
            else:
                logger.error(f"❌ Яндекс отклонил запрос: {response.status_code} - {response.text}")
                return False

    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Error calling Integration Service for Yandex: {e}", exc_info=True)
        return False


async def create_delivery_request(order: Any, items: Any, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Создает заявку в службе доставки (СДЭК или Яндекс) при смене статуса заказа на 'оплачен'
    Возвращает True при успехе, False — при ошибке.
    """
    logger.info(f'Попытка создания заявки в доставке для заказа #{order.id}, тип доставки: {getattr(order, "delivery_type", "")}')  # noqa: E501

    try:
        # Получаем сервис пользователя
        user_service = context.bot_data.get('user_service')
        if not user_service:
            logger.error("Сервис пользователей не доступен в bot_data")
            return False

        user = await user_service.get_user(order.user_id)
        if not user:
            logger.error(f"Не найден пользователь с ID {order.user_id} для заказа #{order.id}")
            return False

        # Подготовка данных для api доставки
        order_data = {
            "order_id": order.id,
            "customer_name": user.fio or f"Клиент {user.telegram_id}",
            "customer_phone": user.phone,
            "customer_address": getattr(order, "delivery_address", ""),  # Важно: адрес из заказа
            "delivery_type": getattr(order, "delivery_type", ""),
            "delivery_point_id": getattr(order, "delivery_point_id", None),
            "total_amount": order.total_amount,        # Оставляем как есть — пусть API сам конвертирует
            "delivery_price": getattr(order, "delivery_price", 0),    # То же самое
            "items": []
        }

        # Наполняем список товаров
        for item in items:
            order_data["items"].append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": item.price
            })

        # Выбор службы доставки
        if getattr(order, "delivery_type", "") == 'cdek_point':
            success = await create_cdek_request(order_data, context)
        elif getattr(order, "delivery_type", "") == 'yandex_point':
            success = await create_yandex_request(order_data, context)
        else:
            logger.warning(f'Неизвестный тип доставки для заказа #{order.id}: {getattr(order, "delivery_type", "")}')
            return False

        # Обработка результата
        if success:
            logger.info(f"✅ Заявка в доставке успешно создана для заказа #{order.id}")
            logger.info("Admin: Order %s delivery request succeeded — status/tracking update not configured", order.id)
            return True
        else:
            logger.error(f"❌ Не удалось создать заявку в доставке для заказа #{order.id}")
            return False

    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(
            f"❗️ Критическая ошибка при создании заявки в доставке для заказа #{order.id}: {e}",
            exc_info=True
        )
        return False


async def create_cdek_request(order_data: dict[str, Any], context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Создает заявку в СДЭК через existing integration service API
    """
    try:
        # Используем существующий delivery_service для взаимодействия с integration service
        delivery_service = context.bot_data.get('delivery_service')
        if not delivery_service:
            logger.error("Delivery service недоступен")
            return False

        # Подготовим данные для существующего api
        payload = {
            "order_id": order_data["order_id"],
            "recipient_name": order_data["customer_name"],
            "recipient_phone": order_data["customer_phone"],
            "pvz_code": order_data["delivery_point_id"],
            "items": order_data["items"],
            "total_cost": order_data["total_amount"],
            "delivery_cost": order_data["delivery_price"],
            # Добавим все необходимые данные для создания заявки
            "order_data": order_data
        }

        # Делаем вызов через уже существующую структуру в delivery_service
        # Используем методы из baseintegrationservice
        # На самом деле, нам нужно использовать внутренние методы delivery_service
        # Или воспользоваться уже существующими api в integration service

        # В настоящее время в delivery_service нет прямого метода для создания заявки,
        # Но мы можем использовать _post_request из baseintegrationservice напрямую

        # Попробуем вызвать через те же эндпоинты, что и при инициализации сессии
        import httpx
        integration_url = context.bot_data.get('integration_url')
        bot_id = context.bot_data.get('bot_id_for_quart')

        # Используем тот же подход, что и в других api вызовах
        full_payload = {
            "bot_id": bot_id,
            **payload
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Используем существующий endpoint если такой есть, или вызываем напрямую cdek api
            # Так как в текущей архитектуре таких эндпоинтов нет, создадим прямой вызов к cdek api
            # Но для интеграции с нашей системой, нужно сначала создать эндпоинт в integration service
            # Пока что используем существующий паттерн

            # Делаем вызов в integration service для создания заказа в cdek
            response = await client.post(
                f"{integration_url}/api/delivery/cdek-create-request",
                json=full_payload
            )

            if response.status_code in [200, 201]:
                result = response.json()
                logger.info(f"Заявка в СДЭК создана успешно для заказа #{order_data['order_id']}: {result}")
                return True
            elif response.status_code == 400:
                logger.warning(f"Неверные данные для создания заявки в СДЭК: {response.text}")
                return False
            else:
                logger.error(f"Ошибка при создании заявки в СДЭК: {response.status_code}, {response.text}")
                return False

    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Ошибка при вызове API СДЭК: {e}", exc_info=True)
        return False


@auth_guard(staff_only=True)
async def show_communication_center(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список всех чатов, отсортированный по правилам."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    comms_service: CommunicationService = context.bot_data['communication_service']
    threads = await comms_service.get_all_threads_sorted()

    if not threads:
        text = "📬 Сообщений от клиентов пока нет."
    else:
        text = "📬 Все чаты с клиентами (важные и непрочитанные вверху):"

    reply_markup = get_threads_list_keyboard(threads)
    await query.edit_message_text(text, reply_markup=reply_markup)


@auth_guard(staff_only=True)
async def show_thread_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Входная точка для просмотра чата (парсит ID и вызывает рендер)."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    data = query.data
    page = 0

    # Разбираем callback_data
    if data.startswith(CB_PREFIX_THREAD_PAGE):
        payload = data.replace(CB_PREFIX_THREAD_PAGE, '')
        thread_id_str, page_str = payload.split('_')
        thread_id = int(thread_id_str)
        page = int(page_str)
    else:
        thread_id = int(data.replace(CB_PREFIX_THREAD_DETAILS, ''))
        page = 0

    if query.message is None:
        return
    # Вызываем универсальный рендерер
    await _render_thread_interface(context, query.message.chat_id, query.message.message_id, thread_id, page)


@validate_callback
@auth_guard(staff_only=True)
async def handle_thread_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Обрабатывает действия с чатом (пометить важным/непрочитанным)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    payload = query.data.replace(CB_PREFIX_THREAD_ACTION, '')
    action, thread_id_str = payload.split('_', 1)
    thread_id = int(thread_id_str)

    comms_service: CommunicationService = context.bot_data['communication_service']
    thread = await comms_service.get_or_create_thread_by_id(thread_id)
    if thread is None:
        return

    if action == "toggle_important":
        await comms_service.update_thread_status(thread_id, is_important=not thread.is_important)
        await query.answer("Статус 'важное' изменен")
    elif action == "mark_unread":
        await comms_service.update_thread_status(thread_id, is_read=False)
        await query.answer("Чат помечен как непрочитанный")
        # Возвращаемся к списку, т.к. текущий просмотр завершен
        return await show_communication_center(update, context)

    # Обновляем сообщение с чатом, чтобы показать изменения
    await show_thread_view(update, context)

# Логика для ответа персонала клиенту
AWAITING_STAFF_REPLY = 0
async def prompt_for_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Запрашивает ответ, обновляя текущее меню."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    payload = query.data.replace(CB_PREFIX_THREAD_ACTION, '')
    # Action (reply) нам не нужен, нужен id
    _, thread_id_str = payload.split('_')
    thread_id = int(thread_id_str)

    user_data: dict[str, Any] = context.user_data or {}
    user_data['reply_thread_id'] = thread_id
    # Запоминаем id сообщения меню, чтобы потом его обновить
    if query.message is None:
        return
    user_data['admin_menu_msg_id'] = query.message.message_id

    # Кнопка отмены возвращает в режим просмотра (через нашу новую функцию)
    # Но так как мы в conversationhandler, мы ловим колбек в cancel_reply
    cancel_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Отмена", callback_data="cancel_reply_action")
    ]])

    text = (
        "✍️ <b>Режим ответа</b>\n\n"
        "Введите сообщение для клиента. Оно будет отправлено мгновенно.\n"
        "Для выхода нажмите кнопку ниже."
    )

    await query.edit_message_text(text, reply_markup=cancel_keyboard, parse_mode=ParseMode.HTML)
    return AWAITING_STAFF_REPLY


async def handle_staff_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Принимает текст, отправляет клиенту (с кнопками Ответить/История), удаляет ввод."""
    if update.effective_chat is None:
        return
    if update.effective_user is None:
        return ConversationHandler.END
    if update.message is None or update.message.text is None:
        return ConversationHandler.END
    staff_reply_text = update.message.text
    user_data: dict[str, Any] = context.user_data or {}
    thread_id = user_data.get('reply_thread_id')
    menu_msg_id = user_data.get('admin_menu_msg_id')

    # 1. удаляем сообщение админа
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    if not thread_id:
        await update.message.reply_text("Ошибка контекста. Начните заново.")
        return ConversationHandler.END

    comms_service: CommunicationService = context.bot_data['communication_service']

    # 2. получаем данные для отправки
    customer_id = await comms_service.get_customer_id_from_thread(thread_id)
    thread = await comms_service.get_or_create_thread_by_id(thread_id)
    if thread is None or customer_id is None:
        await update.message.reply_text("Ошибка: чат или пользователь не найден.")
        return ConversationHandler.END

    # Сохраняем в базу
    await comms_service.add_message_by_thread_id(
        thread_id=thread_id,
        sender_id=update.effective_user.id,
        sender_role=SenderRole.STAFF,
        text=staff_reply_text
    )

    try:
        user_message = f"💬 *Сообщение от поддержки по заказу #{thread.order_id}:*\n\n{staff_reply_text}"

        user_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Ответить", callback_data=f"{CB_PREFIX_USER_CONTACT_SUPPORT}{thread.order_id}")],
            [InlineKeyboardButton("📜 История переписки", callback_data=f"{CB_USER_VIEW_THREAD}{thread.order_id}")],
            [InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]
        ])

        await context.bot.send_message(
            chat_id=customer_id,
            text=user_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=user_markup
        )

        # 3. тост для админа
        success_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Ответ отправлен клиенту!"
        )
        asyncio.create_task(_delete_after_delay(context, update.effective_chat.id, success_msg.message_id, 3))

    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Не удалось отправить сообщение клиенту: {e}")
        err_msg = await context.bot.send_message(update.effective_chat.id, "⚠️ Не удалось отправить (клиент заблокировал бота?), но в базу сохранено.")  # noqa: E501
        asyncio.create_task(_delete_after_delay(context, update.effective_chat.id, err_msg.message_id, 5))

    # 4. обновляем меню админа
    if menu_msg_id:
        await _render_thread_interface(context, update.effective_chat.id, menu_msg_id, thread_id, page=0)

    return ConversationHandler.END


async def cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Отменяет режим ответа и возвращает историю."""
    # Может быть вызван и командой, и кнопкой
    if update.message is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    if update.callback_query:
        await update.callback_query.answer()
        msg_obj = update.callback_query
        if msg_obj is None or msg_obj.message is None:
            return
        chat_id = msg_obj.message.chat_id
    else:
        chat_id = update.message.chat_id
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    thread_id = user_data.get('reply_thread_id')
    menu_msg_id = user_data.get('admin_menu_msg_id')

    if thread_id and menu_msg_id:
        await _render_thread_interface(context, chat_id, menu_msg_id, thread_id, page=0)
    else:
        await context.bot.send_message(chat_id, "Действие отменено.")

    return ConversationHandler.END

# Создаем сам conversationhandler
staff_reply_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(prompt_for_reply, pattern=f"^{CB_PREFIX_THREAD_ACTION}reply_")],
    states={
        AWAITING_STAFF_REPLY: [
            # Обработка текста
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_staff_reply),
            # Обработка кнопки "отмена" (которая внутри сообщения)
            CallbackQueryHandler(cancel_reply, pattern="^cancel_reply_action$")
        ],
    },
    fallbacks=[CommandHandler("cancel_reply", cancel_reply)],
    per_user=True, per_chat=True,
)


@auth_guard(staff_only=True)
async def setup_yandex_station(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Ищет ближайший склад через Integration Service и предлагает сохранить."""
    query = update.callback_query
    if query is None or query.data is None or query.message is None:
        return
    await query.answer("Ищем склад... Это может занять пару секунд.")

    loading_msg = await query.edit_message_text("🔍 Связываюсь с Яндекс.Доставкой для поиска склада...")
    if not isinstance(loading_msg, Message):
        return

    integration_url = cast(str, context.bot_data.get('integration_url'))
    bot_id = cast(str, context.bot_data.get('bot_id_for_quart'))

    integration = BaseIntegrationService(integration_url, bot_id)
    result = await integration.find_yandex_station()

    if not result:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=loading_msg.message_id,
            text="❌ Не удалось найти подходящий склад или ПВЗ для отгрузки.\nПроверьте координаты магазина и токен.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_SETTINGS)]])
        )
        return

    s_name = result.get('name')
    s_addr = result.get('address')
    s_id = cast(str, result.get('id'))

    text = (
        f"✅ <b>Найден пункт отгрузки!</b>\n\n"
        f"🏪 <b>Название:</b> {s_name}\n"
        f"📍 <b>Адрес:</b> {s_addr}\n"
        f"🆔 <b>ID:</b> {s_id}\n\n"
        f"Сохранить этот ID для автоматического расчета доставки?"
    )

    await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=loading_msg.message_id,
        text=text,
        reply_markup=get_yandex_confirm_keyboard(s_id),
        parse_mode=ParseMode.HTML
    )


@auth_guard(staff_only=True)
async def save_yandex_station(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Сохраняет ID склада в .env и пушит конфиг."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    station_id = query.data.replace(CB_ADMIN_SAVE_YANDEX, "")

    settings_service: SettingsService = context.bot_data['settings_service']

    # 1. сохраняем в бд (резерв)
    await settings_service.set_setting('yandex_station_id', station_id)

    # 2. сохраняем в .env через правильную утилиту
    update_env_variable("YANDEX_STATION_ID", station_id, env_path=str(DEPLOY_ENV_PATH))

    # 3. пушим конфиг (он возьмет обновленные данные из os.environ или бд)
    pool = context.bot_data['db_pool']
    await push_config_to_integration(pool)

    await query.answer("✅ ID склада сохранен в .env и применен!", show_alert=True)

    # Возвращаемся в меню настроек
    await show_settings_menu(update, context)


@validate_callback
@auth_guard(staff_only=True)
async def sync_products_button_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Запускает синхронизацию товаров по кнопке из настроек.
    """
    query = update.callback_query
    if query is None or query.data is None:
        return
    # Отвечаем сразу, чтобы убрать часики, но можно показать всплывающее уведомление
    await query.answer("Запускаю процесс синхронизации...")

    # Меняем текст меню на статус
    await query.edit_message_text("⏳ <b>Синхронизация каталога и баз данных...</b>\nПожалуйста, подождите.", parse_mode=ParseMode.HTML)  # noqa: E501

    try:
        pool = context.bot_data['db_pool']
        notif_service: NotificationService = context.bot_data.get('notification_service')  # type: ignore[assignment]

        # 1. синхронизация файлов и бд
        await sync_service.sync_products(pool)

        # 2. рассылка уведомлений
        if notif_service:
            # Можно немного доработать process_restock_notifications, чтобы он возвращал кол-во,
            # Но пока просто вызываем
            await notif_service.process_restock_notifications()

        # 3. возвращаем меню настроек с обновленным статусом
        settings_service: SettingsService = context.bot_data['settings_service']
        auto_approve_str = await settings_service.get_setting('auto_approve_new_users', 'false')

        text = "✅ <b>Синхронизация успешно завершена!</b>\n\n⚙️ Настройки бота:"
        reply_markup = get_admin_settings_keyboard(is_auto_approve_enabled=(auto_approve_str == 'true'))

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Button sync error: {e}", exc_info=True)
        # В случае ошибки даем возможность вернуться
        await query.edit_message_text(
            f"❌ <b>Ошибка при синхронизации:</b>\n<code>{e}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_SETTINGS)]]),
            parse_mode=ParseMode.HTML
        )



async def show_courier_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Главный экран настройки курьера."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    s_service: SettingsService = context.bot_data['settings_service']
    enabled = await s_service.get_setting('courier_enabled', 'false') == 'true'
    cities_json = await s_service.get_setting('courier_cities', '[]')
    cities = json.loads(cast(str, cities_json))

    reply_markup = get_admin_courier_mgmt_keyboard(enabled, cities)

    text = (
        "🚚 <b>Управление курьерской доставкой</b>\n\n"
        "Здесь вы настраиваете города, в которые возите заказы сами.\n"
        "Если служба выключена, кнопка 'Курьер' исчезнет при оформлении."
    )
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@validate_callback
async def toggle_courier_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Вкл/Выкл курьерскую службу."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    s_service: SettingsService = context.bot_data['settings_service']

    current = await s_service.get_setting('courier_enabled', 'false') == 'true'
    new_val = 'true' if not current else 'false'
    await s_service.set_setting('courier_enabled', new_val)

    await query.answer(f"Служба {'включена' if new_val == 'true' else 'выключена'}")
    return await show_courier_mgmt(update, context)

# Логика добавления города
async def start_add_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    await query.edit_message_text("Введите <b>Название города</b> (например: Подольск):", parse_mode=ParseMode.HTML)  # noqa: E501
    return C_CITY

async def set_city_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.message is None or update.message.text is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    user_data['new_city_name'] = update.message.text.strip()
    await update.message.reply_text(f"Город: {update.message.text}\nТеперь введите <b>стоимость доставки</b> (только цифры):", parse_mode=ParseMode.HTML)  # noqa: E501
    return C_COST

async def set_city_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.message is None or update.message.text is None:
        return
    if not update.message.text.isdigit():
        await update.message.reply_text("Пожалуйста, введите число.")
        return C_COST
    user_data: dict[str, Any] = context.user_data or {}
    user_data['new_city_cost'] = int(update.message.text)
    await update.message.reply_text("Введите <b>срок доставки в днях</b> (например: 1):")
    return C_DAYS

async def set_city_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.message is None or update.message.text is None:
        return
    if not update.message.text.isdigit():
        await update.message.reply_text("Введите число.")
        return C_DAYS

    user_data: dict[str, Any] = context.user_data or {}
    new_city = {
        "name": user_data.pop('new_city_name'),
        "cost": user_data.pop('new_city_cost'),
        "days": int(update.message.text)
    }

    s_service: SettingsService = context.bot_data['settings_service']
    cities_json = await s_service.get_setting('courier_cities', '[]')
    cities = json.loads(cast(str, cities_json))
    cities.append(new_city)

    await s_service.set_setting('courier_cities', json.dumps(cities, ensure_ascii=False))
    await update.message.reply_text(f"✅ Город {new_city['name']} добавлен!")

    # Возвращаемся в меню (используем фейковый update для вызова)
    return await panel_start(update, context)

async def delete_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    city_name = query.data.replace(CB_ADMIN_COURIER_DEL_CITY, "")
    s_service: SettingsService = context.bot_data['settings_service']
    cities_json = await s_service.get_setting('courier_cities', '[]')
    cities = json.loads(cast(str, cities_json))

    new_cities = [c for c in cities if c['name'] != city_name]
    await s_service.set_setting('courier_cities', json.dumps(new_cities, ensure_ascii=False))

    await query.answer(f"Город {city_name} удален")
    return await show_courier_mgmt(update, context)

# Сборка handler
admin_courier_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_city, pattern=f"^{CB_ADMIN_COURIER_ADD_CITY}$")],
    states={
        C_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city_name)],
        C_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city_cost)],
        C_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city_days)],
    },
    fallbacks=[CommandHandler("cancel", panel_start)],
    per_user=True
)

@auth_guard(staff_only=True)
async def show_pickup_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Главный список точек самовывоза. Универсальный хендлер (кнопка/текст)."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id = update.effective_user.id

    # 1. сбрасываем временные данные мастера, если мы вышли в меню
    user_data: dict[str, Any] = context.user_data or {}
    user_data.pop('p_new', None)

    if query:
        await query.answer()

    s_service: SettingsService = context.bot_data['settings_service']
    points = json.loads((await s_service.get_setting('pickup_points', '[]')) or '[]')

    text = "🏃 <b>Управление самовывозом</b>\n\n✅ — активен | ❌ — скрыт"

    if query:
        await query.edit_message_text(text, reply_markup=get_admin_pickup_mgmt_keyboard(points), parse_mode='HTML')
    else:
        # Если пришли после сохранения (из текста) — чистим чат
        await cleanup_previous_menu(context, user_id)
        msg = await context.bot.send_message(
            chat_id=user_id, text=text,
            reply_markup=get_admin_pickup_mgmt_keyboard(points), parse_mode='HTML'
        )
        # Регистрируем новый якорь
        user_service = context.bot_data['user_service']
        await user_service.save_registration_message_id(user_id, msg.message_id)

    return ConversationHandler.END

async def show_pickup_item_details(update: Update, context: ContextTypes.DEFAULT_TYPE, idx_override: Optional[int] = None) -> Any:  # noqa: E501
    if update.effective_chat is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    idx = idx_override if idx_override is not None else int(query.data.replace(CB_PREFIX_ADMIN_PICKUP_VIEW, ""))

    s_service: SettingsService = context.bot_data['settings_service']
    points = json.loads((await s_service.get_setting('pickup_points', '[]')) or '[]')

    if idx >= len(points):
        return await show_pickup_mgmt(update, context)

    pt = points[idx]
    status = "✅ Включен" if pt.get('is_active', True) else "❌ Выключен"

    # Отображение координат
    coords_display = pt.get('coords', '⚠️ Не заданы')

    text = (
        f"⚙️ <b>Настройка: {pt['name']}</b>\n\n"
        f"<b>Статус:</b> {status}\n"
        f"<b>Адрес:</b> {pt['address']}\n"
        f"<b>График:</b> {pt.get('schedule', 'Не указан')}\n"
        f"<b>Срок:</b> {pt.get('days', 0)} дн.\n"
        f"<b>Координаты:</b> <code>{coords_display}</code>"
    )

    if query:
        await query.edit_message_text(text, reply_markup=get_pickup_item_edit_keyboard(idx, pt.get('is_active', True)), parse_mode='HTML')  # noqa: E501
    else:
        msg = await context.bot.send_message(update.effective_chat.id, text, reply_markup=get_pickup_item_edit_keyboard(idx, pt.get('is_active', True)), parse_mode='HTML')  # noqa: E501
        user_data: dict[str, Any] = context.user_data or {}
        user_data['last_global_menu_id'] = msg.message_id

@auth_guard(staff_only=True)
async def toggle_pickup_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Включает или выключает точку самовывоза (скрывает из меню клиента)."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return

    # Используем актуальное имя префикса
    try:
        idx_str = query.data.replace(CB_PREFIX_ADMIN_PICKUP_TOGGLE, "")
        idx = int(idx_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга индекса в toggle_pickup_status: {query.data}")
        await query.answer("⚠️ Ошибка данных", show_alert=True)
        return

    s_service: SettingsService = context.bot_data['settings_service']
    # Загружаем текущий список точек
    points = json.loads((await s_service.get_setting('pickup_points', '[]')) or '[]')

    if 0 <= idx < len(points):
        # Инвертируем статус (true -> false / false -> true)
        current_status = points[idx].get('is_active', True)
        new_status = not current_status
        points[idx]['is_active'] = new_status

        # Сохраняем обратно в бд
        await s_service.set_setting('pickup_points', json.dumps(points, ensure_ascii=False))

        action_text = "включена" if new_status else "выключена"
        await query.answer(f"Точка '{points[idx]['name']}' {action_text}")
        logger.info(f"Admin {update.effective_user.id} toggled pickup point {idx} to {new_status}")
    else:
        await query.answer("Пункт не найден", show_alert=True)

    # Возвращаемся в карточку просмотра этой же точки (одно окно)
    return await show_pickup_item_details(update, context, idx_override=idx)


@auth_guard(staff_only=True)
async def delete_pickup_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Удаляет пункт самовывоза по индексу."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return

    # [исправлено] используем актуальное имя prefix
    try:
        idx_str = query.data.replace(CB_PREFIX_ADMIN_PICKUP_DEL, "")
        idx = int(idx_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга индекса в delete_pickup_point: {query.data}")
        await query.answer("⚠️ Ошибка данных при удалении.", show_alert=True)
        return

    s_service: SettingsService = context.bot_data['settings_service']
    # Загружаем текущий список
    points = json.loads((await s_service.get_setting('pickup_points', '[]')) or '[]')

    if 0 <= idx < len(points):
        # Удаляем элемент
        removed = points.pop(idx)
        # Сохраняем обновленный список в бд
        await s_service.set_setting('pickup_points', json.dumps(points, ensure_ascii=False))

        await query.answer(f"🗑 Пункт '{removed['name']}' полностью удален.")
        logger.info(f"Admin {update.effective_user.id} deleted pickup point: {removed['name']}")
    else:
        await query.answer("Ошибка: пункт не найден.", show_alert=True)

    # Возвращаемся в главный список (одно окно)
    return await show_pickup_mgmt(update, context)


# Логика редактирования полей
async def start_pickup_field_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Вход в режим правки поля с подробной подсказкой по формату."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    # Данные: adm_p_edit_field_idx
    data_raw = query.data.replace(CB_ADMIN_PICKUP_EDIT, "")
    parts = data_raw.split("_")
    field, idx = parts[0], int(parts[1])

    user_data: dict[str, Any] = context.user_data or {}
    user_data['p_edit_idx'] = idx
    user_data['p_edit_field'] = field

    # Словарь человекочитаемых названий
    labels = {
        "name": "Название",
        "address": "Адрес",
        "schedule": "График",
        "days": "Срок (дни)",
        "coords": "Координаты (Геолокация)"
    }

    label = labels.get(field, "Поле")

    # Формируем подсказку по формату ввода
    hint = ""
    if field == 'coords':
        hint = (
            "\n\n📍 <b>Требуемый формат:</b> <code>55.666843, 37.890427</code>\n"
            "(Широта и долгота через запятую).\n"
            "<i>Если пришлете пустой текст — применится дефолт.</i>"
        )
    elif field == 'days':
        hint = "\n\n🔢 <b>Формат:</b> Введите только целое число (например: 2)."
    elif field == 'schedule':
        hint = "\n\n🕒 <b>Пример:</b> Ежедневно, с 10:00 до 22:00."

    text = f"✏️ Редактирование поля: <b>{label}</b>{hint}\n\nВведите новое значение:"

    # Исправленная клавиатура (убран мусор che)
    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Отмена", callback_data=f"{CB_PREFIX_ADMIN_PICKUP_VIEW}{idx}")
    ]])

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    logger.debug("Admin UI: Started editing field '%s' for pickup point %s", field, idx)
    return P_EDIT_VAL

async def save_pickup_field_val(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return P_EDIT_VAL
    if update.message is None or update.message.text is None:
        return P_EDIT_VAL
    new_val = update.message.text.strip()
    user_data: dict[str, Any] = context.user_data or {}
    idx = user_data.get('p_edit_idx')
    field = user_data.get('p_edit_field')
    user_id = update.effective_user.id

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    s_service: SettingsService = context.bot_data['settings_service']
    points = json.loads((await s_service.get_setting('pickup_points', '[]')) or '[]')

    if idx is not None and 0 <= idx < len(points):
        # Валидация для дней
        if field == 'days':
            if not new_val.isdigit():
                await context.bot.send_message(user_id, "❌ Введите число.")
                return P_EDIT_VAL
            new_val = int(new_val)  # type: ignore[assignment]

        # Логика для координат
        if field == 'coords':
            # Если пусто — ставим эталон
            if not new_val:
                new_val = "55.666843, 37.890427"

            # Регулярка для проверки: число, число (с точками)
            if not re.match(r'^\d+\.\d+,\s*\d+\.\d+$', new_val):
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ <b>Ошибка формата!</b>\n\nИспользуйте формат: <code>55.123, 37.123</code>\nПопробуйте снова:",  # noqa: E501
                    parse_mode='HTML'
                )
                return P_EDIT_VAL

        points[idx][field] = new_val
        await s_service.set_setting('pickup_points', json.dumps(points, ensure_ascii=False))
        logger.info(f"Admin {user_id} updated {field} for point {idx}")

    await cleanup_previous_menu(context, user_id)
    return await show_pickup_item_details(update, context, idx_override=idx)


# Логика добавления (пошаговая)
async def start_add_pickup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Шаг 0: Название. Назад -> к списку пунктов."""
    if update.effective_user is None:
        return
    if update.effective_chat is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    if query:
        await query.answer()

    text = "🆕 <b>Добавление точки (Шаг 1/4)</b>\n\nВведите название (напр. Кафе на Мира):"
    # Назад из первого шага — это просто возврат в меню управления
    markup = get_pickup_wizard_keyboard(CB_ADMIN_PICKUP_MGMT)

    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
    else:
        await cleanup_previous_menu(context, update.effective_user.id)
        msg = await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup, parse_mode='HTML')
        user_data: dict[str, Any] = context.user_data or {}
        user_data['last_global_menu_id'] = msg.message_id
    return P_NAME

async def p_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 1: Получили имя (или вернулись назад). Просим адрес."""
    if update.effective_user is None:
        return P_NAME
    user_id = update.effective_user.id
    if update.message is None:
        return P_NAME
    query = update.callback_query
    if query is None or query.data is None:
        return P_NAME
    if query:
        await query.answer()
    else:
        if update.message.text is None:
            return P_NAME
        user_data: dict[str, Any] = context.user_data or {}
        user_data['p_new'] = {'name': update.message.text.strip(), 'is_active': True}
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    await cleanup_previous_menu(context, user_id)

    text = f"🏢 Название: <b>{user_data['p_new']['name']}</b>\n\n📍 <b>Введите полный адрес:</b>"
    markup = get_pickup_wizard_keyboard(CB_ADMIN_PICKUP_ADD) # Назад к Имени

    msg = await context.bot.send_message(user_id, text, reply_markup=markup, parse_mode='HTML')
    user_data['last_global_menu_id'] = msg.message_id
    return P_ADDR

async def p_add_addr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 2: Получили адрес (или вернулись назад). Просим график."""
    if update.effective_user is None:
        return P_ADDR
    user_id = update.effective_user.id
    if update.message is None:
        return P_ADDR
    query = update.callback_query
    if query is None or query.data is None:
        return P_ADDR

    if query:
        await query.answer()
    else:
        if update.message.text is None:
            return P_ADDR
        user_data: dict[str, Any] = context.user_data or {}
        user_data['p_new']['address'] = update.message.text.strip()
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    await cleanup_previous_menu(context, user_id)

    text = f"📍 Адрес: <i>{user_data['p_new']['address']}</i>\n\n🕒 <b>Введите график работы:</b>"
    markup = get_pickup_wizard_keyboard(CB_ADMIN_PICKUP_BACK_TO_NAME) # Назад к Адресу

    msg = await context.bot.send_message(user_id, text, reply_markup=markup, parse_mode='HTML')
    user_data['last_global_menu_id'] = msg.message_id
    return P_SCHED

async def p_add_sched(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 3: Получили график (или вернулись назад). Просим дни."""
    if update.effective_user is None:
        return P_SCHED
    user_id = update.effective_user.id
    if update.message is None:
        return P_SCHED
    query = update.callback_query
    if query is None or query.data is None:
        return P_SCHED

    if query:
        await query.answer()
    else:
        if update.message.text is None:
            return P_SCHED
        user_data: dict[str, Any] = context.user_data or {}
        user_data['p_new']['schedule'] = update.message.text.strip()
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    await cleanup_previous_menu(context, user_id)

    text = f"🕒 График: <i>{user_data['p_new']['schedule']}</i>\n\n⏱ <b>Срок готовности (дни):</b>"
    markup = get_pickup_wizard_keyboard(CB_ADMIN_PICKUP_BACK_TO_ADDR) # Назад к Графику

    msg = await context.bot.send_message(user_id, text, reply_markup=markup, parse_mode='HTML')
    user_data['last_global_menu_id'] = msg.message_id
    return P_DAYS


async def p_add_final(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Шаг 4: Финал добавления. Теперь проставляем дефолтные координаты."""
    if update.effective_user is None:
        return P_DAYS
    if update.message is None or update.message.text is None:
        return P_DAYS
    user_data: dict[str, Any] = context.user_data or {}
    user_id = update.effective_user.id
    text_val = update.message.text.strip()

    if not text_val.isdigit():
        await update.message.reply_text("❌ Введите число (количество дней):")
        return P_DAYS

    user_data['p_new']['days'] = int(text_val)

    # Авто-проставление координат при создании, если их нет
    if 'coords' not in user_data['p_new']:
        user_data['p_new']['coords'] = "55.666843, 37.890427"

    s_service: SettingsService = context.bot_data['settings_service']
    points = json.loads((await s_service.get_setting('pickup_points', '[]')) or '[]')
    points.append(user_data.pop('p_new'))
    await s_service.set_setting('pickup_points', json.dumps(points, ensure_ascii=False))

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    logger.info(f"✅ Новая точка создана с координатами {user_id}")
    return await show_pickup_mgmt(update, context)


async def admin_exit_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Локальный хендлер выхода, чтобы избежать циклической зависимости с order.py."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if query:
        await query.answer()

    # Импортируем функцию меню внутри, чтобы не ломать импорты при старте
    from tg_bot.handlers.registration import show_main_menu_from_welcome

    # Полная очистка временных данных мастера самовывоза
    user_data: dict[str, Any] = context.user_data or {}
    user_data.pop('p_new', None)
    user_data.pop('p_edit_idx', None)
    user_data.pop('p_edit_field', None)

    # Возвращаемся в корень
    await show_main_menu_from_welcome(update, context)
    return ConversationHandler.END


@auth_guard(staff_only=True)
async def show_logo_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Главное меню управления визиткой регистрации. Универсальный рендер (кнопка/текст)."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id = update.effective_user.id

    if query:
        await query.answer()

    user_data: dict[str, Any] = context.user_data or {}

    s_service: SettingsService = context.bot_data['settings_service']
    logo_id = await s_service.get_setting('registration_logo')
    logo_type = await s_service.get_setting('registration_logo_type', 'photo')

    text = "🎨 <b>Настройка приветственной визитки</b>\n\nЗдесь вы настраиваете сообщение, которое видит пользователь сразу после /start."  # noqa: E501
    reply_markup = get_admin_logo_mgmt_keyboard(has_logo=bool(logo_id))

    # 1. если логотипа нет — работаем с текстом
    if not logo_id:
        if query is None or query.message is None:
            return
        if not (query.message.photo or query.message.video):
            # Обычный edit текста
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            # Если было медиа или нет query — удаляем старое и шлем новый текст
            if query:
                try:
                    await query.message.delete()
                except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")
            await cleanup_previous_menu(context, user_id)
            msg = await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode='HTML')
            user_data['last_global_menu_id'] = msg.message_id
        return

    # 2. если логотип есть — работаем с медиа
    is_current_media = bool(query is not None and query.message is not None and (query.message.photo or query.message.video or query.message.animation))  # noqa: E501

    if is_current_media:
        # Если мы уже в медиа-сообщении — просто обновляем подпись
        try:
            await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode='HTML')
        except (ValueError, KeyError, telegram.error.TelegramError):
            # Если не вышло — переотправим (ниже)
            pass
        else:
            return

    # 3. фолбек: отправка нового медиа-сообщения (если нет query или старое было текстом)
    if query and query.message:
        try:
            await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    await cleanup_previous_menu(context, user_id)

    if logo_type == "video":
        msg = await context.bot.send_video(user_id, video=logo_id, caption=text, reply_markup=reply_markup, parse_mode='HTML')  # noqa: E501
    elif logo_type == "animation":
        msg = await context.bot.send_animation(user_id, animation=logo_id, caption=text, reply_markup=reply_markup, parse_mode='HTML')  # noqa: E501
    else:
        msg = await context.bot.send_photo(user_id, photo=logo_id, caption=text, reply_markup=reply_markup, parse_mode='HTML')  # noqa: E501

    user_data['last_global_menu_id'] = msg.message_id
    await context.bot_data['user_service'].save_registration_message_id(user_id, msg.message_id)

    logger.debug("Admin UI: Logo menu refreshed for %s. Media sent.", user_id)


async def start_logo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Вход в режим ожидания медиа. Исправлен переход для исключения баннера iOS."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None or query.message is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    text = (
        "📸 <b>Загрузка медиа-логотипа</b>\n\n"
        "Пожалуйста, отправьте <b>Фото</b>, <b>Видео</b> или <b>GIF</b>.\n\n"
        "<i>Этот файл будет использоваться для принудительного скрытия плашки ввода на iPhone.</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADMIN_LOGO_MGMT)]])

    # Сначала отправляем новое
    sent_msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=markup,
        parse_mode='HTML'
    )

    # Сохраняем новый id сообщения
    old_msg_id = query.message.message_id
    user_data: dict[str, Any] = context.user_data or {}
    user_data['last_global_menu_id'] = sent_msg.message_id
    user_service = context.bot_data['user_service']
    await user_service.save_registration_message_id(user_id, sent_msg.message_id)

    # Теперь удаляем старое (будь то медиа или текст)
    try:
        await context.bot.delete_message(chat_id=user_id, message_id=old_msg_id)
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.debug(f"Could not delete old menu: {e}")

    logger.info(f"[DEBUG] Admin {user_id}: Upload prompt sent, old menu deleted.")
    return AWAITING_LOGO_PHOTO


async def save_logo_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Универсальное сохранение медиа с гарантированным удалением старого окна."""
    if update.effective_user is None:
        return
    if update.message is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    s_service: SettingsService = context.bot_data['settings_service']
    user_service: UserService = context.bot_data['user_service']
    user_id = update.effective_user.id

    file_id = None
    file_type = None

    # 1. определяем тип контента
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = "video"
    elif update.message.animation:
        file_id = update.message.animation.file_id
        file_type = "animation"

    if not file_id:
        await update.message.reply_text("❌ Пожалуйста, отправьте Фото, Видео или GIF.")
        return AWAITING_LOGO_PHOTO

    # 2. сохраняем в бд
    await s_service.set_setting("registration_logo", file_id or "")
    await s_service.set_setting("registration_logo_type", file_type or "")

    logger.info(f"[DEBUG] Admin {user_id}: Media saved, preparing UI swap.")

    # 3. подготавливаем кнопки
    keyboard = [
        [InlineKeyboardButton("⚙️ Перейти в настройки", callback_data=CB_ADMIN_SETTINGS)],
        [InlineKeyboardButton("🖼 Управление логотипом", callback_data=CB_ADMIN_LOGO_MGMT)]
    ]

    text = (
        f"✅ <b>Медиа-логотип успешно сохранен!</b>\n"
        f"Тип файла: <code>{file_type}</code>\n\n"
        f"Теперь новые пользователи увидят его при входе."
    )

    # 4. отправляем новое чистое окно вперед удаления (для ios)
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

    # 5. запоминаем id старого сообщения (якоря), который нужно удалить
    user_db = await user_service.get_user(user_id)
    old_anchor_id = user_db.registration_message_id if user_db else None

    # 6. регистрируем новый якорь сразу
    user_data['last_global_menu_id'] = msg.message_id
    await user_service.save_registration_message_id(user_id, msg.message_id)

    # 7. теперь безопасно удаляем старое и сообщение пользователя
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    if old_anchor_id:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=old_anchor_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    logger.info(f"Admin {user_id} updated logo. UI swap completed. New anchor: {msg.message_id}")
    return ConversationHandler.END

async def delete_logo_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Удаляет настройку логотипа из БД."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    s_service: SettingsService = context.bot_data['settings_service']

    # Сбрасываем обе настройки
    await s_service.set_setting("registration_logo", None or "")
    await s_service.set_setting("registration_logo_type", None or "")

    logger.info(f"Admin {update.effective_user.id} deleted registration logo.")

    # Возвращаемся в меню управления логотипом (оно теперь покажет, что лого нет)
    return await show_logo_mgmt(update, context)


@auth_guard(staff_only=True)
async def start_welcome_text_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Вход в режим редактирования текста."""
    if update.effective_chat is None:
        return
    query = update.callback_query
    if query is None or query.data is None or query.message is None:
        return
    await query.answer()

    user_data: dict[str, Any] = context.user_data or {}

    # Чтобы не падать на видео-сообщениях
    if query.message.photo or query.message.video:
        await query.message.delete()
        msg = await context.bot.send_message(update.effective_chat.id, "⌛ Подготовка...")
        user_data['last_global_menu_id'] = msg.message_id

    text = "✏️ <b>Введите новый текст приветствия (поддерживает HTML):</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADMIN_LOGO_MGMT)]])

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=user_data.get('last_global_menu_id') or query.message.message_id,
        text=text, reply_markup=markup, parse_mode='HTML'
    )
    return AWAITING_WELCOME_TEXT


async def save_welcome_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Сохраняет текст и возвращает в меню."""
    if update.effective_user is None:
        return
    if update.message is None:
        return
    new_text = update.message.text_html
    user_id = update.effective_user.id
    s_service: SettingsService = context.bot_data['settings_service']

    await s_service.set_setting('registration_welcome_text', new_text)
    logger.info(f"Admin {user_id} updated welcome text.")

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    await cleanup_previous_menu(context, user_id)
    return await show_logo_mgmt(update, context)


# Handler для процесса загрузки
admin_logo_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_logo_upload, pattern=f"^{CB_ADMIN_LOGO_SET}$"),
        CallbackQueryHandler(start_welcome_text_edit, pattern=f"^{CB_ADMIN_WELCOME_TEXT_EDIT}$") # Здесь должна быть точка входа!  # noqa: E501
    ],
    states={
        AWAITING_LOGO_PHOTO: [
            MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION, save_logo_photo)
        ],
        AWAITING_WELCOME_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_welcome_text)
        ],
    },
    fallbacks=[
        CallbackQueryHandler(show_logo_mgmt, pattern=f"^{CB_ADMIN_LOGO_MGMT}$"),
        CallbackQueryHandler(panel_start, pattern=f"^{CB_ADMIN_BACK_TO_MAIN}$")
    ],
    per_user=True,
    name="admin_logo_editor",
    persistent=True
)

# Объединение в handler
admin_pickup_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_add_pickup, pattern=f"^{CB_ADMIN_PICKUP_ADD}$"),
        CallbackQueryHandler(start_pickup_field_edit, pattern=f"^{CB_ADMIN_PICKUP_EDIT}")
    ],
    states={
        P_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, p_add_name),
            CallbackQueryHandler(show_pickup_mgmt, pattern=f"^{CB_ADMIN_PICKUP_MGMT}$"),
            CallbackQueryHandler(admin_exit_to_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$")
        ],
        P_ADDR: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, p_add_addr),
            CallbackQueryHandler(start_add_pickup, pattern=f"^{CB_ADMIN_PICKUP_ADD}$"),
            CallbackQueryHandler(show_pickup_mgmt, pattern=f"^{CB_ADMIN_PICKUP_MGMT}$"),
            CallbackQueryHandler(admin_exit_to_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$")
        ],
        P_SCHED: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, p_add_sched),
            CallbackQueryHandler(p_add_name, pattern=f"^{CB_ADMIN_PICKUP_BACK_TO_NAME}$"), # ИСПОЛЬЗУЕМ ТУТ
            CallbackQueryHandler(show_pickup_mgmt, pattern=f"^{CB_ADMIN_PICKUP_MGMT}$"),
            CallbackQueryHandler(admin_exit_to_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$")
        ],
        P_DAYS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, p_add_final),
            CallbackQueryHandler(p_add_addr, pattern=f"^{CB_ADMIN_PICKUP_BACK_TO_ADDR}$"), # ИСПОЛЬЗУЕМ ТУТ
            CallbackQueryHandler(show_pickup_mgmt, pattern=f"^{CB_ADMIN_PICKUP_MGMT}$"),
            CallbackQueryHandler(admin_exit_to_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$")
        ],
        P_EDIT_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_pickup_field_val)],
    },
    fallbacks=[
        CallbackQueryHandler(show_pickup_mgmt, pattern=f"^{CB_ADMIN_PICKUP_MGMT}$"),
        CallbackQueryHandler(admin_exit_to_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$")
    ],
    per_user=True,
    name="admin_pickup_editor",
    persistent=True
)


PROXY_CONFIG_PATH = KOJO_ROOT / "config" / "config.json"

def _read_config_proxy_flag() -> bool:
    try:
        if PROXY_CONFIG_PATH.exists():
            with open(PROXY_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return cast(bool, json.load(f).get("use_proxy", False))
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Read proxy config error: {e}")
    return False

def _write_config_proxy_flag(status: bool) -> Any:
    try:
        with open(PROXY_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data["use_proxy"] = status
        with open(PROXY_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Write proxy config error: {e}")

@auth_guard(staff_only=True)
async def show_proxy_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Главное меню управления прокси."""
    if update.effective_chat is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    if query:
        await query.answer()

    from tg_bot.infrastructure.secrets_loader import SecretsLoader
    current_proxy = SecretsLoader.get("TG_PROXY_URL")
    is_enabled = _read_config_proxy_flag()

    if not current_proxy:
        status_text = "❌ <b>URL не задан</b>"
    elif is_enabled:
        status_text = f"✅ <b>Включен</b>\nАдрес: <code>{current_proxy}</code>"
    else:
        status_text = f"⏸ <b>Выключен</b> (в config.json)\nАдрес в базе: <code>{current_proxy}</code>"

    text = (
        "🌐 <b>Настройка Proxy-сервера</b>\n\n"
        "Позволяет боту обходить блокировки Telegram (ТСПУ) при загрузке фотографий.\n\n"
        f"Текущий статус: {status_text}\n\n"
        "⚠️ <i>После включения/выключения или смены адреса потребуется перезапуск контейнера бота (docker compose restart bot)!</i>"  # noqa: E501
    )

    reply_markup = get_admin_proxy_mgmt_keyboard(has_proxy_url=bool(current_proxy), is_enabled=is_enabled)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=reply_markup, parse_mode='HTML')
    return ConversationHandler.END

async def toggle_proxy_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Включает/выключает флаг use_proxy в config.json."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None or query.data is None:
        return

    current_status = _read_config_proxy_flag()
    new_status = not current_status
    _write_config_proxy_flag(new_status)

    logger.info(f"Proxy status toggled to {new_status} by {update.effective_user.id}")
    await query.answer(f"Прокси {'ВКЛЮЧЕН' if new_status else 'ВЫКЛЮЧЕН'}! Перезапустите контейнер.", show_alert=True)
    return await show_proxy_mgmt(update, context)

async def start_proxy_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    text = (
        "🌐 <b>Ввод Proxy</b>\n\n"
        "Введите URL прокси-сервера.\n"
        "Форматы:\n"
        "• <code>http://v2raya:20171</code> (для соседнего контейнера)\n"
        "• <code>socks5://user:pass@host:port</code>\n\n"
        "Отправьте URL текстом:"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADMIN_PROXY_MGMT)]])
    await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
    return AWAITING_PROXY_URL

async def save_proxy_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    if update.message is None or update.message.text is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    new_proxy = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/admin_panel.py] TelegramError: {e}")

    if not (new_proxy.startswith("http://") or new_proxy.startswith("https://") or new_proxy.startswith("socks5://")):
        await context.bot.send_message(user_id, "❌ Ошибка: URL должен начинаться с http://, https:// или socks5://")
        return AWAITING_PROXY_URL

    update_env_variable("TG_PROXY_URL", new_proxy, env_path=str(DEPLOY_ENV_PATH))

    # Автоматически включаем флаг, если ввели урл
    _write_config_proxy_flag(True)

    await cleanup_previous_menu(context, user_id)
    msg = await context.bot.send_message(
        chat_id=user_id,
        text="✅ <b>Прокси сохранен и включен!</b>\n\n⚠️ <b>ВНИМАНИЕ:</b> Чтобы изменения вступили в силу, необходимо перезагрузить контейнер:\n<code>docker compose restart bot</code>",  # noqa: E501
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню прокси", callback_data=CB_ADMIN_PROXY_MGMT)]])  # noqa: E501
    )
    user_data['last_global_menu_id'] = msg.message_id
    return ConversationHandler.END

async def delete_proxy_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    update_env_variable("TG_PROXY_URL", "", env_path=str(DEPLOY_ENV_PATH))
    _write_config_proxy_flag(False) # Автоматически выключаем флаг

    await query.edit_message_text(
        "🗑 <b>Прокси удален и выключен.</b>\n\n⚠️ Перезапустите бота (docker compose restart bot), чтобы изменения вступили в силу.",  # noqa: E501
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В настройки", callback_data=CB_ADMIN_SETTINGS)]])
    )
    return ConversationHandler.END

# Инициализация диалога proxy (теперь после функций)
admin_proxy_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_proxy_setup, pattern=f"^{CB_ADMIN_PROXY_SET}$")],
    states={
        AWAITING_PROXY_URL:[MessageHandler(filters.TEXT & ~filters.COMMAND, save_proxy_url)]
    },
    fallbacks=[CallbackQueryHandler(show_proxy_mgmt, pattern=f"^{CB_ADMIN_PROXY_MGMT}$")],
    per_user=True,
    name="admin_proxy_editor"
)

# Регистрация обработчиков
admin_panel_handlers = [
    admin_proxy_handler,
    CommandHandler("panel", panel_start),
    CallbackQueryHandler(show_logo_mgmt, pattern=f"^{CB_ADMIN_LOGO_MGMT}$"),
    CallbackQueryHandler(delete_logo_photo, pattern=f"^{CB_ADMIN_LOGO_DEL}$"),
    CallbackQueryHandler(panel_start, pattern=f"^{CB_ADMIN_BACK_TO_MAIN}$"),
    CallbackQueryHandler(show_users_menu, pattern=f"^{CB_ADMIN_USERS}$"),
    CallbackQueryHandler(show_stats, pattern=f"^{CB_ADMIN_STATS}$"),
    CallbackQueryHandler(show_user_list_by_status, pattern=f"^{CB_PREFIX_USERS_BY_STATUS}"),
    CallbackQueryHandler(show_user_list_by_role, pattern=f"^{CB_PREFIX_USERS_BY_ROLE}"),
    CallbackQueryHandler(show_user_details, pattern=f"^{CB_PREFIX_USER_DETAILS}"),
    CallbackQueryHandler(handle_user_action, pattern=f"^{CB_PREFIX_USER_ACTION}"),
    CallbackQueryHandler(show_settings_menu, pattern=f"^{CB_ADMIN_SETTINGS}$"),
    CallbackQueryHandler(sync_products_button_action, pattern=f"^{CB_ADMIN_SYNC_PRODUCTS}$"),
    CallbackQueryHandler(toggle_auto_approve, pattern=f"^{CB_ADMIN_TOGGLE_AUTO_APPROVE}$"),
    CallbackQueryHandler(show_courier_mgmt, pattern=f"^{CB_ADMIN_COURIER_MGMT}$"),
    CallbackQueryHandler(toggle_courier_service, pattern=f"^{CB_ADMIN_COURIER_TOGGLE}$"),
    CallbackQueryHandler(delete_city, pattern=f"^{CB_ADMIN_COURIER_DEL_CITY}"),
    CallbackQueryHandler(setup_yandex_station, pattern=f"^{CB_ADMIN_SETUP_YANDEX}$"),
    CallbackQueryHandler(save_yandex_station, pattern=f"^{CB_ADMIN_SAVE_YANDEX}"),
    CallbackQueryHandler(show_communication_center, pattern=f"^{CB_ADMIN_COMMUNICATION_CENTER}$"),
    CallbackQueryHandler(show_thread_view, pattern=f"^{CB_PREFIX_THREAD_DETAILS}|^{CB_PREFIX_THREAD_PAGE}"),
    CallbackQueryHandler(handle_thread_action, pattern=f"^{CB_PREFIX_THREAD_ACTION}"),

    # Секция самовывоза (pickup)
    CallbackQueryHandler(show_pickup_mgmt, pattern=f"^{CB_ADMIN_PICKUP_MGMT}$"),
    CallbackQueryHandler(show_pickup_item_details, pattern=f"^{CB_PREFIX_ADMIN_PICKUP_VIEW}"),
    CallbackQueryHandler(toggle_pickup_status, pattern=f"^{CB_PREFIX_ADMIN_PICKUP_TOGGLE}"),
    CallbackQueryHandler(delete_pickup_point, pattern=f"^{CB_PREFIX_ADMIN_PICKUP_DEL}"),

    # Секция прокси
    CallbackQueryHandler(show_proxy_mgmt, pattern=f"^{CB_ADMIN_PROXY_MGMT}$"),
    CallbackQueryHandler(delete_proxy_url, pattern=f"^{CB_ADMIN_PROXY_DEL}$"),
    CallbackQueryHandler(toggle_proxy_status, pattern=f"^{CB_ADMIN_PROXY_TOGGLE}$"),
]
