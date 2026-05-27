import logging
import telegram
from typing import Any, Optional, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from tg_bot.bot_services.ai_communication_service import AICommunicationService
from tg_bot.bot_services.user_service import UserService
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import get_gift_choice_keyboard, get_gift_comment_keyboard

logger = logging.getLogger(__name__)


async def prompt_gift_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_cart_fn: Any,
    asking_gift_state: int,
    delivery_data: Optional[dict[str, Any]] = None,
) -> int:
    if update.effective_user is None:
        return asking_gift_state
    user_id = update.effective_user.id

    if update.effective_chat is None:
        return asking_gift_state

    user_data: dict[str, Any] = context.user_data or {}
    user_service: UserService = context.bot_data['user_service']

    if delivery_data:
        user_data['temp_delivery_data'] = delivery_data
    else:
        delivery_data = user_data.get('temp_delivery_data')

    if not delivery_data:
        logger.warning(f"User {user_id} lost temp_delivery_data in prompt_gift_choice")
        query_early = update.callback_query
        if query_early is not None:
            await query_early.answer("Сессия истекла, выберите доставку заново.", show_alert=True)
        return cast(int, await show_cart_fn(update, context))

    logger.info(f"User {user_id} choosing gift option. Delivery: {delivery_data.get('delivery_type')}")

    text = "☕️ <b>Почти готово!</b>\n\nЭтот заказ для вас или вы хотите отправить его в подарок?"
    reply_markup = get_gift_choice_keyboard()

    query = update.callback_query

    if query is not None:
        try:
            msg = await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            if isinstance(msg, Message):
                user_data['last_global_menu_id'] = msg.message_id
            return asking_gift_state
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"Could not edit message in prompt_gift_choice: {e}")

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
    new_id = msg.message_id

    webapp_msg_id = user_data.pop('webapp_msg_id', None)
    if webapp_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=webapp_msg_id)
            logger.info(f"🗑 [iOS Flush Fix] Удалено старое окно WebApp (ID: {webapp_msg_id}) ПОСЛЕ отправки нового.")
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.debug(f"Не удалось удалить webapp_msg_id: {e}")

    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    logger.debug("prompt_gift_choice: UI rendered for user %s. New Anchor: %s", user_id, new_id)
    return asking_gift_state


async def handle_gift_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, finalize_order_and_pay_fn: Any) -> int:
    if update.effective_user is None:
        return ConversationHandler.END

    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    logger.info(f"User {update.effective_user.id} skipped gift comment via button.")
    logger.debug("Handle_gift_skip: Finalizing Order Without Comment.")

    user_data: dict[str, Any] = context.user_data or {}
    delivery_data = user_data.get('temp_delivery_data')
    if not delivery_data:
        await query.edit_message_text("Ошибка сессии.")
        return ConversationHandler.END

    return cast(int, await finalize_order_and_pay_fn(
        update,
        context,
        **delivery_data,
        is_gift=True,
        gift_comment=None,
    ))


async def handle_gift_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    finalize_order_and_pay_fn: Any,
    gift_for_me_callback: str,
    gift_as_present_callback: str,
    awaiting_gift_comment_state: int,
) -> int:
    if update.effective_user is None:
        return ConversationHandler.END

    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    user_data: dict[str, Any] = context.user_data or {}
    delivery_data = user_data.get('temp_delivery_data')
    if not delivery_data:
        logger.warning(f"User {update.effective_user.id} lost temp_delivery_data in handle_gift_choice")
        await query.edit_message_text("Ошибка сессии. Начните оформление заново.")
        return ConversationHandler.END

    if query.data is None:
        return ConversationHandler.END

    parts: list[str] = query.data.split(":")

    if parts[0] == gift_for_me_callback:
        logger.info(f"User {update.effective_user.id} finalized order as 'For Me'")
        return cast(int, await finalize_order_and_pay_fn(update, context, **delivery_data, is_gift=False))

    elif parts[0] == gift_as_present_callback:
        logger.info(f"User {update.effective_user.id} selected 'As Gift'. Prompting for comment.")
        await query.edit_message_text(
            "🎁 <b>Заказ в подарок</b>\n\n"
            "Напишите текст поздравления или пожелания, который мы приложим к заказу.\n\n"
            "Вы также можете нажать кнопку ниже, чтобы оставить заказ без открытки.",
            reply_markup=get_gift_comment_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return awaiting_gift_comment_state

    return ConversationHandler.END


async def handle_gift_comment(update: Update, context: ContextTypes.DEFAULT_TYPE, finalize_order_and_pay_fn: Any) -> int:
    if update.effective_user is None:
        return ConversationHandler.END

    if update.message is None or update.message.text is None:
        return ConversationHandler.END

    user_id = update.effective_user.id
    user_data: dict[str, Any] = context.user_data or {}
    user_service: UserService = context.bot_data['user_service']

    comment: str | None = update.message.text
    if comment == '/skip':
        comment = None

    logger.debug("handle_gift_comment: Comment received: %s", comment)
    delivery_data = user_data.get('temp_delivery_data')
    if not delivery_data:
        logger.warning(f"User {user_id} lost temp_delivery_data in handle_gift_comment")
        return ConversationHandler.END

    status_msg = await context.bot.send_message(chat_id=user_id, text="⏳ Оформляем ваш подарок...")
    new_id = status_msg.message_id

    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_gift.py] TelegramError: {e}")

    return cast(int, await finalize_order_and_pay_fn(
        update,
        context,
        **delivery_data,
        is_gift=True,
        gift_comment=comment,
    ))


