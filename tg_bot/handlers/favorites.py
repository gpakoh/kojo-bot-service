# Tg_bot/handlers/favorites.py
import logging
from typing import Any, Optional, cast

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from tg_bot.decorators import auth_guard
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import (
    CB_FAV_ADD_CART,
    CB_FAV_CART_CLEAR,
    CB_FAV_DEC_CART,
    CB_FAV_INC_CART,
    CB_FAV_UNDO_RM,
    CB_FAVORITES_MENU,
    CB_PREFIX_FAV_QTY_GRID,
    CB_PREFIX_FAV_SET_QTY,
    CB_PREFIX_NOTIFY_FAV,
    CB_PREFIX_RM_FAV,
    CB_PREFIX_TOGGLE_FAV,
    CB_RECIPE_DELETE,
    CB_RECIPE_VIEW_SAVED,
    get_fav_quantity_grid_keyboard,
    get_favorites_hub_keyboard,
    get_favorites_list_keyboard,
    get_saved_recipe_view_keyboard,
)

logger = logging.getLogger(__name__)

STATE_HOME = 0

async def _get_fav_data(user_id: int, fav_service: Any, product_service: Any) -> list[Any]:
    fav_ids = await fav_service.get_user_favorites(user_id)
    data = []
    for pid in fav_ids:
        p = await product_service.get_product_by_id(pid)
        if not p:
            continue
        notify = await fav_service.get_notification_status(user_id, pid)
        data.append({'product': p, 'is_available': p.is_available, 'notify_status': notify})
    return data


@auth_guard()
async def show_favorites_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    fav_service = context.bot_data['favorite_service']

    prod_count = await fav_service.get_favorites_count(user_id)
    saved_recipes = await fav_service.get_saved_recipes(user_id)
    rec_count = len(saved_recipes)

    text = (
        "❤️ <b>Ваше избранное</b>\n\n"
        "Здесь хранятся ваши любимые лоты кофе и персональные рецепты от AI-бариста.\n\n"
        "Выберите раздел:"
    )

    markup = get_favorites_hub_keyboard(prod_count, rec_count)

    try:
        if query and query.message and not (query.message.photo or query.message.document):
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await cleanup_previous_menu(context, user_id)
            sent_msg = await context.bot.send_message(user_id, text, reply_markup=markup, parse_mode='HTML')

            user_data = context.user_data
            if user_data is not None:
                user_data['last_global_menu_id'] = sent_msg.message_id
            user_service = context.bot_data['user_service']
            await user_service.save_registration_message_id(user_id, sent_msg.message_id)
            logger.debug("UI Anchor: New Text anchor set (from Hub): %s", sent_msg.message_id)

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error rendering Fav Hub: {e}")

    return STATE_HOME

@auth_guard()
async def show_favorite_products(update: Update, context: ContextTypes.DEFAULT_TYPE, deleted_product: Optional[Any] = None) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    user_id = update.effective_user.id

    fav_service = context.bot_data['favorite_service']
    product_service = context.bot_data['product_service']
    cart_service = context.bot_data['cart_service']

    favorites_data = await _get_fav_data(user_id, fav_service, product_service)
    cart = await cart_service.get_cart(user_id)

    if deleted_product:
        favorites_data.append({'product': deleted_product, 'is_available': True, 'notify_status': False})

    if not favorites_data:
        text = "<b>Ваш список избранных товаров пуст.</b>\n\nНо у вас могут быть сохраненные рецепты!"
        from tg_bot.keyboards import CB_FAVORITES_MENU
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в Избранное", callback_data=CB_FAVORITES_MENU)]])
    else:
        text = "🛍 <b>Ваши избранные товары</b>\n\nЗдесь вы можете быстро добавить их в корзину."
        if deleted_product:
            markup = get_favorites_list_keyboard(favorites_data, cart, deleted_id=int(deleted_product.id))
        else:
            markup = get_favorites_list_keyboard(favorites_data, cart)

    msg = None
    if query:
        msg = await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        msg = await context.bot.send_message(user_id, text, reply_markup=markup, parse_mode=ParseMode.HTML)

    if isinstance(msg, Message):
        user_data = context.user_data
        if user_data is not None:
            user_data['last_fav_list_msg_id'] = msg.message_id

    return STATE_HOME


@auth_guard()
async def show_fav_quantity_grid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if query.data is None:
        return
    product_id = int(query.data.replace(CB_PREFIX_FAV_QTY_GRID, ""))
    reply_markup = get_fav_quantity_grid_keyboard(product_id)

    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/favorites.py] TelegramError: {e}")
    return STATE_HOME

