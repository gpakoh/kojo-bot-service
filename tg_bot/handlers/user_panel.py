# Tg_bot/handlers/user_panel.py
import logging
from typing import Any, Optional

import telegram
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tg_bot.bot_services.communication_service import CommunicationService
from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.product_service import ProductService
from tg_bot.bot_services.user_address_service import UserAddressService
from tg_bot.bot_services.user_service import UserService
from tg_bot.decorators import auth_guard
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import (
    CB_CANCEL_NO_REASON,
    CB_CLOSE_GENERIC,
    CB_DONT_CANCEL,
    CB_PREFIX_ADDR_DEF,
    CB_PREFIX_ADDR_DEL,
    CB_PREFIX_ADDR_RENAME,
    # Клавиатуры и колбэки для настроек и адресов
    CB_PREFIX_ADDR_VIEW,
    CB_PREFIX_USER_CANCEL_ORDER,
    CB_PREFIX_USER_CONTACT_SUPPORT,
    CB_PREFIX_USER_ORDER_DETAILS,
    CB_SUPPORT_CONSULTATION,
    # Константы для комментариев к заказу
    CB_USER_ADD_COMMENT_ORDER,
    CB_USER_DELETE_COMMENT_ORDER,
    CB_USER_DELETE_DATA,
    CB_USER_EDIT_COMMENT_ORDER,
    CB_USER_MY_ORDERS,
    # Добавленные импорты для рейтинга
    CB_USER_RATE_ORDER_START,
    CB_USER_SET_RATING,
    CB_USER_SHOW_MAIN_MENU,
    CB_USER_VIEW_THREAD,
    get_address_details_keyboard,
    get_after_cancellation_keyboard,
    get_cancellation_inline_keyboard,
    get_order_rating_keyboard,
    get_user_addresses_list_keyboard,
    get_user_order_details_keyboard,
    # Клавиатуры и колбэки для заказов
    get_user_orders_keyboard,
    get_user_settings_keyboard,
)
from tg_bot.models import Order, OrderStatus, SenderRole

logger = logging.getLogger(__name__)

# Состояния
AWAITING_USER_MESSAGE = 0
AWAITING_CANCELLATION_REASON = 0
WAITING_NEW_ADDR_NAME = 1

@auth_guard()
async def show_my_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Обертка для показа деталей."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    order_id = int(query.data.replace(CB_PREFIX_USER_ORDER_DETAILS, ''))
    await send_or_edit_order_details(update, context, order_id)


