# Tg_bot/handlers/registration.py
import asyncio
import logging
import re
from typing import Any, Optional

import telegram
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tg_bot.bot_services.cart_service import CartService
from tg_bot.bot_services.settings_service import SettingsService
from tg_bot.bot_services.user_service import UserService
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram
from tg_bot.keyboards import (
    CB_CLOSE_GENERIC,
    CB_PREFIX_APPROVE,
    CB_RESTART_BOT,
    CB_START_REGISTRATION,
    get_contact_keyboard,
    get_staff_main_keyboard,
    get_user_main_keyboard,
    get_user_welcome_keyboard,
)
from tg_bot.models import UserRole, UserStatus

logger = logging.getLogger(__name__)

DEFAULT_WELCOME_MESSAGE = "☕️ Добро пожаловать! Используйте меню, чтобы сделать заказ."
AWAITING_FIO, AWAITING_EMAIL, AWAITING_PHONE = range(3)
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'


async def show_staff_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Меню персонала с защитой iOS Flush."""
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    cart_service: CartService = context.bot_data['cart_service']

    is_empty = await cart_service.is_cart_empty(user_id)
    text = "👨‍💼 <b>Панель персонала</b>\nС возвращением! Используйте кнопки для управления."
    reply_markup = get_staff_main_keyboard(is_cart_empty=is_empty)

    query = update.callback_query
    user_data: dict[str, Any] = context.user_data or {}

    # 1. попытка плавного редактирования (только если старое сообщение было текстом)
    if query and query.message and not user_data.get('is_guest'):
        try:
            if not (query.message.photo or query.message.video or query.message.animation):
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
                user_data['last_global_menu_id'] = query.message.message_id
                return
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    # 2. если edit невозможен — эстафета [правило ios]
    sent_msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    new_id = sent_msg.message_id

    # [правило ios] 1. сначала чистим старое меню (читаем старый якорь из бд до перезаписи)
    user_data['last_global_menu_id'] = new_id
    if query and query.message:
        try:
            await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    # 2. только после зачистки сохраняем новый якорь в бд
    await user_service.save_registration_message_id(user_id, new_id)

    logger.info(f"Staff Menu: Sent {new_id}. Old UI cleaned.")


async def _handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: Any) -> Optional[int]:
    """Обрабатывает аргументы команды /start (p123 или prod_123)."""
    if not context.args:
        return None
    if update.effective_user is None:
        return None

    arg = context.args[0]
    prod_id = None

    # Поддерживаем оба формата для максимальной совместимости
    if arg.startswith('p'):
        prod_id = arg.replace('p', '')
    elif arg.startswith('prod_'):
        prod_id = arg.replace('prod_', '')

    if prod_id and prod_id.isdigit():
        p_id = int(prod_id)
        logger.info(f"🔗 [DeepLink] Пользователь {update.effective_user.id} запрашивает товар {p_id}")

        # Если пользователь уже одобрен — сразу ведем в карточку
        if db_user and db_user.status == UserStatus.APPROVED:
            from tg_bot.handlers.order import VIEWING_PRODUCT, show_product_view
            user_data: dict[str, Any] = context.user_data or {}
            user_data['current_category'] = 'all'
            await show_product_view(update, context, product_id=p_id, category='all')
            return VIEWING_PRODUCT

    return None

async def _handle_staff_entry(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Any, db_user: Any, admin_ids: Any) -> Optional[int]:
    """Логика входа для персонала (админы/менеджеры)."""
    is_staff = user.id in admin_ids or (db_user and db_user.role in [UserRole.ADMIN, UserRole.MANAGER])

    if is_staff:
        if not db_user:
            user_service: UserService = context.bot_data['user_service']
            await user_service.create_approved_admin(user.id, user.full_name or "Admin", "N/A", f"a{user.id}@bot.local")

        logger.info(f"👨‍💼 [Staff] Вход сотрудника {user.id}")
        await show_staff_main_menu(update, context)
        return ConversationHandler.END

    return None


async def received_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ФИО и запрашивает Email (эстафета)."""
    if update.effective_user is None:
        return AWAITING_FIO
    if update.message is None or update.message.text is None:
        return AWAITING_FIO
    user_id = update.effective_user.id
    raw_fio = update.message.text.strip()
    user_service: UserService = context.bot_data['user_service']
    user_data: dict[str, Any] = context.user_data or {}

    # Валидация
    if any(char.isdigit() for char in raw_fio) or len(raw_fio) < 3:
        msg = await context.bot.send_message(user_id, "⚠️ Пожалуйста, введите ФИО буквами:", parse_mode='HTML')
        old_id = user_data.get('prompt_msg_id')
        if old_id:
            try:
                await context.bot.delete_message(user_id, old_id)
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

        user_data['prompt_msg_id'] = msg.message_id
        await user_service.save_registration_message_id(user_id, msg.message_id)
        return AWAITING_FIO

    user_data['fio'] = raw_fio.title()
    safe_fio = prepare_html_for_telegram(user_data['fio'])
    old_anchor_id = user_data.get('prompt_msg_id')

    # 1. сначала новый промпт (email)
    next_prompt = await context.bot.send_message(
        chat_id=user_id,
        text=f"🤝 <b>{safe_fio}</b>, принято!\n\nВведите ваш <b>Email</b>:",
        parse_mode='HTML'
    )

    # 2. обновляем якорь
    await user_service.save_registration_message_id(user_id, next_prompt.message_id)
    user_data['prompt_msg_id'] = next_prompt.message_id

    # 3. зачистка
    if old_anchor_id:
        try:
            await context.bot.delete_message(user_id, old_anchor_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    return AWAITING_EMAIL


async def received_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает Email и запрашивает телефон (эстафета)."""
    if update.effective_user is None:
        return AWAITING_EMAIL
    if update.message is None or update.message.text is None:
        return AWAITING_EMAIL
    user_id = update.effective_user.id
    email = update.message.text.strip()
    user_service: UserService = context.bot_data['user_service']
    user_data: dict[str, Any] = context.user_data or {}

    if not re.fullmatch(EMAIL_REGEX, email):
        msg = await context.bot.send_message(user_id, "⚠️ Введите корректный Email:", parse_mode='HTML')
        old_id = user_data.get('prompt_msg_id')
        if old_id:
            try:
                await context.bot.delete_message(user_id, old_id)
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

        user_data['prompt_msg_id'] = msg.message_id
        await user_service.save_registration_message_id(user_id, msg.message_id)
        return AWAITING_EMAIL

    user_data['email'] = email
    old_anchor_id = user_data.get('prompt_msg_id')

    # 1. запрос контакта
    prompt = await context.bot.send_message(
        chat_id=user_id,
        text="📧 <b>Email сохранен!</b>\n\nНажмите кнопку ниже, чтобы поделиться номером телефона:",
        reply_markup=get_contact_keyboard(),
        parse_mode='HTML'
    )

    # 2. регистрация якоря
    await user_service.save_registration_message_id(user_id, prompt.message_id)
    user_data['prompt_msg_id'] = prompt.message_id

    # 3. зачистка
    if old_anchor_id:
        try:
            await context.bot.delete_message(user_id, old_anchor_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    return AWAITING_PHONE

async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершает регистрацию.
    Уведомляет ВСЕХ админов (персонально + в общий чат) и зачищает интерфейс.
    """
    if update.effective_user is None:
        return AWAITING_PHONE
    user = update.effective_user
    user_id = user.id
    user_service: UserService = context.bot_data['user_service']
    settings_service: SettingsService = context.bot_data['settings_service']
    user_data: dict[str, Any] = context.user_data or {}

    # 1. валидация контакта
    if not update.message or not update.message.contact:
        return await invalid_phone_input(update, context)

    phone = update.message.contact.phone_number
    fio: Any = user_data.get('fio')
    email: Any = user_data.get('email')
    old_prompt_id: Any = user_data.get('prompt_msg_id')

    # Удаляем сообщение пользователя с контактом
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    # 2. регистрация в бд
    auto_approve_setting = (await settings_service.get_setting('auto_approve_new_users', 'false')) or 'false'
    auto_approve_bool = auto_approve_setting.lower() == 'true'

    new_user = await user_service.register_new_user(
        user_id, fio, phone, email, auto_approve_bool
    )

    logger.info(f"✅ [Reg] User {user_id} registered. Status: {new_user.status}")

    # 3. блок уведомления администрации (гибридный)
    if new_user.status == UserStatus.PENDING:
        # Собираем все id, куда нужно отправить уведомление
        admin_targets = set()

        # Добавляем общий чат админов (если настроен)
        gen_chat_id = context.bot_data.get('admin_chat_id')
        if gen_chat_id:
            admin_targets.add(int(gen_chat_id))

        # Добавляем всех персональных админов из конфига (как в старой версии)
        individual_ids = context.bot_data.get('admin_ids', [])
        for a_id in individual_ids:
            admin_targets.add(int(a_id))

        if admin_targets:
            safe_fio = prepare_html_for_telegram(fio)
            safe_email = prepare_html_for_telegram(email)
            safe_phone = prepare_html_for_telegram(phone)
            admin_text = (
                f"🔔 <b>Новая заявка на регистрацию!</b>\n\n"
                f"<b>ФИО:</b> {safe_fio}\n"
                f"<b>Телефон:</b> <code>{safe_phone}</code>\n"
                f"<b>Email:</b> <code>{safe_email}</code>\n"
                f"<b>TG ID:</b> <code>{user_id}</code>"
            )
            from tg_bot.keyboards import get_admin_approval_keyboard
            reply_markup = get_admin_approval_keyboard(user_id)

            logger.info(f"🔍 [AdminNotify] Рассылка уведомления на {len(admin_targets)} целей.")

            for target_id in admin_targets:
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=admin_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    logger.debug("Admin Notification: Sent to %s", target_id)
                except (ConnectionError, TimeoutError, OSError) as e:
                    logger.error(f"❌ [AdminNotify] Не удалось отправить сообщение на {target_id}: {e}")
        else:
            logger.warning("⚠️ [adminnotify] список получателей (admin_targets) пуст!")

    # 4. зачистка промпта с кнопкой
    if old_prompt_id:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=old_prompt_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    # 5. переход к интерфейсу
    user_data.clear()

    if new_user.status == UserStatus.APPROVED:
        # Если авто-одобрен — открываем меню
        return await show_main_menu_from_welcome(update, context)
    else:
        # Если ждет — экран gate
        return await show_unauthorized_gate(update, context)


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет процесс регистрации."""
    if update.effective_user is None:
        return ConversationHandler.END
    user_id = update.effective_user.id
    if update.message:
        await update.message.delete()

    # Очищаем корзину в бд, если пользователь решил не регистрироваться,
    # Но успел что-то добавить (хотя auth_guard обычно не пускает, но для чистоты)
    if 'cart_service' in context.bot_data:
        await context.bot_data['cart_service'].clear_cart(user_id)

    if update.effective_chat is None:
        return ConversationHandler.END
    await context.bot.send_message(update.effective_chat.id, "Регистрация отменена.")
    user_data: dict[str, Any] = context.user_data or {}
    user_data.clear()
    return ConversationHandler.END

async def handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Обрабатывает одобрение/отклонение заявки модератором."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    await query.answer()

    moderator = update.effective_user
    data = query.data
    is_approve = data.startswith(CB_PREFIX_APPROVE)
    user_to_moderate_id = int(data.split('_')[1])

    user_service: UserService = context.bot_data['user_service']
    updated_user = await user_service.get_user(user_to_moderate_id)

    # Подготовка общей клавиатуры для модератора (финал действия)
    from tg_bot.keyboards import CB_CLOSE_GENERIC, CB_USER_SHOW_MAIN_MENU
    moderator_finish_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU),
            InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)
        ]
    ])

    if is_approve:
        approved_user = await user_service.approve_user(user_to_moderate_id, moderator.id)
        if approved_user:
            logger.info(f"✅ User {user_to_moderate_id} approved by moderator {moderator.id}")

            # 1. уведомление пользователю
            welcome_text = "✅ <b>Ваш аккаунт был одобрен!</b>\n\nТеперь вам доступны все функции магазина."
            try:
                if updated_user and updated_user.registration_message_id:
                    await context.bot.edit_message_text(
                        chat_id=updated_user.telegram_id,
                        message_id=updated_user.registration_message_id,
                        text=welcome_text,
                        reply_markup=get_user_welcome_keyboard(),
                        parse_mode='HTML'
                    )
                else:
                    raise ValueError()
            except (ValueError, KeyError, telegram.error.TelegramError):
                await context.bot.send_message(
                    chat_id=user_to_moderate_id,
                    text=welcome_text,
                    reply_markup=get_user_welcome_keyboard(),
                    parse_mode='HTML'
                )

            # 2. ответ модератору (с кнопками выхода)
            safe_fio = prepare_html_for_telegram(approved_user.fio)
            await query.edit_message_text(
                text=f"✅ Пользователь <b>{safe_fio}</b> одобрен модератором {prepare_html_for_telegram(moderator.full_name)}.",
                reply_markup=moderator_finish_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("ℹ️ Действие уже было выполнено ранее.", reply_markup=moderator_finish_markup)

    else:
        # Логика отклонения (decline)
        declined_user = await user_service.decline_user(user_to_moderate_id, moderator.id)
        if declined_user:
            logger.info(f"❌ User {user_to_moderate_id} declined by moderator {moderator.id}")
            try:
                await context.bot.send_message(user_to_moderate_id, "❌ К сожалению, ваша заявка на регистрацию была отклонена.")
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

            safe_fio = prepare_html_for_telegram(declined_user.fio)
            await query.edit_message_text(
                text=f"❌ Заявка пользователя <b>{safe_fio}</b> отклонена модератором {prepare_html_for_telegram(moderator.full_name)}.",
                reply_markup=moderator_finish_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("ℹ️ Действие уже было выполнено ранее.", reply_markup=moderator_finish_markup)


async def show_unauthorized_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Экран статуса для тех, кто уже подал заявку или заблокирован (защита iOS)."""
    if update.effective_user is None:
        return ConversationHandler.END
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    db_user = await user_service.get_user(user_id)

    if db_user and db_user.status == UserStatus.BLOCKED:
        text = "🚫 <b>Доступ заблокирован.</b>\n\nСвяжитесь с администрацией для уточнения причин."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]])
    else:
        # Статус "в ожидании"
        text = (
            "⏳ <b>Ваша заявка на рассмотрении.</b>\n\n"
            "Менеджеры проверяют данные. Мы пришлем уведомление, когда доступ будет открыт.\n\n"
            "👇 Нажмите кнопку ниже, чтобы обновить статус:"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить статус", callback_data=CB_RESTART_BOT)]])

    # [правило ios] 1. сначала отправляем новое окно
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=markup,
        parse_mode='HTML'
    )

    # 2. фиксируем якорь
    await user_service.save_registration_message_id(user_id, msg.message_id)

    # 3. удаляем старое
    await cleanup_previous_menu(context, user_id, exclude_id=msg.message_id)

    return ConversationHandler.END