async def start_ai_gift_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gift_back_callback: str,
    awaiting_gift_ai_data_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return awaiting_gift_ai_data_state

    await query.answer()

    if query.message is None:
        return awaiting_gift_ai_data_state

    text = (
        "✨ <b>Мастерская поздравлений KOJO</b>\n\n"
        "Напишите коротко: <b>кому</b> этот подарок и <b>какой повод</b>?\n"
        "<i>Пример: 'Для подруги на новоселье, она очень веселая' или 'Коллеге на юбилей, любит классику'.</i>"
    )

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=gift_back_callback)]])

    msg = await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    user_data: dict[str, Any] = context.user_data or {}
    if isinstance(msg, Message):
        user_data['last_global_menu_id'] = msg.message_id

    return awaiting_gift_ai_data_state


async def process_ai_gift_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gift_as_present_callback: str,
    awaiting_gift_ai_data_state: int,
) -> int:
    if update.effective_user is None:
        return awaiting_gift_ai_data_state

    if update.message is None or update.message.text is None:
        return awaiting_gift_ai_data_state

    user_input = update.message.text.strip()
    user_id = update.effective_user.id
    user_data: dict[str, Any] = context.user_data or {}
    user_service: UserService = context.bot_data['user_service']

    status_msg = await context.bot.send_message(user_id, "⏳ <b>Сочиняем идеальные слова...</b>", parse_mode=ParseMode.HTML)
    new_id = status_msg.message_id

    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_gift.py] TelegramError: {e}")

    ai_service: AICommunicationService = context.bot_data['ai_comm_service']
    options = await ai_service.get_ai_gift_greetings(user_input)

    if not options:
        await status_msg.edit_text(
            "К сожалению, нейросеть сейчас не может помочь. Пожалуйста, напишите текст поздравления самостоятельно.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Написать самому", callback_data=gift_as_present_callback)]]),
        )
        return awaiting_gift_ai_data_state

    user_data['ai_gift_options'] = options

    text = "✨ <b>Выберите подходящий вариант для открытки:</b>\n\n"
    for i, opt in enumerate(options):
        text += f"<b>Вариант {i+1}:</b>\n{opt}\n\n"

    from tg_bot.keyboards import get_ai_gift_options_keyboard

    await status_msg.edit_text(text, reply_markup=get_ai_gift_options_keyboard(len(options)), parse_mode=ParseMode.HTML)
    return awaiting_gift_ai_data_state


async def select_ai_gift_option(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    finalize_order_and_pay_fn: Any,
    prefix_ai_gift_select_callback: str,
    awaiting_gift_comment_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return awaiting_gift_comment_state

    if query.data is None:
        return awaiting_gift_comment_state

    idx = int(query.data.replace(prefix_ai_gift_select_callback, ""))

    user_data: dict[str, Any] = context.user_data or {}
    options: list[str] = user_data.get('ai_gift_options', [])
    if not options or idx >= len(options):
        await query.answer("Ошибка выбора варианта.", show_alert=True)
        return awaiting_gift_comment_state

    selected_text = options[idx]
    delivery_data = user_data.get('temp_delivery_data')
    if not delivery_data:
        await query.answer("Ошибка сессии.", show_alert=True)
        return awaiting_gift_comment_state

    await query.answer("Текст выбран! ✨")

    logger.debug("AI Gift selected: %s", selected_text)
    return cast(int, await finalize_order_and_pay_fn(
        update,
        context,
        **delivery_data,
        is_gift=True,
        gift_comment=selected_text,
    ))


async def handle_ai_gift_retry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gift_as_present_callback: str,
    awaiting_gift_ai_data_state: int,
) -> int:
    if update.effective_user is None:
        return awaiting_gift_ai_data_state

    query = update.callback_query
    if query is None:
        return awaiting_gift_ai_data_state

    await query.answer()

    if query.message is None:
        return awaiting_gift_ai_data_state

    text = (
        "🔄 <b>Давайте попробуем ещё раз!</b>\n\n"
        "Пожалуйста, переформулируйте ваш запрос. Опишите детали, которые важно упомянуть, или укажите желаемый стиль."
    )

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=gift_as_present_callback)]])

    msg = await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    user_data: dict[str, Any] = context.user_data or {}
    if isinstance(msg, Message):
        user_data['last_global_menu_id'] = msg.message_id

    logger.info(f"User {update.effective_user.id} requested AI gift retry.")
    return awaiting_gift_ai_data_state