# Поддержка (чат по заказу)
@auth_guard()
async def show_user_thread_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    order_id = int(query.data.replace(CB_USER_VIEW_THREAD, ''))
    comms_service: CommunicationService = context.bot_data['communication_service']

    thread = await comms_service.get_thread_by_order_id(order_id)
    if not thread:
        await query.edit_message_text("История сообщений по этому заказу отсутствует.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]]))
        return

    messages = await comms_service.get_messages_for_thread(thread.id)
    if not messages:
        await query.edit_message_text("История сообщений пуста.")
        return

    import html
    text_blocks = []
    for msg in messages[-15:
        ]:
        sender = "Вы" if msg.sender_role == SenderRole.USER else "Поддержка"
        icon = "👤" if msg.sender_role == SenderRole.USER else "👨‍💻"
        time_str = msg.created_at.strftime('%d.%m %H:%M')
        text_safe = html.escape(msg.text)
        text_blocks.append(f"<b>{icon} {sender}</b> <i>({time_str})</i>:\n{text_safe}\n")

    history_text = f"📜 <b>Чат по заказу #{order_id}</b>\n\n" + "\n".join(text_blocks)

    keyboard = [
        [InlineKeyboardButton("✍️ Написать сообщение", callback_data=f"{CB_PREFIX_USER_CONTACT_SUPPORT}{order_id}")],
        [InlineKeyboardButton("⬅️ Назад к заказам", callback_data=CB_USER_MY_ORDERS)]
    ]
    try:
        await query.edit_message_text(history_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    except (ValueError, KeyError, telegram.error.TelegramError):
        await query.edit_message_text(history_text[:4000] + "...", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def prompt_user_for_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает текст сообщения, определяя: это по заказу или общий вопрос."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    await query.answer()

    data = query.data
    order_id = None

    # 1. определяем контекст обращения
    if data.startswith(CB_PREFIX_USER_CONTACT_SUPPORT):
        # Обращение по конкретному заказу
        try:
            order_id = int(data.replace(CB_PREFIX_USER_CONTACT_SUPPORT, ''))
            context.user_data['support_order_id'] = order_id
            header = f"📦 <b>Заказ #{order_id}</b>"
        except ValueError:
            logger.error(f"Ошибка парсинга order_id из {data}")
            return ConversationHandler.END
    else:
        # Общая консультация (sup_cons)
        context.user_data['support_order_id'] = None
        header = "💬 <b>Общая консультация</b>"

    logger.info(f"User {update.effective_user.id} prompt for msg. Context: {header}")

    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data="cancel_support_input")]])

    text = (
        f"{header}\n\n"
        "✍️ <b>Введите ваше сообщение:</b>\n"
        "Опишите ваш вопрос, и наш менеджер ответит вам в ближайшее время."
    )

    if query.message is None:
        return ConversationHandler.END
    msg = await query.message.reply_text(text, reply_markup=cancel_markup, parse_mode='HTML')
    context.user_data['support_prompt_msg_id'] = msg.message_id

    logger.debug("UI: Prompt Shown For %s", f"order #{order_id}" if order_id else "general")
    return AWAITING_USER_MESSAGE

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет сообщение в БД (в заказ или в общую консультацию)."""
    if update.message is None or update.message.text is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    if update.effective_chat is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}

    user_message_text: str = update.message.text
    user_id = update.effective_user.id
    order_id = context.user_data.get('support_order_id')
    prompt_msg_id = context.user_data.get('support_prompt_msg_id')

    # 1. чистим интерфейс
    if prompt_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_msg_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    comms_service: CommunicationService = context.bot_data['communication_service']

    # 2. сохраняем в правильный тред
    try:
        if order_id:
            # Путь а: сообщение по заказу
            await comms_service.add_message_by_order_id(
                order_id=order_id,
                sender_id=user_id,
                sender_role=SenderRole.USER,
                text=user_message_text
            )
            target_desc = f"по заказу #{order_id}"
        else:
            # Путь б: общая консультация
            thread = await comms_service.get_or_create_consultation_thread(user_id)
            await comms_service.add_message_general(thread.id, user_id, SenderRole.USER, user_message_text)
            target_desc = "в отдел консультаций"

        # 3. фидбек пользователю
        close_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Ваше сообщение {target_desc} успешно отправлено!",
            reply_markup=close_markup,
            parse_mode='HTML'
        )

        # 4. уведомляем админа
        admin_chat_id = context.bot_data.get('admin_chat_id')
        if admin_chat_id:
            try:
                admin_text = f"🔵 <b>Новое сообщение:</b> {target_desc.capitalize()}\nОт: {update.effective_user.first_name}"
                await context.bot.send_message(admin_chat_id, admin_text, parse_mode='HTML')
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error saving user support message: {e}", exc_info=True)
        await context.bot.send_message(user_id, "❌ Произошла ошибка при отправке. Пожалуйста, попробуйте позже.")

    # Очистка контекста
    context.user_data.pop('support_order_id', None)
    context.user_data.pop('support_prompt_msg_id', None)

    logger.debug("Support: Message from %s saved %s", user_id, target_desc)
    return ConversationHandler.END

async def cancel_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        context.user_data = {}
    if update.callback_query:
        await update.callback_query.answer()
        try:
            if update.callback_query.message is not None:
                await update.callback_query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")
    elif update.message:
        await update.message.reply_text("Отменено.")
    context.user_data.pop('support_order_id', None)
    context.user_data.pop('support_prompt_msg_id', None)
    return ConversationHandler.END


# Отмена заказа (inline)

async def prompt_for_cancellation_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    await query.answer()

    order_id = int(query.data.replace(CB_PREFIX_USER_CANCEL_ORDER, ''))
    context.user_data['cancellation_order_id'] = order_id
    if query.message is None:
        return ConversationHandler.END
    context.user_data['cancellation_message_id'] = query.message.message_id

    text = (
        f"⚠️ <b>Отмена заказа #{order_id}</b>\n\n"
        "Пожалуйста, напишите причину отмены.\n"
        "Или выберите действие:"
    )

    await query.edit_message_text(text=text, reply_markup=get_cancellation_inline_keyboard(), parse_mode=ParseMode.HTML)
    return AWAITING_CANCELLATION_REASON

async def handle_cancellation_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        context.user_data = {}
    order_id = context.user_data.get('cancellation_order_id')
    message_to_edit_id = context.user_data.get('cancellation_message_id')

    if not order_id:
        if update.message:
            await update.message.reply_text("Ошибка контекста.")
        return ConversationHandler.END

    reason: str = "Без объяснения причин"
    # Сценарий кнопки
    if update.callback_query:
        await update.callback_query.answer()
    # Сценарий текста
    elif update.message:
        reason = update.message.text or "Без объяснения причин"
        try:
            await update.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    order_service: OrderService = context.bot_data['order_service']
    await order_service.cancel_order_with_reason(order_id, reason)

    result_text = f"✅ <b>Заказ #{order_id} успешно отменен.</b>\n📝 Причина: <i>{reason}</i>"

    if update.effective_chat is None:
        return ConversationHandler.END
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text=result_text, reply_markup=get_after_cancellation_keyboard(), parse_mode=ParseMode.HTML)
        elif message_to_edit_id:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_to_edit_id, text=result_text, reply_markup=get_after_cancellation_keyboard(), parse_mode=ParseMode.HTML)
        else:
             await context.bot.send_message(chat_id=update.effective_chat.id, text=result_text, reply_markup=get_after_cancellation_keyboard(), parse_mode=ParseMode.HTML)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Cancel error: {e}")

    context.user_data.pop('cancellation_order_id', None)
    context.user_data.pop('cancellation_message_id', None)
    return ConversationHandler.END

async def exit_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    await query.answer()
    order_id = context.user_data.get('cancellation_order_id')
    if order_id:
        await send_or_edit_order_details(update, context, order_id)
    else:
        await show_my_orders(update, context)
    return ConversationHandler.END


# Обработка комментариев к заказу
async def add_comment_to_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс добавления комментария к заказу."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    if update.effective_user is None:
        return ConversationHandler.END
    await query.answer()

    order_id = int(query.data.replace(CB_USER_ADD_COMMENT_ORDER, ''))
    context.user_data['comment_order_id'] = order_id
    # Запоминаем id сообщения, которое нужно будет отредактировать в конце
    if query.message is None:
        return ConversationHandler.END
    context.user_data['last_order_details_msg_id'] = query.message.message_id

    logger.info(f"User {update.effective_user.id} adding comment to order #{order_id}")

    await query.edit_message_text(
        f"💬 <b>Введите комментарий к заказу #{order_id}:</b>\n\n"
        "Напишите ваши пожелания (например: <i>'Позвоните за час'</i> или <i>'Оставить у двери'</i>).\n\n"
        "👇 Просто отправьте текст следующим сообщением.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Отмена (Вернуться)", callback_data="cancel_add_comment")
        ]]),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_USER_MESSAGE


async def edit_comment_of_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс редактирования существующего комментария."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    if update.effective_user is None:
        return ConversationHandler.END
    await query.answer()

    order_id = int(query.data.replace(CB_USER_EDIT_COMMENT_ORDER, ''))
    context.user_data['comment_order_id'] = order_id
    if query.message is None:
        return ConversationHandler.END
    context.user_data['last_order_details_msg_id'] = query.message.message_id

    order_service: OrderService = context.bot_data['order_service']
    details = await order_service.get_full_order_details(order_id)

    current_comment = ""
    if details:
        current_comment = details[0].gift_comment or ""

    logger.info(f"User {update.effective_user.id} editing comment of order #{order_id}")

    await query.edit_message_text(
        f"✏️ <b>Редактирование комментария к заказу #{order_id}:</b>\n\n"
        f"Текущий текст:\n<i>{current_comment}</i>\n\n"
        "👇 Пришлите новый текст сообщения:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Отмена", callback_data="cancel_add_comment")
        ]]),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_USER_MESSAGE

async def delete_comment_of_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Обработка удаления комментария к заказу в режиме одного окна."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    # Получаем id заказа из callback_data
    order_id = int(query.data.replace(CB_USER_DELETE_COMMENT_ORDER, ''))
    user_id = update.effective_user.id

    logger.info(f"User {user_id} deleting comment for order #{order_id}")

    # 1. удаляем комментарий в бд
    order_service: OrderService = context.bot_data['order_service']
    await order_service.update_order_comment(order_id, None)  # type: ignore[arg-type]

    # 2. показываем уведомление (всплывающее)
    await query.answer("🗑️ Комментарий удален!", show_alert=False)

    # 3. обновляем текущее сообщение заказа
    if query.message is not None:
        await send_or_edit_order_details(update, context, order_id, force_msg_id=query.message.message_id)


async def save_comment_to_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Универсальное сохранение текста (комментарий или отзыв)."""
    if update.message is None or update.message.text is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}

    text: str = update.message.text.strip()

    # Извлекаем контексты
    rating_order_id = context.user_data.get('rating_order_id')
    comment_order_id = context.user_data.get('comment_order_id')
    main_ui_msg_id = context.user_data.get('last_order_details_msg_id')

    logger.debug("save_comment_to_order: rating_id=%s, comment_id=%s", rating_order_id, comment_order_id)

    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    order_service: OrderService = context.bot_data['order_service']

    if rating_order_id:
        # Сохраняем отзыв (текст к звездам)
        logger.info(f"Saving feedback text for order #{rating_order_id}")
        await order_service.set_order_rating_comment(rating_order_id, text)

        await send_or_edit_order_details(update, context, rating_order_id, force_msg_id=main_ui_msg_id)
        context.user_data.pop('rating_order_id', None)

    elif comment_order_id:
        # Сохраняем комментарий к заказу
        logger.info(f"Saving order comment for order #{comment_order_id}")
        await order_service.update_order_comment(comment_order_id, text)

        await send_or_edit_order_details(update, context, comment_order_id, force_msg_id=main_ui_msg_id)
        context.user_data.pop('comment_order_id', None)

    return ConversationHandler.END