async def _check_start_redirections(update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: Any) -> Optional[int]:
    """
    Проверяет, нужно ли отправить пользователя по спец. путям:
    диплинки, сотрудники или главное меню.
    """
    if update.effective_user is None:
        return None
    user = update.effective_user
    admin_ids: Any = context.bot_data.get('admin_ids', [])

    # 1. обработка глубоких ссылок (товары)
    dl_state = await _handle_deep_link(update, context, db_user)
    if dl_state is not None:
        logger.debug("Start: Handled Via Deeplink")
        return dl_state

    # 2. обработка сотрудников
    staff_state = await _handle_staff_entry(update, context, user, db_user, admin_ids)
    if staff_state is not None:
        logger.debug("Start: Handled Via Staffentry")
        return staff_state

    # 3. обработка уже одобренных пользователей
    if db_user and db_user.status == UserStatus.APPROVED:
        logger.debug("Start: Redirecting To Main Menu (approved)")
        return await show_main_menu_from_welcome(update, context)

    return None


async def _send_welcome_ui(user_id: int, context: ContextTypes.DEFAULT_TYPE, logo_id: Any, logo_type: Any, welcome_text: str, markup: InlineKeyboardMarkup) -> Any:
    """
    Отправка приветствия. Использует физическую клавиатуру для уничтожения баннера iOS.
    """
    # Шаг а: силовой захват (force resize).
    # Placeholder заставляет ios перерисовать область ввода, что убивает баннер.
    force_kb = ReplyKeyboardMarkup(
        [[KeyboardButton("☕️ Открыть Kojo")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Нажмите 'Посмотреть каталог'..."
    )

    # Отправляем flush-сообщение
    flush_msg = await context.bot.send_message(
        chat_id=user_id,
        text="⌛ <b>Загрузка магазина...</b>",
        reply_markup=force_kb,
        parse_mode='HTML'
    )

    # Даем ios время (0.3с оптимально) переключить баннер на клавиатуру
    await asyncio.sleep(0.3)

    # Шаг б: основной контент (видео/фото + inline кнопки)
    sent_msg = None
    try:
        if logo_id:
            params: dict[str, Any] = {"chat_id": user_id, "caption": welcome_text, "reply_markup": markup, "parse_mode": 'HTML'}
            if logo_type == "video":
                sent_msg = await context.bot.send_video(video=logo_id, **params)
            elif logo_type == "animation":
                sent_msg = await context.bot.send_animation(animation=logo_id, **params)
            else:
                sent_msg = await context.bot.send_photo(photo=logo_id, **params)
        else:
            sent_msg = await context.bot.send_message(user_id, text=welcome_text, reply_markup=markup, parse_mode='HTML')
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Error in _send_welcome_ui: {e}")
        sent_msg = await context.bot.send_message(user_id, text=welcome_text, reply_markup=markup, parse_mode='HTML')

    return flush_msg, sent_msg


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Главный диспетчер /start. Чистый переход без баннеров.
    """
    import time
    _t_start = time.perf_counter()

    if update.effective_user is None:
        return ConversationHandler.END
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    settings_service: SettingsService = context.bot_data['settings_service']
    user_data: dict[str, Any] = context.user_data or {}

    logger.info(f"🚀 [Start] Stable iOS Flush for {user_id}")

    if update.message:
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    _t_before_db = time.perf_counter()
    db_user = await user_service.get_user(user_id)
    _t_after_db = time.perf_counter()
    logger.info(f"[TIMING] get_user: {(_t_after_db - _t_before_db)*1000:.0f}ms")

    # 1. редиректы
    _t0 = time.perf_counter()
    redirect_state = await _check_start_redirections(update, context, db_user)
    logger.info(f"[TIMING] _check_start_redirections: {(time.perf_counter() - _t0)*1000:.0f}ms")
    if redirect_state is not None:
        logger.info(f"[TIMING] TOTAL before redirect: {(time.perf_counter() - _t_start)*1000:.0f}ms")
        return redirect_state

    # 2. контент
    _t0 = time.perf_counter()
    logo_id: Any = await settings_service.get_setting('registration_logo')
    logo_type: Any = await settings_service.get_setting('registration_logo_type', 'photo')
    welcome_text: str = await settings_service.get_setting('registration_welcome_text', DEFAULT_WELCOME_MESSAGE) or DEFAULT_WELCOME_MESSAGE
    logger.info(f"[TIMING] settings queries: {(time.perf_counter() - _t0)*1000:.0f}ms")

    from tg_bot.keyboards import get_welcome_options_keyboard
    markup = get_welcome_options_keyboard()

    # 3. отправка (сначала flush-текст, потом видео)
    _t0 = time.perf_counter()
    flush_msg, sent_msg = await _send_welcome_ui(user_id, context, logo_id, logo_type, welcome_text, markup)
    logger.info(f"[TIMING] _send_welcome_ui: {(time.perf_counter() - _t0)*1000:.0f}ms")
    new_id = sent_msg.message_id

    # 4. зачистка после того как всё появилось
    # Удаляем временную надпись "загрузка..."
    _t0 = time.perf_counter()
    try:
        await context.bot.delete_message(user_id, flush_msg.message_id)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    # Очищаем все старые якоря в чате через exclude_id (наше новое видео не трогаем)
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)
    logger.info(f"[TIMING] cleanup: {(time.perf_counter() - _t0)*1000:.0f}ms")

    # 5. регистрация финального якоря
    _t0 = time.perf_counter()
    await user_service.save_registration_message_id(user_id, new_id)
    user_data.pop('prompt_msg_id', None)
    logger.info(f"[TIMING] save_registration: {(time.perf_counter() - _t0)*1000:.0f}ms")

    logger.info(f"[TIMING] TOTAL /start handler: {(time.perf_counter() - _t_start)*1000:.0f}ms")
    return ConversationHandler.END


async def start_fio_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Второй такт: переход к вводу ФИО. Использует Double Flush для открытия поля ввода.
    """
    if update.effective_user is None:
        return AWAITING_FIO
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    settings_service: SettingsService = context.bot_data['settings_service']
    user_data: dict[str, Any] = context.user_data or {}

    if update.callback_query:
        try:
            await update.callback_query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    logger.info(f"📝 [Reg] FIO Step initiated with Flush for {user_id}")

    # 1. получаем лого и чистую инструкцию (без приветствия)
    logo_id: Any = await settings_service.get_setting('registration_logo')
    logo_type: Any = await settings_service.get_setting('registration_logo_type', 'photo')
    fio_prompt = (
        "🤝 <b>Начнем регистрацию!</b>\n\n"
        "Введите ваше <b>ФИО</b> через пробел:\n"
        "<i>(Например: Иванов Иван Иванович)</i>"
    )

    # 2. шаг а: flush-сообщение (сброс кнопок и плашки)
    flush_msg = None
    remove_kb = ReplyKeyboardRemove()
    try:
        params: dict[str, Any] = {"chat_id": user_id, "caption": fio_prompt, "reply_markup": remove_kb, "parse_mode": 'HTML'}
        if logo_id:
            if logo_type == "video":
                flush_msg = await context.bot.send_video(video=logo_id, **params)
            elif logo_type == "animation":
                flush_msg = await context.bot.send_animation(animation=logo_id, **params)
            else:
                flush_msg = await context.bot.send_photo(photo=logo_id, **params)
        else:
            flush_msg = await context.bot.send_message(user_id, text=fio_prompt, reply_markup=remove_kb, parse_mode='HTML')
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    await asyncio.sleep(0.05)

    # 3. шаг б: основное сообщение (ожидает текст)
    sent_msg = None
    try:
        params = {"chat_id": user_id, "caption": fio_prompt, "reply_markup": remove_kb, "parse_mode": 'HTML'}
        if logo_id:
            if logo_type == "video":
                sent_msg = await context.bot.send_video(video=logo_id, **params)
            elif logo_type == "animation":
                sent_msg = await context.bot.send_animation(animation=logo_id, **params)
            else:
                sent_msg = await context.bot.send_photo(photo=logo_id, **params)
        else:
            sent_msg = await context.bot.send_message(user_id, text=fio_prompt, reply_markup=remove_kb, parse_mode='HTML')
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    # 4. зачистка
    db_user = await user_service.get_user(user_id)
    old_welcome_id = db_user.registration_message_id if db_user else None
    current_call_id = update.callback_query.message.message_id if update.callback_query and update.callback_query.message else None

    if flush_msg:
        try:
            await context.bot.delete_message(user_id, flush_msg.message_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    if sent_msg:
        for to_del in {old_welcome_id, current_call_id}:
            if to_del and to_del != sent_msg.message_id:
                try:
                    await context.bot.delete_message(chat_id=user_id, message_id=to_del)
                except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

        await user_service.save_registration_message_id(user_id, sent_msg.message_id)
        user_data['prompt_msg_id'] = sent_msg.message_id

    # Прямо сейчас возвращаем стейт ожидания фио
    return AWAITING_FIO


async def show_main_menu_from_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отрисовка главного меню. Исправлено: сначала Send, потом Cleanup (iOS Flush)."""
    if update.effective_user is None:
        return ConversationHandler.END
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    user_db = await user_service.get_user(user_id)

    # 1. проверка авторизации (стабильность)
    if not user_db or user_db.status != UserStatus.APPROVED:
        from .registration import show_unauthorized_gate
        return await show_unauthorized_gate(update, context)

    if update.callback_query:
        await update.callback_query.answer()

    is_staff = user_db.role in [UserRole.ADMIN, UserRole.MANAGER]
    cart_service = context.bot_data['cart_service']
    is_empty = await cart_service.is_cart_empty(user_id)

    fav_service = context.bot_data.get('favorite_service')
    has_favs = False
    if fav_service:
        has_favs = await fav_service.has_any_favorites(user_id)

    reply_markup = get_user_main_keyboard(
        is_staff=is_staff,
        is_cart_empty=is_empty,
        has_favorites=has_favs
    )

    text = context.bot_data.get('welcome_message', "☕️ Добро пожаловать!")

    # [правило ios] 1. сначала отправляем новое сообщение
    sent_msg = await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode='HTML')
    new_id = sent_msg.message_id

    # [правило ios] 2. чистим старые окна, исключая наше новое
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    # [правило ios] 3. регистрируем новый якорь в бд
    user_data: dict[str, Any] = context.user_data or {}
    user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    logger.debug("Main Menu: Sent %s. iOS Flush applied.", new_id)
    return ConversationHandler.END


async def invalid_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка некорректного ввода на этапе телефона.
    Восстанавливает кнопку 'Поделиться контактом', если она пропала.
    """
    if update.effective_user is None:
        return AWAITING_PHONE
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    user_data: dict[str, Any] = context.user_data or {}

    logger.info(f"🔄 [Reg] Восстановление кнопки контакта для {user_id}")

    # 1. эстафета: сначала отправляем новый промпт с кнопкой
    from tg_bot.keyboards import get_contact_keyboard
    text = (
        "⚠️ <b>Кнопка контакта потерялась?</b>\n\n"
        "Пожалуйста, нажмите на кнопку <b>'Поделиться контактом'</b> ниже.\n"
        "<i>Мы используем этот метод для мгновенной верификации вашего номера.</i>"
    )

    new_prompt = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=get_contact_keyboard(),
        parse_mode='HTML'
    )

    # 2. сразу регистрируем новый якорь в бд и памяти
    old_prompt_id = user_data.get('prompt_msg_id')
    user_data['prompt_msg_id'] = new_prompt.message_id
    await user_service.save_registration_message_id(user_id, new_prompt.message_id)

    # 3. теперь зачищаем чат от старых сообщений
    # Удаляем то, что ввел пользователь
    if update.message:
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    # Удаляем старое сообщение-инструкцию (если оно еще живо)
    if old_prompt_id:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=old_prompt_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/registration.py] TelegramError: {e}")

    logger.info(f"[DEBUG] Registration: Contact button restored. New anchor: {new_prompt.message_id}")

    # Остаемся в состоянии ожидания телефона
    return AWAITING_PHONE



# Conversationhandler с тремя состояниями
registration_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        CallbackQueryHandler(start, pattern=f"^{CB_RESTART_BOT}$"),
        # Точка входа после клика на кнопку "начать регистрацию"
        CallbackQueryHandler(start_fio_step, pattern=f"^{CB_START_REGISTRATION}$")
    ],
    states={
        AWAITING_FIO: [
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, received_fio)
        ],
        AWAITING_EMAIL: [
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, received_email)
        ],
        AWAITING_PHONE: [
            CommandHandler("start", start),
            MessageHandler(filters.CONTACT, received_phone),
            MessageHandler(filters.ALL & ~filters.COMMAND, invalid_phone_input)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_registration)],
    per_user=True,
    per_chat=True,
    name="registration_conversation",
    persistent=True,
    allow_reentry=True
)