@auth_guard()
async def handle_fav_preset_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    data = query.data.replace(CB_PREFIX_FAV_SET_QTY, "")
    product_id, value = map(int, data.split('_'))

    await context.bot_data['cart_service'].update_item(update.effective_user.id, product_id, value)
    await query.answer(f"Обновлено: {value} шт.")

    return await show_favorite_products(update, context)

@auth_guard()
async def handle_fav_cart_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    product_id = int(query.data.replace(CB_FAV_CART_CLEAR, ""))

    await context.bot_data['cart_service'].remove_item(update.effective_user.id, product_id)
    await query.answer("Убрано из корзины 🗑")

    return await show_favorite_products(update, context)


@auth_guard()
async def handle_fav_cart_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    data = query.data
    user_id = update.effective_user.id
    cart_service = context.bot_data['cart_service']

    product_id = int(data.split('_')[-1])
    cart = await cart_service.get_cart(user_id)
    current_qty = cart.get(str(product_id), {}).get('quantity', 0)

    if CB_FAV_ADD_CART in data or CB_FAV_INC_CART in data:
        await cart_service.update_item(user_id, product_id, current_qty + 1)
        await query.answer("Добавлено")
    elif CB_FAV_DEC_CART in data:
        if current_qty <= 1:
            await cart_service.remove_item(user_id, product_id)
            await query.answer("Убрано")
        else:
            await cart_service.update_item(user_id, product_id, current_qty - 1)
            await query.answer("Уменьшено")

    return await show_favorite_products(update, context)

@auth_guard()
async def remove_favorite_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    if update.effective_chat is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    product_id = int(query.data.replace(CB_PREFIX_RM_FAV, ""))
    user_id = update.effective_user.id

    product = await context.bot_data['product_service'].get_product_by_id(product_id)
    await context.bot_data['favorite_service'].remove_favorite(user_id, product_id)

    await show_favorite_products(update, context, deleted_product=product)
    msg_id = (context.user_data or {}).get('last_fav_list_msg_id')

    if msg_id:
        job_name = f"undo_fav_{user_id}"
        jq = context.job_queue
        if jq is not None:
            existing_jobs = jq.get_jobs_by_name(job_name)
            for j in existing_jobs:
                try:
                    j.schedule_removal()
                except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/handlers/favorites.py] TelegramError: {e}")

            jq.run_repeating(
                _fav_countdown_job,
                interval=1,
                first=1,
                data={
                    'chat_id': update.effective_chat.id,
                    'user_id': user_id,
                    'message_id': msg_id,
                    'product_id': product_id,
                    'seconds': 5
                },
                name=job_name
            )

    await query.answer()
    return STATE_HOME

async def _internal_render_fav_for_undo(update: Update, context: ContextTypes.DEFAULT_TYPE, product: Any) -> Any:
    await show_favorite_products(update, context, deleted_product=product)
    return (context.user_data or {}).get('last_fav_list_msg_id')


async def _fav_countdown_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    data = cast(dict[str, Any], job.data)
    data['seconds'] -= 1

    if data['seconds'] <= 0:
        try:
            job.schedule_removal()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/favorites.py] TelegramError: {e}")

    app = context.application
    user_id = data['user_id']

    try:
        fav_ids = await app.bot_data['favorite_service'].get_user_favorites(user_id)
        fav_data = []
        for pid in fav_ids:
            p = await app.bot_data['product_service'].get_product_by_id(pid)
            if p:
                fav_data.append({'product': p, 'is_available': p.is_available, 'notify_status': False})

        if data['seconds'] > 0:
            deleted_p = await app.bot_data['product_service'].get_product_by_id(data['product_id'])
            if deleted_p:
                fav_data.append({'product': deleted_p, 'is_available': True, 'notify_status': False})

        if not fav_data:
            text = "<b>Список избранных товаров пуст.</b>"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в Избранное", callback_data=CB_FAVORITES_MENU)]])
        else:
            text = "🛍 <b>Ваши избранные товары</b>"
            cart = await app.bot_data['cart_service'].get_cart(user_id)
            if data['seconds'] > 0:
                reply_markup = get_favorites_list_keyboard(
                    fav_data, cart,
                    deleted_id=int(data['product_id']),
                    timer=data['seconds']
                )
            else:
                reply_markup = get_favorites_list_keyboard(fav_data, cart, timer=data['seconds'])

        try:
            await app.bot.edit_message_text(
                chat_id=data['chat_id'],
                message_id=data['message_id'],
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise e

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Job Error in fav_countdown: {e}")
        try:
            job.schedule_removal()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/favorites.py] TelegramError: {e}")