async def cancel_add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Универсальная отмена ввода: для комментариев и для отзывов."""
    if context.user_data is None:
        context.user_data = {}
    query = update.callback_query
    if query:
        await query.answer()

        # Пробуем найти id заказа в любом из контекстов
        order_id = context.user_data.get('comment_order_id') or context.user_data.get('rating_order_id')
        main_ui_msg_id = context.user_data.get('last_order_details_msg_id')

        logger.info(f"User cancelled input for order #{order_id}. Returning to UI.")

        if order_id:
            # Возвращаемся в детали заказа (force_msg_id обеспечит одно окно)
            await send_or_edit_order_details(update, context, order_id, force_msg_id=main_ui_msg_id)
        else:
            # Если совсем потеряли контекст (редко), просто удаляем сообщение
            try:
                if query.message is not None:
                    await query.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    # Очищаем всё лишнее
    context.user_data.pop('comment_order_id', None)
    context.user_data.pop('rating_order_id', None)
    return ConversationHandler.END


# Handlers
@auth_guard()
async def show_user_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает меню настроек. Исправлено: сначала Send, потом Cleanup (iOS Flush)."""
    if update.effective_user is None:
        return
    if context.user_data is None:
        context.user_data = {}
    query = update.callback_query
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']

    if query:
        await query.answer()

    text = "⚙️ <b>Настройки</b>\nЗдесь вы можете управлять сохраненными данными."
    reply_markup = get_user_settings_keyboard()

    # [правило ios] 1. сначала отправляем новое сообщение
    sent_msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    new_id = sent_msg.message_id

    # [правило ios] 2. сразу сохраняем новый id
    context.user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    # [правило ios] 3. чистим старое (особенно если это было фото товара)
    if query:
        try:
            if query.message is not None:
                await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    logger.debug("Settings UI: New anchor %s sent. iOS Flush applied.", new_id)


