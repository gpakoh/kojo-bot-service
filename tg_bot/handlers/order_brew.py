import logging
from typing import Any

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram
from tg_bot.models import Product

logger = logging.getLogger(__name__)


async def show_brewing_methods_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_product_for_view_fn: Any,
    brew_guide_callback: str,
    viewing_product_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return viewing_product_state
    if query.data is None:
        return viewing_product_state
    await query.answer()

    product_id = int(query.data.replace(brew_guide_callback, ""))
    user_data: dict[str, Any] = context.user_data or {}
    category = user_data.get('current_category', 'all')

    product = await get_product_for_view_fn(product_id, context)
    if not product:
        return viewing_product_state

    is_tea = any(w in product.name.lower() or w in str(product.chapters).lower() for w in ['чай', 'tea', 'улун', 'пуэр'])

    text = (
        f"☕️ <b>{product.name}</b>\n\n"
        f"Для какого способа заваривания составить рецепт?"
    )

    from tg_bot.keyboards import get_brewing_methods_keyboard

    await query.edit_message_caption(
        caption=text,
        reply_markup=get_brewing_methods_keyboard(product_id, category, is_tea),
        parse_mode='HTML',
    )
    return viewing_product_state


def get_brew_method_label(method_code: str) -> str:
    method_names = {
        "espresso": "Эспрессо",
        "aeropress": "Аэропресс",
        "v60": "V60 (Воронка)",
        "chemex": "Кемекс",
        "cezve": "Турка",
        "french": "Френч-пресс",
        "cold_coffee": "Cold Brew",
        "gongfu": "Проливом",
        "infusion": "Настаиванием",
    }
    label = method_names.get(method_code, "Классический способ")
    logger.debug("Brew Parser: Code '%s' -> Label '%s'", method_code, label)
    return label


async def prepare_recipe_content(product: Product, method_label: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    ai_service = context.bot_data['ai_comm_service']

    full_info = f"Название: {product.name}\nКатегории: {', '.join(product.chapters)}\nОписание: {product.full_description}"

    recipe_raw = await ai_service.get_brewing_guide(product.name, full_info, method=method_label)

    recipe_text = prepare_html_for_telegram(recipe_raw)

    user_data: dict[str, Any] = context.user_data or {}
    user_data['last_generated_recipe'] = recipe_text

    header = f"📖 <b>{method_label.upper()}: {product.name.upper()}</b>\n\n"
    footer = "\n\n⚠️ <i>AI может ошибаться. Экспериментируйте!</i>"

    logger.debug("Recipe Generator: Content prepared, length=%s", len(recipe_text))
    return header + recipe_text + footer


async def display_brewing_guide(query: Any, user_id: int, full_text: str, markup: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_service = context.bot_data.get('user_service')

    if len(full_text) > 1024:
        logger.info("Recipe long (%s), switching to text message.", len(full_text))

        msg = await context.bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=markup,
            parse_mode='HTML',
        )
        new_id = msg.message_id

        user_data: dict[str, Any] = context.user_data or {}
        user_data['last_global_menu_id'] = new_id
        if user_service:
            await user_service.save_registration_message_id(user_id, new_id)

        try:
            await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError):
            logger.warning("Display_brewing_guide Delete Error")

        await cleanup_previous_menu(context, user_id, exclude_id=new_id)
    else:
        await query.edit_message_caption(
            caption=full_text,
            reply_markup=markup,
            parse_mode='HTML',
        )
    logger.debug("Brew Renderer: Render complete for user %s", user_id)


async def show_brewing_guide(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_product_for_view_fn: Any,
    get_brew_method_label_fn: Any,
    prepare_recipe_content_fn: Any,
    display_brewing_guide_fn: Any,
    brew_method_select_callback: str,
    prefix_select_product_callback: str,
    viewing_product_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return viewing_product_state
    if query.data is None:
        return viewing_product_state
    if update.effective_user is None:
        return viewing_product_state

    user_id = update.effective_user.id
    user_data: dict[str, Any] = context.user_data or {}
    category = user_data.get('current_category', 'all')

    try:
        payload = query.data.replace(brew_method_select_callback, "").split("_")
        product_id, method_code = int(payload[0]), payload[1]
    except (ValueError, IndexError):
        await query.answer("Ошибка данных")
        return viewing_product_state

    await query.answer("👨‍🍳 Мастер готовит инструкцию...")

    product = await get_product_for_view_fn(product_id, context)
    if not product:
        return viewing_product_state

    method_label = get_brew_method_label_fn(method_code)

    try:
        loading_cap = f"☕️ <b>{product.name}</b>\n\n⏳ <i>Составляю рецепт для: <b>{method_label}</b>...</i>"
        await query.edit_message_caption(caption=loading_cap, parse_mode='HTML')
    except (ValueError, KeyError, telegram.error.TelegramError):
        logger.warning("Show_brewing_guide Loading Caption Error")

    full_display_text = await prepare_recipe_content_fn(product, method_label, context)

    if "ошибка" in full_display_text.lower():
        error_msg = "⚠️ <b>Ошибка генерации.</b>\nПожалуйста, попробуйте позже."
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=f"{prefix_select_product_callback}{product_id}_{category}_details")]])
        await query.edit_message_caption(caption=error_msg, reply_markup=back_kb, parse_mode='HTML')
        return viewing_product_state

    fav_service = context.bot_data['favorite_service']
    is_saved = await fav_service.is_recipe_saved(user_id, product_id)

    from tg_bot.keyboards import get_recipe_view_keyboard

    reply_markup = get_recipe_view_keyboard(product_id, category, is_saved=is_saved)
    await display_brewing_guide_fn(query, user_id, full_display_text, reply_markup, context)

    return viewing_product_state


async def save_recipe_action(update: Update, context: ContextTypes.DEFAULT_TYPE, recipe_save_callback: str) -> None:
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    if update.effective_user is None:
        return

    product_id = int(query.data.replace(recipe_save_callback, ""))
    user_id = update.effective_user.id
    user_data: dict[str, Any] = context.user_data or {}
    category = user_data.get('current_category', 'all')

    recipe_text = user_data.get('last_generated_recipe')
    if not recipe_text:
        await query.answer("⚠️ Ошибка: данные рецепта устарели. Попробуйте сгенерировать заново.", show_alert=True)
        return

    fav_service = context.bot_data['favorite_service']
    await fav_service.save_recipe(user_id, product_id, recipe_text)

    await query.answer("✅ Рецепт сохранён в избранное!", show_alert=False)

    from tg_bot.keyboards import get_recipe_view_keyboard

    new_markup = get_recipe_view_keyboard(product_id, category, is_saved=True)

    try:
        await query.edit_message_reply_markup(reply_markup=new_markup)
        logger.info("Recipe %s saved for user %s. UI updated.", product_id, user_id)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error("Error updating recipe markup: %s", e)
