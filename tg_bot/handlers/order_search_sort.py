import logging
import re
from typing import Any

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from tg_bot.bot_services.ai_communication_service import AICommunicationService
from tg_bot.bot_services.product_service import ProductService
from tg_bot.bot_services.user_service import UserService
from tg_bot.handlers.common import cleanup_previous_menu, safe_delete_message
from tg_bot.keyboards import (
    CB_BACK_TO_CATEGORIES,
    CB_PREFIX_SET_SORT,
    CB_SEARCH_PRODUCTS,
    CB_USER_SHOW_MAIN_MENU,
)

logger = logging.getLogger(__name__)


async def toggle_view(update: Update, context: ContextTypes.DEFAULT_TYPE, show_sort_menu_fn: Any) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    mode = query.data.split('_')[-1]
    user_data['view_mode'] = mode
    logger.debug("toggle_view: new mode set to %s", mode)
    await query.answer(f"Вид: {mode}")
    return await show_sort_menu_fn(update, context)


async def show_sort_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, showing_products_state: int) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if query.message is None:
        return
    if update.effective_user is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    user_id = update.effective_user.id
    is_guest = user_data.get('is_guest', False)
    current_sort = user_data.get('sort_mode', 'default')
    view_mode = user_data.get('view_mode', 'list')
    category = user_data.get('current_category', 'all').lower()
    non_coffee_keywords = ['мерч', 'аксессуары', 'кружка', 'шоппер', 'кепка', 'gear', 'одежда']
    has_sca = not any(keyword in category for keyword in non_coffee_keywords)
    from tg_bot.keyboards import get_sort_menu_keyboard
    reply_markup = get_sort_menu_keyboard(current_sort, view_mode=view_mode, has_sca_data=has_sca, is_guest=is_guest)
    text = "🛠 <b>Настройки отображения</b>\nВыберите способ сортировки и вид каталога:"
    try:
        if query.message.photo:
            msg = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML',
            )
            new_id = msg.message_id
            user_data['last_global_menu_id'] = new_id
            await context.bot_data['user_service'].save_registration_message_id(user_id, new_id)
            await safe_delete_message(context, query.message.chat_id, query.message.message_id)
            await cleanup_previous_menu(context, user_id, exclude_id=new_id)
        else:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.debug("Sort menu render info: %s", e)
    logger.debug("UI Sort: Rendered for %s. Guest: %s", user_id, is_guest)
    return showing_products_state


async def apply_sort(update: Update, context: ContextTypes.DEFAULT_TYPE, show_sort_menu_fn: Any) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    sort_mode = query.data.replace(CB_PREFIX_SET_SORT, '')
    user_data['sort_mode'] = sort_mode
    logger.debug("apply_sort: new mode set to %s", sort_mode)
    await query.answer("Сортировка выбрана")
    return await show_sort_menu_fn(update, context)


async def ask_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE, awaiting_search_state: int) -> Any:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if query.message is None:
        return
    if update.effective_user is None:
        return
    await query.answer()
    text = "🔍 <b>Поиск товаров</b>\n\nВведите название кофе или вкусовую ноту (например: <i>Колумбия</i> или <i>Фруктовый кофе</i>):"
    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_BACK_TO_CATEGORIES)]])
    await query.edit_message_text(text, reply_markup=cancel_markup, parse_mode=ParseMode.HTML)
    return awaiting_search_state


async def process_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_product_list_fn: Any,
    awaiting_search_state: int,
) -> Any:
    if update.message is None or update.message.text is None:
        return
    if update.effective_user is None:
        return
    user_data: dict[str, Any] = context.user_data or {}
    raw_text = update.message.text.strip()
    search_query = re.sub(r'[^\w\s]+$', '', raw_text).strip()
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning("TelegramError: %s", e)
    logger.info("🔎 Поиск от %s: «%s» (исходный: «%s»)", user_id, search_query, raw_text)
    if len(search_query) < 2:
        msg = await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ <b>Запрос слишком короткий.</b>\nВведите хотя бы 2 символа:",
            parse_mode='HTML',
        )
        new_id = msg.message_id
        await cleanup_previous_menu(context, user_id, exclude_id=new_id)
        user_data['last_global_menu_id'] = new_id
        await user_service.save_registration_message_id(user_id, new_id)
        return awaiting_search_state
    product_service: ProductService = context.bot_data['product_service']
    results = await product_service.search_products(search_query)
    if not results:
        logger.info("🔎 Поиск: по запросу «%s» ничего не найдено. Пробуем семантику...", search_query)
        user_data['last_failed_query'] = search_query
        logger.info("🧠 [Auto-RAG] Запуск автоматического семантического поиска для «%s»", search_query)
        ai_service: AICommunicationService = context.bot_data['ai_comm_service']
        try:
            product_names = await ai_service.get_semantic_retrieval(search_query)
            logger.info("📦 [Auto-RAG] RAG вернул %s названий: %s", len(product_names), product_names[:5])
            if product_names:
                all_available = await product_service.get_available_products(light_mode=True)
                normalized_rag_names = [name.lower().strip() for name in product_names]
                found_products = []
                for p in all_available:
                    db_name = p.name.lower().strip()
                    search_blob = " ".join([
                        db_name,
                        (getattr(p, "search_variants", "") or "").lower(),
                        (p.short_description or "").lower(),
                    ])
                    if any((rag_n in db_name or db_name in rag_n or rag_n in search_blob) for rag_n in normalized_rag_names):
                        found_products.append(p)
                if found_products:
                    logger.info("✅ [Auto-RAG] Найдено %s товаров через RAG!", len(found_products))
                    user_data['current_category'] = 'search'
                    user_data['search_results'] = found_products
                    user_data['last_search_query'] = f"{search_query} 🤖"
                    if 'products' not in user_data:
                        user_data['products'] = {}
                    for p in found_products:
                        user_data['products'][p.id] = p
                    return await show_product_list_fn(update, context)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.error("Ошибка в автоматическом семантическом поиске: %s", e)
        text = (
            f"🔍 <b>Поиск: «{search_query}»</b>\n\n"
            f"К сожалению, ничего не найдено. 😔\n\n"
            f"💡 <i>Попробуйте:</i>\n"
            f"• Изменить запрос (например, 'шоколад' вместо 'горький')\n"
            f"• Использовать вкусовые ноты ('фруктовый', 'ореховый')\n"
            f"• Выбрать категорию в меню"
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Искать снова", callback_data=CB_SEARCH_PRODUCTS)],
            [InlineKeyboardButton("🗂 Перейти в каталог", callback_data=CB_BACK_TO_CATEGORIES)],
            [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)],
        ])
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML',
        )
        new_id = msg.message_id
        await cleanup_previous_menu(context, user_id, exclude_id=new_id)
        user_data['last_global_menu_id'] = new_id
        await user_service.save_registration_message_id(user_id, new_id)
        return awaiting_search_state
    user_data['current_category'] = 'search'
    user_data['search_results'] = results
    user_data['last_search_query'] = search_query
    if 'products' not in user_data:
        user_data['products'] = {}
    for p in results:
        user_data['products'][p.id] = p
    logger.info("✅ Search Success: Found %s items for query '%s'", len(results), search_query)
    logger.debug("Search: Found %s items for user %s", len(results), user_id)
    return await show_product_list_fn(update, context)