@auth_guard()
async def show_user_addresses_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список адресов."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    address_service: UserAddressService = context.bot_data['address_service']

    addresses = await address_service.get_addresses(user_id)

    if not addresses:
        text = "📂 У вас пока нет сохраненных адресов.\nОни появятся здесь после успешного оформления заказа."
    else:
        text = "📍 <b>Ваши сохраненные адреса:</b>\nВыберите адрес для управления."

    await query.edit_message_text(text, reply_markup=get_user_addresses_list_keyboard(addresses), parse_mode=ParseMode.HTML)


@auth_guard()
async def show_address_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Детальный просмотр адреса."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    await query.answer()

    addr_id = int(query.data.replace(CB_PREFIX_ADDR_VIEW, ""))
    user_id = update.effective_user.id
    address_service: UserAddressService = context.bot_data['address_service']

    # Ищем адрес в списке (чтобы не делать лишний select one, но можно и select)
    # Сделаем get_addresses, их обычно мало
    addresses = await address_service.get_addresses(user_id)
    address = next((a for a in addresses if a['id'] == addr_id), None)

    if not address:
        await query.answer("Адрес не найден (возможно, удален).", show_alert=True)
        return await show_user_addresses_list(update, context)

    provider_name = "Яндекс Доставка" if address['provider'] == 'yandex' else "СДЭК"
    status = "✅ Основной адрес" if address['is_default'] else "Дополнительный адрес"

    text = (
        f"📍 <b>{address.get('custom_name')}</b>\n\n"
        f"🏢 Служба: {provider_name}\n"
        f"📝 Адрес: {address['address_text']}\n"
        f"🆔 ID точки: {address['point_id']}\n"
        f"ℹ️ Статус: {status}"
    )

    await query.edit_message_text(
        text,
        reply_markup=get_address_details_keyboard(address['id'], address['is_default']),
        parse_mode=ParseMode.HTML
    )

@auth_guard()
async def handle_address_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Обработка удаления или назначения дефолтным."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    data = query.data
    user_id = update.effective_user.id
    address_service: UserAddressService = context.bot_data['address_service']

    if data.startswith(CB_PREFIX_ADDR_DEL):
        addr_id = int(data.replace(CB_PREFIX_ADDR_DEL, ""))
        await address_service.delete_address(addr_id, user_id)
        await query.answer("🗑️ Адрес удален!")
        return await show_user_addresses_list(update, context)

    elif data.startswith(CB_PREFIX_ADDR_DEF):
        addr_id = int(data.replace(CB_PREFIX_ADDR_DEF, ""))
        await address_service.set_default_address(user_id, addr_id)
        await query.answer("✅ Установлен как основной!")
        # Обновляем карточку, чтобы показать новый статус и убрать кнопку "сделать основным"
        # Для простоты вернемся в список, там сразу видно галочку
        return await show_user_addresses_list(update, context)