@auth_guard()
async def undo_remove_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    product_id = int(query.data.replace(CB_FAV_UNDO_RM, ""))
    user_id = update.effective_user.id

    job_name = f"undo_fav_{user_id}"
    jq = context.job_queue
    if jq is not None:
        for j in jq.get_jobs_by_name(job_name):
            try:
                j.schedule_removal()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/favorites.py] TelegramError: {e}")

    await context.bot_data['favorite_service'].add_favorite(user_id, product_id)
    await query.answer("Возвращено! ❤️")

    return await show_favorite_products(update, context)

@auth_guard()
async def toggle_favorite_in_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    data = query.data.replace(CB_PREFIX_TOGGLE_FAV, "")
    parts = data.split('_')
    product_id, category = int(parts[0]), parts[1]

    details_shown = (parts[2] == "det") if len(parts) > 2 else False

    user_id = update.effective_user.id
    await context.bot_data['favorite_service'].toggle_favorite(user_id, product_id)

    await query.answer("Избраное обновлено ❤️")

    view_mode = (context.user_data or {}).get('view_mode', 'list')

    if view_mode == 'gallery':
        from tg_bot.handlers.order import show_gallery_view
        logger.info(f"❤️ Toggle in Gallery: Stay in gallery for user {user_id}")
        return await show_gallery_view(update, context)
    else:
        from tg_bot.handlers.order import show_product_view
        logger.info(f"❤️ Toggle in Card: Stay in product view for user {user_id}")
        return await show_product_view(
            update, context,
            product_id=product_id,
            category=category,
            force_details=details_shown
        )


@auth_guard()
async def toggle_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    product_id = int(query.data.replace(CB_PREFIX_NOTIFY_FAV, ""))
    user_id = update.effective_user.id

    current = await context.bot_data['favorite_service'].get_notification_status(user_id, product_id)
    await context.bot_data['favorite_service'].set_notification(user_id, product_id, not current)

    await query.answer("Статус уведомления изменен")
    return await show_favorite_products(update, context)

@auth_guard()
async def show_saved_recipes_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    fav_service = context.bot_data['favorite_service']

    recipes = await fav_service.get_saved_recipes(user_id)
    logger.debug("UI Recipes: Found %s recipes for user %s", len(recipes), user_id)

    if not recipes:
        text = "<b>У вас пока нет сохраненных рецептов.</b>\n\nВы можете создать их в карточке любого напитка через кнопку «Подробнее»."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в Избранное", callback_data=CB_FAVORITES_MENU)]])
    else:
        text = "📜 <b>Ваша книга рецептов KOJO</b>\n\nЗдесь собраны все рекомендации, которые составил для вас AI-бариста:"
        from tg_bot.keyboards import get_saved_recipes_keyboard
        markup = get_saved_recipes_keyboard(recipes)

    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error rendering recipes list: {e}")


@auth_guard()
async def show_saved_recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if query.data is None:
        return
    product_id = int(query.data.replace(CB_RECIPE_VIEW_SAVED, ""))
    user_id = update.effective_user.id
    fav_service = context.bot_data['favorite_service']

    recipes = await fav_service.get_saved_recipes(user_id)
    recipe = next((r for r in recipes if r['product_id'] == product_id), None)

    if not recipe:
        await query.answer("Рецепт не найден.", show_alert=True)
        return await show_saved_recipes_list(update, context)

    text = f"📖 <b>РЕЦЕПТ: {recipe['product_name'].upper()}</b>\n\n{recipe['recipe_text']}"

    await query.edit_message_text(text, reply_markup=get_saved_recipe_view_keyboard(product_id), parse_mode=ParseMode.HTML)

@auth_guard()
async def delete_recipe_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query is None:
        return
    if query.data is None:
        return
    product_id = int(query.data.replace(CB_RECIPE_DELETE, ""))
    user_id = update.effective_user.id

    fav_service = context.bot_data['favorite_service']
    await fav_service.delete_recipe(user_id, product_id)

    await query.answer("🗑 Рецепт удален из вашей книги")
    logger.info(f"User {user_id} deleted recipe for product {product_id}")

    return await show_saved_recipes_list(update, context)