async def handle_semantic_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_categories_fn: Any,
    show_product_list_fn: Any,
    showing_categories_state: int,
    awaiting_search_state: int,
) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return showing_categories_state
    if query.message is None:
        return showing_categories_state
    if update.effective_user is None:
        return showing_categories_state
    user_data: dict[str, Any] = context.user_data or {}
    user_id = update.effective_user.id
    search_query = user_data.get('last_failed_query')
    if not search_query:
        logger.warning("Semantic search triggered without query for user %s", user_id)
        await query.answer("Запрос потерян. Попробуйте поиск заново.")
        return await show_categories_fn(update, context)  # type: ignore[no-any-return]
    await query.answer("🧠 Нейросеть изучает каталог...")
    logger.info("🧠 [RAG-Search] Старт умного поиска для %s по: '%s'", user_id, search_query)
    ai_service: AICommunicationService = context.bot_data['ai_comm_service']
    try:
        product_names = await ai_service.get_semantic_retrieval(search_query)
        logger.debug("RAG raw names found: %s", product_names)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error("Error during semantic retrieval: %s", e)
        product_names = []
    if not product_names:
        text = (
            f"🔍 <b>Умный поиск: «{search_query}»</b>\n\n"
            f"К сожалению, даже нейросеть не нашла подходящих вариантов. 😔\n"
            f"Попробуйте использовать другие ключевые слова (например, 'ягодный' или 'темная обжарка')."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Попробовать снова", callback_data=CB_SEARCH_PRODUCTS)],
                [InlineKeyboardButton("⬅️ В каталог", callback_data=CB_BACK_TO_CATEGORIES)],
            ]),
            parse_mode='HTML',
        )
        return awaiting_search_state
    product_service: ProductService = context.bot_data['product_service']
    all_available = await product_service.get_available_products(light_mode=False)
    found_products = []
    normalized_rag_names = [name.lower().strip() for name in product_names]
    for p in all_available:
        db_name = p.name.lower().strip()
        match_found = False
        if any((rag_n in db_name or db_name in rag_n) for rag_n in normalized_rag_names):
            match_found = True
        if not match_found:
            db_words = set(db_name.replace(',', '').split())
            for rag_n in normalized_rag_names:
                rag_words = set(rag_n.replace(',', '').split())
                common = db_words & rag_words
                if len(common) >= 2 or (len(rag_words) > 0 and len(common) / len(rag_words) >= 0.5):
                    match_found = True
                    break
        if not match_found:
            search_blob = " ".join([
                db_name,
                (getattr(p, "search_variants", "") or "").lower(),
                (p.short_description or "").lower(),
                (p.full_description or "").lower(),
            ])
            if any(rag_n in search_blob for rag_n in normalized_rag_names):
                match_found = True
        if match_found:
            found_products.append(p)
            logger.debug("Semantic match: RAG '%s...' -> DB '%s'", product_names[:2], p.name)
    if found_products:
        unique_found = {p.id: p for p in found_products}.values()
        found_products = list(unique_found)
        user_data['current_category'] = 'search'
        user_data['search_results'] = found_products
        clean_query = search_query.strip()
        user_data['last_search_query'] = f"{clean_query} 🤖"
        if 'products' not in user_data:
            user_data['products'] = {}
        for p in found_products:
            user_data['products'][p.id] = p
        logger.info("✅ [RAG-Search] Успех! Найдено %s товаров.", len(found_products))
        return await show_product_list_fn(update, context)  # type: ignore[no-any-return]
    logger.warning("RAG found products %s, but none are available in DB.", product_names)
    await query.edit_message_text(
        f"🔍 <b>Умный поиск: «{search_query}»</b>\n\n"
        f"Я нашел упоминания подходящих товаров в базе знаний, но в данный момент их нет в наличии. 🤷‍♂️",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К категориям", callback_data=CB_BACK_TO_CATEGORIES)]]),
        parse_mode='HTML',
    )
    return showing_categories_state