@auth_guard()
async def start_rename_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс переименования: спрашивает новое имя."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    await query.answer()

    # Парсим id адреса из кнопки
    addr_id = int(query.data.replace(CB_PREFIX_ADDR_RENAME, ""))

    # Сохраняем id адреса, который правим, и id сообщения меню (чтобы потом его обновить)
    context.user_data['renaming_addr_id'] = addr_id
    if query.message is None:
        return ConversationHandler.END
    context.user_data['settings_menu_msg_id'] = query.message.message_id

    text = (
        "✏️ <b>Введите новое название для этого адреса:</b>\n"
        "Например: <i>Дом</i>, <i>Офис</i>, <i>Маме</i>.\n\n"
        "Напишите название и отправьте сообщение."
    )

    # Кнопка отмены
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data="cancel_rename")]])

    await query.edit_message_text(text, reply_markup=cancel_kb, parse_mode=ParseMode.HTML)

    return WAITING_NEW_ADDR_NAME

@auth_guard()
async def save_renamed_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает текст, сохраняет в БД и возвращает в меню."""
    if update.message is None or update.message.text is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    if update.effective_chat is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}

    new_name: str = update.message.text
    user_id = update.effective_user.id
    addr_id = context.user_data.get('renaming_addr_id')
    menu_msg_id = context.user_data.get('settings_menu_msg_id')

    # Удаляем сообщение пользователя для чистоты
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    if not addr_id:
        await update.message.reply_text("Ошибка контекста. Попробуйте снова.")
        return ConversationHandler.END

    # Сохраняем в бд
    address_service: UserAddressService = context.bot_data['address_service']
    await address_service.rename_address(addr_id, user_id, new_name)

    # Возвращаемся в меню деталей адреса (обновляем старое сообщение)
    # Нам нужно сымитировать вызов show_address_details, но так как update другой,
    # Мы просто вызовем логику рендера вручную или "хакнем" update.

    # Проще всего: вывести уведомление и вернуть меню деталей
    try:
        # Получаем обновленный адрес для отображения
        addresses = await address_service.get_addresses(user_id)
        address = next((a for a in addresses if a['id'] == addr_id), None)

        if address and menu_msg_id:
            provider_name = "Яндекс Доставка" if address['provider'] == 'yandex' else "СДЭК"
            status = "✅ Основной адрес" if address['is_default'] else "Дополнительный адрес"

            text = (
                f"✅ <b>Название изменено!</b>\n\n"
                f"📍 <b>{address.get('custom_name')}</b>\n\n"
                f"🏢 Служба: {provider_name}\n"
                f"📝 Адрес: {address['address_text']}\n"
                f"🆔 ID точки: {address['point_id']}\n"
                f"ℹ️ Статус: {status}"
            )

            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=menu_msg_id,
                text=text,
                reply_markup=get_address_details_keyboard(address['id'], address['is_default']),
                parse_mode=ParseMode.HTML
            )
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error restoring menu after rename: {e}")
        # Если не получилось обновить старое, шлем новое
        await context.bot.send_message(update.effective_chat.id, "✅ Название обновлено! Перейдите в настройки, чтобы увидеть изменения.")

    return ConversationHandler.END

@auth_guard()
async def cancel_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена переименования, возврат к деталям."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    await query.answer()

    addr_id = context.user_data.get('renaming_addr_id')

    # Возвращаем старый экран.
    # Мы можем просто триггернуть show_address_details, подменив callback_data
    query.data = f"{CB_PREFIX_ADDR_VIEW}{addr_id}"
    await show_address_details(update, context)

    return ConversationHandler.END

# Сборка conversationhandler
rename_address_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_rename_address, pattern=f"^{CB_PREFIX_ADDR_RENAME}")],
    states={
        WAITING_NEW_ADDR_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_renamed_address),
            CallbackQueryHandler(cancel_rename, pattern="^cancel_rename$")
        ]
    },
    fallbacks=[CallbackQueryHandler(cancel_rename, pattern="^cancel_rename$")],
    per_user=True,
    per_chat=True,
    # Map_to_parent не нужен, так как это самостоятельный диалог внутри меню
)


async def start_order_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает меню выбора звезд."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    await query.answer()
    order_id = int(query.data.replace(CB_USER_RATE_ORDER_START, ''))

    logger.info(f"User {update.effective_user.id} starting rating process for order #{order_id}")
    logger.debug("start_order_rating: order_id=%s", order_id)

    await query.edit_message_text(
        f"⭐️ <b>Оцените заказ #{order_id}</b>\n\n"
        "Нам очень важно ваше мнение! Пожалуйста, выберите оценку от 1 до 5:",
        reply_markup=get_order_rating_keyboard(order_id),
        parse_mode=ParseMode.HTML
    )


def _get_payment_status_html(order: Order) -> str:
    """Возвращает HTML-строку со статусом оплаты."""
    paid_statuses = [OrderStatus.PAID, OrderStatus.ASSEMBLING, OrderStatus.READY_FOR_PICKUP, OrderStatus.SHIPPED, OrderStatus.COMPLETED]
    if order.status in paid_statuses:
        return "✅ <b>Оплачено</b>"
    if order.status == OrderStatus.CANCELLED:
        return "🚫 <b>Отменен</b>"
    return "❌ <b>Не оплачено</b>"


async def _build_items_summary(order_id: int, product_service: ProductService) -> tuple[str, float]:
    """Формирует список товаров и считает сумму без доставки."""
    # Получаем данные из бд
    details = await product_service.pool.fetch(
        "SELECT oi.quantity, oi.price, p.name FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = $1",
        order_id
    )

    items_text = ""
    goods_total = 0.0

    logger.debug("_build_items_summary for order #%s. Found items: %s", order_id, len(details))

    for row in details:
        # Критично: приведение decimal -> float
        price = float(row['price'])
        qty = row['quantity']
        item_sum = qty * price

        goods_total += item_sum
        items_text += f"  • {row['name']}: {qty} шт. x {price}₽\n"

    return items_text, goods_total


def _get_delivery_block(order: Order) -> str:
    """Формирует блок информации о доставке."""
    d_map = {"pickup": "СДЭК", "cdek_point": "СДЭК", "self_pickup": "Самовывоз", "courier": "Курьер", "yandex_point": "Яндекс"}
    d_type = d_map.get(str(order.delivery_type) if order.delivery_type is not None else "", "Не указано")

    # Комментарий (подарочный или обычный)
    comment_part = ""
    if order.gift_comment:
        label = "🎁 Поздравление" if order.is_gift else "💬 Комментарий"
        comment_part = f"\n\n{label}:\n<i>{order.gift_comment}</i>"

    # Убеждаемся, что цена форматируется корректно
    d_price = float(order.delivery_price)
    return (
        f"🚚 <b>Доставка:</b> {d_type}\n"
        f"📍 <b>Адрес:</b> {order.delivery_address or 'Нет данных'}\n"
        f"🚛 Стоимость доставки: {d_price}₽"
        f"{comment_part}"
    )


def _get_rating_block(order: Order) -> str:
    """Формирует блок с оценкой заказа."""
    if not order.rating:
        return ""

    stars = "⭐" * order.rating
    text = f"\n\n<b>Ваша оценка:</b> {stars}"
    if order.rating_comment:
        text += f"\n<i>«{order.rating_comment}»</i>"
    return text


async def set_order_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет числовую оценку и предлагает оставить текстовый отзыв."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    if context.user_data is None:
        context.user_data = {}
    await query.answer()

    # Формат: u_set_rat_orderid_value
    payload = query.data.replace(CB_USER_SET_RATING, '').split('_')
    order_id, rating_val = int(payload[0]), int(payload[1])

    logger.info(f"User {update.effective_user.id} set rating {rating_val} for order #{order_id}")
    logger.debug("set_order_rating: order=%s, val=%s", order_id, rating_val)

    # 1. сохраняем только число в бд
    order_service: OrderService = context.bot_data['order_service']
    await order_service.set_order_rating(order_id, rating_val)

    # 2. устанавливаем контекст для текстового обработчика
    context.user_data['rating_order_id'] = order_id
    if query.message is None:
        return ConversationHandler.END
    context.user_data['last_order_details_msg_id'] = query.message.message_id

    await query.edit_message_text(
        f"🌟 <b>Спасибо за оценку ({rating_val}/5)!</b>\n\n"
        "Вы можете написать, что именно вам понравилось или что нам стоит улучшить.\n"
        "Ваш отзыв поможет нам стать лучше. Или просто нажмите кнопку ниже.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭ Завершить без отзыва", callback_data="cancel_add_comment")
        ]]),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_USER_MESSAGE


async def send_or_edit_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int, force_msg_id: Optional[int] = None) -> Any:
    """Оркестратор: собирает части сообщения и обновляет UI."""
    if update.effective_user is None:
        return
    if context.user_data is None:
        context.user_data = {}

    order_service: OrderService = context.bot_data['order_service']
    product_service: ProductService = context.bot_data['product_service']
    comms_service: CommunicationService = context.bot_data['communication_service']

    user_id = update.effective_user.id
    order_data = await order_service.get_full_order_details(order_id)

    if not order_data:
        logger.error(f"Order {order_id} not found for UI update")
        return

    order, _ = order_data
    if order.id is None or order.created_at is None:
        return

    # 1. собираем части текста
    pay_status = _get_payment_status_html(order)  # type: ignore[arg-type]
    items_text, goods_total = await _build_items_summary(order.id, product_service)
    delivery_text = _get_delivery_block(order)  # type: ignore[arg-type]
    rating_text = _get_rating_block(order)  # type: ignore[arg-type]

    # 2. итоговый текст
    text = (
        f"🧾 <b>Детали Заказа #{order.id}</b>\n\n"
        f"📅 <b>Дата:</b> {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"⭐ <b>Статус:</b> {order.status.value}\n"
        f"💳 <b>Оплата:</b> {pay_status}\n\n"
        f"📦 <b>Состав заказа:</b>\n{items_text}\n"
        f"{delivery_text}\n"
        f"💰 <b>ИТОГО: {order.total_amount}₽</b>"
        f"{rating_text}"
    )

    # 3. клавиатура
    bot_username: str = (await context.bot.get_me()).username or ""
    has_history = await comms_service.check_order_has_messages(order.id)
    reply_markup = get_user_order_details_keyboard(order, bot_username, has_history=has_history)  # type: ignore[arg-type]

    # 4. отправка/редактирование
    target_msg_id = force_msg_id or (update.callback_query.message.message_id if update.callback_query is not None and update.callback_query.message is not None else None)

    logger.info(f"Rendering order #{order_id} (Target Msg: {target_msg_id})")

    if target_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id, message_id=target_msg_id,
                text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
            return
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"Fallback to send_message: {e}")

    sent_msg = await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    context.user_data['last_order_details_msg_id'] = sent_msg.message_id


async def show_logout_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает выбор: просто выход или с очисткой данных."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    text = (
        "<b>🚪 Выход из аккаунта</b>\n\n"
        "Выберите желаемое действие:\n\n"
        "1️⃣ <b>Просто выйти</b> — вы сможете войти снова, ваша история заказов и переписка сохранятся.\n\n"
        "2️⃣ <b>Удалить мои данные</b> — ваша история станет недоступна для вас в боте. "
        "Менеджеры сохранят доступ к истории заказов для отчетности."
    )
    from tg_bot.keyboards import get_logout_options_keyboard
    await query.edit_message_text(text, reply_markup=get_logout_options_keyboard(), parse_mode=ParseMode.HTML)


async def handle_logout_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Выполняет выход и предлагает войти заново через кнопку."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    if context.user_data is None:
        context.user_data = {}
    await query.answer()

    user_id = update.effective_user.id
    should_clear = (query.data == CB_USER_DELETE_DATA)

    user_service: UserService = context.bot_data['user_service']
    await user_service.logout_user(user_id, clear_data=should_clear)

    # Очищаем временные данные сессии
    context.user_data.clear()

    # Сообщение с кнопкой вместо сухого текста
    from tg_bot.keyboards import get_logged_out_keyboard

    text = "✅ <b>Вы успешно вышли из аккаунта.</b>"
    if should_clear:
        text += "\n🗑 Ваша личная история данных в этом боте очищена."

    text += "\n\nНажмите кнопку ниже, чтобы авторизоваться снова."

    await query.edit_message_text(
        text=text,
        reply_markup=get_logged_out_keyboard(),
        parse_mode=ParseMode.HTML
    )
    logger.info(f"User {user_id} logged out (ClearData={should_clear})")


@auth_guard()
async def handle_support_routing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Финальная точка: отправляет сообщение и очищает буфер."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    if context.user_data is None:
        context.user_data = {}
    user_id = update.effective_user.id
    data = query.data

    # 1. пытаемся взять текст из буфера
    user_msg = context.user_data.pop('pending_message_text', None)

    # [новое] если буфера нет (юзер зашел через "детали заказа" -> "поддержка")
    if not user_msg:
        # Просто вызываем старый добрый промпт ввода сообщения
        from tg_bot.handlers.user_panel import prompt_user_for_message
        return await prompt_user_for_message(update, context)

    # 2. определяем цель и создаём/находим тред
    comms_service = context.bot_data['communication_service']
    thread = None
    target_name = ""

    if data == CB_SUPPORT_CONSULTATION:
        thread = await comms_service.get_or_create_consultation_thread(user_id)
        target_name = "в отдел консультаций"
    elif data.startswith(CB_PREFIX_USER_CONTACT_SUPPORT):
        order_id = int(data.replace(CB_PREFIX_USER_CONTACT_SUPPORT, ""))
        thread = await comms_service.get_or_create_thread(order_id)
        target_name = f"по заказу #{order_id}"

    if not thread:
        await query.answer("Ошибка выбора линии поддержки.", show_alert=True)
        return

    # 3. отправляем сообщение
    await comms_service.add_message_general(thread.id, user_id, SenderRole.USER, user_msg)

    # 4. уведомляем админа
    admin_chat_id = context.bot_data.get('admin_chat_id')
    if admin_chat_id:
        try:
            admin_text = f"🔵 <b>Новое сообщение:</b> {target_name.capitalize()}\nОт: {update.effective_user.first_name}"
            await context.bot.send_message(admin_chat_id, admin_text, parse_mode='HTML')
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")

    # 5. ответ пользователю (в одном окне)
    await query.edit_message_text(
        f"✅ <b>Ваше сообщение успешно передано {target_name}!</b>\n\nМенеджер ответит вам в ближайшее время.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]]),
        parse_mode='HTML'
    )


@auth_guard()
async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список заказов. Исправлено: iOS Flush (Send -> Cleanup)."""
    if update.effective_user is None:
        return
    if context.user_data is None:
        context.user_data = {}

    user_id = update.effective_user.id
    order_service: OrderService = context.bot_data['order_service']
    user_service: UserService = context.bot_data['user_service']

    query = update.callback_query
    if query:
        await query.answer()

    # 1. получаем данные
    orders = await order_service.get_orders_by_user_id(user_id)
    text = "📦 <b>Ваши заказы:</b>" if orders else "У вас еще нет ни одного заказа."

    bot_username: str = (await context.bot.get_me()).username or ""
    reply_markup = get_user_orders_keyboard(orders, bot_username)  # type: ignore[arg-type]

    # 2. [правило ios] сначала отправляем новое сообщение
    # Если зашли через команду /orders — шлем новое. если через кнопку — редактируем или шлем новое.
    if query and query.message is not None and not (query.message.photo or query.message.video):
        # Если это был текст (меню) — просто правим
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        new_id = query.message.message_id
    else:
        # Если была команда или переход из фото — шлем новое
        sent_msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        new_id = sent_msg.message_id

        # Удаляем сообщение пользователя (команда /orders) и старое меню после появления нового
        if update.message:
            try:
                await update.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")
        if query and query.message is not None:
            try:
                await query.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/user_panel.py] TelegramError: {e}")
        await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    # 3. регистрация якоря
    context.user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    logger.info(f"Orders UI: Showed list for {user_id}. New anchor: {new_id}")


