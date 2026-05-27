# Tg_bot/handlers/ai_chat.py
import logging
from typing import Any, cast

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from tg_bot.app_config import get_app_config
from tg_bot.decorators import auth_guard
from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram
from tg_bot.keyboards import (
    CB_AI_HIST_PAGE,
    get_ai_chat_keyboard,
    get_support_type_keyboard,
)
from tg_bot.tenant.config import FeatureFlags

logger = logging.getLogger(__name__)

@auth_guard()
async def start_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вход в режим общения с AI с защитой iOS Flush."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return

    user_data: dict[str, Any] = context.user_data or {}
    user_id = update.effective_user.id
    user_service = context.bot_data['user_service']
    user_data['is_ai_chat_mode'] = True

    text = (
        "🤖 <b>Режим AI-консультанта KOJO</b>\n\n"
        "Я знаю всё о нашем кофе, способах заваривания и условиях доставки. "
        "Просто напишите мне свой вопрос ниже.\n\n"
        "<i>Пример: 'Какой кофе самый кислый?' или 'Как варить в воронке?'</i>"
    )

    # [правило ios] 1. шлем новое сообщение
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=get_ai_chat_keyboard(),
        parse_mode='HTML'
    )
    new_id = msg.message_id

    # 2. фиксируем якорь в сессии
    user_data['last_ai_msg_id'] = new_id

    # 3. очищаем старое меню (старый якорь в бд), исключая новое сообщение
    from tg_bot.handlers.common import cleanup_previous_menu
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    # 4. сохраняем новый якорь в бд после зачистки
    await user_service.save_registration_message_id(user_id, new_id)

    # 5. локально удаляем сообщение‑источник колбэка, если оно ещё есть
    if query.message:
        try:
            await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/ai_chat.py] TelegramError: {e}")
    logger.info(f"🤖 AI Chat Started for {user_id}. Anchor: {new_id}")

@auth_guard()
async def handle_ai_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает историю с пагинацией (безопасный переход)."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return

    user_data: dict[str, Any] = context.user_data or {}
    user_id = update.effective_user.id
    user_service = context.bot_data['user_service']
    assert query.data is not None
    data = query.data

    if data == "ai_chat_history":
        await query.answer("Загружаю историю...")
    else:
        await query.answer()

    # Определяем страницу
    page_idx = 0
    if data.startswith(CB_AI_HIST_PAGE):
        page_idx = int(data.replace(CB_AI_HIST_PAGE, ""))

    # Кэшируем страницы
    pages = user_data.get('ai_history_cache')
    if not pages or data == "ai_chat_history":
        ai_service = context.bot_data['ai_comm_service']
        nickname = update.effective_user.username or update.effective_user.first_name
        result = await ai_service.get_chat_history_paged(user_id, nickname)
        pages = result.get("pages", ["История пуста."])
        user_data['ai_history_cache'] = pages

    total = len(pages)
    if page_idx >= total:
        page_idx = total - 1

    clean_text = prepare_html_for_telegram(pages[page_idx])
    text = f"📜 <b>Архив переписки (Стр. {page_idx + 1}/{total})</b>\n\n{clean_text}"

    from tg_bot.keyboards import get_ai_history_keyboard
    reply_markup = get_ai_history_keyboard(page_idx, total)

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True)
    except (ValueError, KeyError, telegram.error.TelegramError):
        msg = await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True)
        new_id = msg.message_id

        user_data['last_history_msg_id'] = new_id
        await user_service.save_registration_message_id(user_id, new_id)

        last_ai_msg = user_data.pop('last_ai_msg_id', None)
        if last_ai_msg and last_ai_msg != new_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=last_ai_msg)
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/ai_chat.py] TelegramError: {e}")

        if query.message:
            try:
                await query.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/ai_chat.py] TelegramError: {e}")


@auth_guard()
async def handle_router_ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Берет сообщение из буфера и передает в workflow AI, используя то же окно."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return

    user_data: dict[str, Any] = context.user_data or {}
    user_msg = user_data.get('pending_message_text')

    if not user_msg:
        from tg_bot.keyboards import CB_CLOSE_GENERIC
        close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]])
        await query.edit_message_text(
            "⚠️ <b>Ошибка: сообщение потеряно.</b>\n\nПожалуйста, попробуйте написать вопрос снова.",
            reply_markup=close_btn,
            parse_mode='HTML'
        )
        return

    user_data['is_ai_chat_mode'] = True
    user_data.pop('pending_message_text', None)

    logger.info(f"🚀 AI Router: Transforming router window into AI response (User: {update.effective_user.id})")

    ai_service = context.bot_data['ai_comm_service']
    app_config = get_app_config(context)
    flags = FeatureFlags(config=app_config)
    if await flags.is_enabled("lightrag"):
        logger.info("LightRAG path enabled for user %s", update.effective_user.id)
        await ai_service.handle_ai_workflow(update, context, override_topic=user_msg)
    else:
        await ai_service.handle_ai_workflow(update, context, override_topic=user_msg)


@auth_guard()
async def handle_router_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает выбор типа поддержки."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return

    user_id = update.effective_user.id
    order_service = context.bot_data['order_service']

    last_order = await order_service.get_last_active_order_for_user(user_id)
    all_orders = await order_service.get_orders_by_user_id(user_id)

    text = "💡 <b>Куда направить ваше сообщение?</b>\n\nВыберите категорию поддержки:"
    reply_markup = get_support_type_keyboard(
        last_order_id=cast(int, last_order.id) if last_order else None,
        has_orders=len(all_orders) > 0
    )

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def handle_back_to_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возвращает пользователя из меню выбора поддержки в меню выбора цели (AI/Поддержка)."""
    query = update.callback_query
    if query is None:
        return

    user_data: dict[str, Any] = context.user_data or {}
    user_msg = user_data.get('pending_message_text', '...')

    from tg_bot.keyboards import get_message_router_keyboard
    text = (
        f"❓ <b>Ваше сообщение в буфере:</b>\n\n"
        f"<i>«{user_msg[:100]}{'...' if len(user_msg) > 100 else ''}»</i>\n\n"
        f"Кому вы хотите адресовать этот вопрос?"
    )

    await query.edit_message_text(text, reply_markup=get_message_router_keyboard(), parse_mode='HTML')
