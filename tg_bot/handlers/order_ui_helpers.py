import logging

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from utils.ui_formatters import format_product_card_html

logger = logging.getLogger(__name__)


def truncate_caption(text: str, limit: int = 1010) -> tuple[str, bool]:
    """Обрезает текст по лимиту, стараясь не рвать абзацы."""
    if len(text) <= limit:
        return text, False

    # Обрезаем до лимита
    truncated = text[:limit]
    # Ищем последний двойной перенос (конец абзаца)
    last_paragraph = truncated.rfind('\n\n')

    if last_paragraph > 200:  # Если абзац не слишком короткий
        return text[:last_paragraph] + "\n\n...", True

    # Если абзацев нет, просто режем по пробелу
    last_space = truncated.rfind(' ')
    return text[:last_space] + "...", True


async def show_full_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    read_full_desc_callback: str,
    close_generic_callback: str,
) -> None:
    """Показывает полное структурированное описание без фото."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    assert query.data is not None
    product_id = int(query.data.replace(read_full_desc_callback, ""))
    product_service = context.bot_data['product_service']
    product = await product_service.get_product_by_id(product_id)

    if not product:
        logger.warning(f"Product {product_id} not found for full description")
        return

    # Применяем наш золотой стандарт форматирования
    # Используем ту же функцию, что и для основной карточки
    full_text = format_product_card_html(product)

    # Добавляем эмодзи в начало для обозначения режима "чтения"
    full_text = "📖 <b>ПОЛНОЕ ОПИСАНИЕ</b>\n\n" + full_text

    logger.info(f"Showing formatted full description for product: {product.name}")
    logger.debug("show_full_description: Rendering %s characters", len(full_text))

    # Отправляем новым сообщением, так как в старое (с фото) оно точно не влезет
    chat = update.effective_chat
    assert chat is not None
    await context.bot.send_message(
        chat_id=chat.id,
        text=full_text,
        parse_mode=ParseMode.HTML,
        # Кнопка закрытия, чтобы не мусорить в чате
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Закрыть описание", callback_data=close_generic_callback)
        ]])
    )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert context.user_data is not None
    context.user_data.clear()
    message = update.message
    assert message is not None
    await message.reply_text("Диалог завершен.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def exit_to_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Безопасный переход из процесса заказа ПРЯМО в админ-панель."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    assert context.user_data is not None
    for key in ['viewed_product_quantity', 'prod_img_index', 'temp_delivery_data', 'editing_order_id']:
        context.user_data.pop(key, None)

    # [критично] вызываем panel_start (админку), а не show_staff_main_menu
    from tg_bot.handlers.admin_panel import panel_start
    await panel_start(update, context)

    return ConversationHandler.END


async def exit_to_user_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Безопасный выход в главное меню с завершением разговора."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError) as exc:
            logger.warning(f"[databases/kojo/tg_bot/handlers/order_ui_helpers.py] TelegramError: {exc}")

    assert context.user_data is not None
    for key in ['viewed_product_quantity', 'prod_img_index', 'temp_delivery_data', 'editing_order_id']:
        context.user_data.pop(key, None)

    # Импортируем внутри, чтобы избежать циклической зависимости
    from tg_bot.handlers.registration import show_main_menu_from_welcome

    # Вызываем стабильную, проверенную функцию отрисовки
    await show_main_menu_from_welcome(update, context)

    # Выходим из conversationhandler
    return ConversationHandler.END