@auth_guard()
async def show_my_orders_for_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает список заказов с кнопкой 'Назад' в Роутер поддержки."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return
    if query:
        await query.answer()

    user_id = update.effective_user.id
    order_service: OrderService = context.bot_data['order_service']
    orders = await order_service.get_orders_by_user_id(user_id)

    if not orders:
        # Если заказов нет, возвращаем в выбор типа поддержки
        from .ai_chat import handle_router_support
        return await handle_router_support(update, context)

    text = "🧾 <b>Выберите заказ, по которому возник вопрос:</b>"

    # Импортируем клавиатуры
    from tg_bot.keyboards import CB_ROUTER_SUPPORT, get_user_orders_keyboard
    bot_username: str = (await context.bot.get_me()).username or ""

    # Передаем cb_router_support как кнопку назад, чтобы вернуться в выбор линии поддержки
    reply_markup = get_user_orders_keyboard(orders, bot_username, back_callback=CB_ROUTER_SUPPORT)  # type: ignore[arg-type]

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except (ValueError, KeyError, telegram.error.TelegramError):
        # Если не вышло отредактировать, шлем новое
        await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode='HTML')


user_support_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(prompt_user_for_message, pattern=f"^{CB_PREFIX_USER_CONTACT_SUPPORT}")],
    states={
        AWAITING_USER_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message),
            CallbackQueryHandler(cancel_user_message, pattern="^cancel_support_input$")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_user_message)],
    per_user=True, per_chat=True,
)

cancellation_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(prompt_for_cancellation_reason, pattern=f"^{CB_PREFIX_USER_CANCEL_ORDER}")],
    states={
        AWAITING_CANCELLATION_REASON: [
            CallbackQueryHandler(handle_cancellation_reason, pattern=f"^{CB_CANCEL_NO_REASON}$"),
            CallbackQueryHandler(exit_cancellation, pattern=f"^{CB_DONT_CANCEL}$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cancellation_reason)
        ]
    },
    fallbacks=[
        CommandHandler("cancel", exit_cancellation),
        CallbackQueryHandler(exit_cancellation, pattern=f"^{CB_DONT_CANCEL}$")
    ],
    per_user=True, per_chat=True
)


# Conversation handler для работы с комментариями к заказу
order_comment_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(add_comment_to_order, pattern=f"^{CB_USER_ADD_COMMENT_ORDER}"),
        CallbackQueryHandler(edit_comment_of_order, pattern=f"^{CB_USER_EDIT_COMMENT_ORDER}"),
        # Добавляем выбор звезд как точку входа в диалог отзыва
        CallbackQueryHandler(set_order_rating, pattern=f"^{CB_USER_SET_RATING}")
    ],
    states={
        AWAITING_USER_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment_to_order),
            CallbackQueryHandler(cancel_add_comment, pattern="^cancel_add_comment$")
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_add_comment),
        CallbackQueryHandler(cancel_add_comment, pattern="^cancel_add_comment$")
    ],
    per_user=True, per_chat=True,
)
