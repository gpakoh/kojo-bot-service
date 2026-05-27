import logging
from typing import Any, Optional, cast

import telegram
from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from tg_bot.bot_services.cart_service import CartService, CartValidationResult
from tg_bot.bot_services.product_service import ProductService
from tg_bot.bot_services.settings_service import SettingsService
from tg_bot.bot_services.user_service import UserService
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import (
    CB_CART_UNDO_RM,
    CB_CHECKOUT,
    CB_CLEAR_CART,
    CB_PREFIX_CART_DEC,
    CB_PREFIX_CART_DEL,
    CB_PREFIX_CART_INC,
    CB_PREFIX_CART_QTY_GRID,
    CB_PREFIX_CART_SET_QTY,
    get_cart_edit_keyboard,
    get_cart_keyboard,
    get_cart_quantity_grid_keyboard,
    get_delivery_method_keyboard,
)

logger = logging.getLogger(__name__)


def get_cart_text_and_total(cart: dict[str, Any], products: dict[str, Any]) -> tuple[str, float]:
    if not cart:
        return "🛒 Ваша корзина пуста.", 0.0

    text = "🛒 <b>Ваша корзина:</b>\n\n"
    total = 0.0

    for product_id, item_data in cart.items():
        product = products.get(str(product_id))
        if product:
            quantity = item_data['quantity']
            price = float(product.variants[0].price) if product.variants else 0.0
            item_total = price * quantity

            text += f"• <b>{product.name}</b> ({quantity} шт.) - {item_total}₽\n"
            if product.short_description:
                text += f"  <i>{product.short_description}</i>\n"

            total += item_total

    text += f"\n<b>Итого:</b> {total}₽"
    return text, total


async def show_cart(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_and_cache_all_products_fn: Any,
    show_categories_fn: Any,
    cart_view_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return cart_view_state
    if query.data is None:
        return cart_view_state
    if query.message is None:
        return cart_view_state
    if update.effective_user is None:
        return cart_view_state
    if update.effective_chat is None:
        return cart_view_state
    user_id = update.effective_user.id
    user_service: UserService = cast(UserService, context.bot_data.get('user_service'))

    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_cart.py] TelegramError: {e}")

    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))

    status, message = await cart_service.validate_cart(user_id)
    if status == CartValidationResult.CLEARED_OLD:
        assert message is not None
        await query.edit_message_text(message, parse_mode=ParseMode.HTML)
        return cast(int, await show_categories_fn(update, context))

    warning_text = ""
    if status == CartValidationResult.ITEM_UNAVAILABLE:
        warning_text = f"\n\n🛑 <b>Внимание:</b> {message}"

    cart = await cart_service.get_cart(user_id)
    products = await get_and_cache_all_products_fn(context)
    cart_text, _ = get_cart_text_and_total(cart, products)
    final_text = cart_text + warning_text

    user_data = context.user_data
    if user_data is None:
        return cart_view_state
    is_staff = user_data.get('is_staff_order', False)
    reply_markup = get_cart_keyboard(cart, is_staff=is_staff)

    sent_msg = await context.bot.send_message(
        chat_id=user_id,
        text=final_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
    new_id = sent_msg.message_id

    user_data['last_global_menu_id'] = new_id
    await user_service.save_registration_message_id(user_id, new_id)

    if isinstance(query.message, Message):
        try:
            await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/order_cart.py] TelegramError: {e}")
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    logger.info(f"Cart UI: Rendered {new_id} for {user_id}. iOS Flush applied.")
    return cart_view_state


async def show_cart_edit_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_and_cache_all_products_fn: Any,
    cart_view_state: int,
    deleted_id: Optional[int] = None,
) -> int:
    query = update.callback_query
    if query is None:
        return cart_view_state
    if query.data is None:
        return cart_view_state
    if query.message is None:
        return cart_view_state
    if update.effective_user is None:
        return cart_view_state
    if update.effective_chat is None:
        return cart_view_state
    user_id = update.effective_user.id
    user_data = context.user_data
    if user_data is None:
        return cart_view_state
    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))

    cart = await cart_service.get_cart(user_id)
    products = await get_and_cache_all_products_fn(context)

    deleted_qty = user_data.get(f'undo_qty_{deleted_id}', 0) if deleted_id else 0

    text = "✏️ <b>Редактирование корзины</b>\n\nИспользуйте ➖ и ➕ для изменения количества.\nНажмите ❌ для удаления товара."
    reply_markup = get_cart_edit_keyboard(cart, products, deleted_id=deleted_id, deleted_qty=deleted_qty)

    msg: Optional[Message] = None
    try:
        if not (query.message.photo or query.message.document):
            result = await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            if isinstance(result, Message):
                msg = result
        else:
            await query.message.delete()
            msg = await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.debug(f"UI update skipped (no changes): {e}")

    if isinstance(msg, Message):
        user_data['last_global_menu_id'] = msg.message_id

    return cart_view_state


async def handle_cart_edit_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    internal_cart_remove_fn: Any,
    show_cart_edit_mode_fn: Any,
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    if query.data is None:
        return ConversationHandler.END
    if query.message is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    if update.effective_chat is None:
        return ConversationHandler.END
    user_id = update.effective_user.id
    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))

    data: str = query.data
    product_id = int(data.split('_')[-1])
    cart = await cart_service.get_cart(user_id)
    current_qty = cart.get(str(product_id), {}).get('quantity', 0)

    if CB_PREFIX_CART_INC in data:
        await cart_service.update_item(user_id, product_id, current_qty + 1)
        await query.answer("Добавлено")
    elif CB_PREFIX_CART_DEC in data:
        if current_qty > 1:
            await cart_service.update_item(user_id, product_id, current_qty - 1)
            await query.answer("Уменьшено")
        else:
            return cast(int, await internal_cart_remove_fn(update, context, product_id))
    elif CB_PREFIX_CART_DEL in data:
        return cast(int, await internal_cart_remove_fn(update, context, product_id))

    return cast(int, await show_cart_edit_mode_fn(update, context))


async def internal_cart_remove(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    product_id: int,
    show_cart_edit_mode_fn: Any,
    cart_view_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return cart_view_state
    if query.data is None:
        return cart_view_state
    if query.message is None:
        return cart_view_state
    if update.effective_user is None:
        return cart_view_state
    if update.effective_chat is None:
        return cart_view_state
    user_id = update.effective_user.id
    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))

    cart = await cart_service.get_cart(user_id)
    old_qty = cart.get(str(product_id), {}).get('quantity', 1)

    user_data = context.user_data
    if user_data is not None:
        user_data[f'undo_qty_{product_id}'] = old_qty

    await cart_service.remove_item(user_id, product_id)

    await show_cart_edit_mode_fn(update, context, deleted_id=product_id)

    msg_id: Any = None
    if user_data is not None:
        msg_id = user_data.get('last_global_menu_id')

    if msg_id and context.job_queue is not None:
        job_name = f"undo_cart_{user_id}"
        for j in context.job_queue.get_jobs_by_name(job_name):
            j.schedule_removal()

        context.job_queue.run_repeating(
            cart_countdown_job,
            interval=1,
            first=1,
            data={'chat_id': user_id, 'message_id': msg_id, 'user_id': user_id, 'product_id': product_id, 'seconds': 5},
            name=job_name,
        )
    await query.answer("Удалено")
    return cart_view_state


async def cart_countdown_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    d: dict[str, Any] = cast(dict[str, Any], job.data)
    d['seconds'] -= 1

    if d['seconds'] <= 0:
        job.schedule_removal()

    app = context.application
    cart_service: CartService = cast(CartService, app.bot_data.get('cart_service'))
    product_service: ProductService = cast(ProductService, app.bot_data.get('product_service'))
    try:
        cart = await cart_service.get_cart(d['user_id'])
        products_list = await product_service.get_available_products(light_mode=True)
        products: dict[str, Any] = {str(p.id): p for p in products_list}

        reply_markup = get_cart_edit_keyboard(
            cart,
            products,
            deleted_id=d['product_id'] if d['seconds'] > 0 else None,
            timer=d['seconds'],
        )

        await app.bot.edit_message_reply_markup(
            chat_id=d['chat_id'],
            message_id=d['message_id'],
            reply_markup=reply_markup,
        )
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        if "Message is not modified" not in str(e):
            job.schedule_removal()


async def handle_cart_undo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_cart_edit_mode_fn: Any,
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    if query.data is None:
        return ConversationHandler.END
    if query.message is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    if update.effective_chat is None:
        return ConversationHandler.END
    user_id = update.effective_user.id

    product_id = int(query.data.replace(CB_CART_UNDO_RM, ""))

    job_name = f"undo_cart_{user_id}"
    if context.job_queue is not None:
        for j in context.job_queue.get_jobs_by_name(job_name):
            j.schedule_removal()

    user_data = context.user_data
    if user_data is not None:
        qty = user_data.pop(f'undo_qty_{product_id}', 1)
    else:
        qty = 1

    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))
    await cart_service.update_item(user_id, product_id, qty)

    await query.answer(f"Возвращено: {qty} шт.")
    return cast(int, await show_cart_edit_mode_fn(update, context))


async def clear_cart_undo_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    d: dict[str, Any] = cast(dict[str, Any], job.data)
    try:
        logger.info(f"[CART] Undo timeout for user {d['user_id']}")
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_cart.py] TelegramError: {e}")


async def handle_cart_interaction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_cart_fn: Any,
    cart_view_state: int,
    delivery_method_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return cart_view_state
    if query.data is None:
        return cart_view_state
    if query.message is None:
        return cart_view_state
    if update.effective_user is None:
        return cart_view_state
    if update.effective_chat is None:
        return cart_view_state
    user_id = update.effective_user.id
    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))
    s_service: SettingsService = cast(SettingsService, context.bot_data.get('settings_service'))

    if query.data == CB_CLEAR_CART:
        await cart_service.clear_cart(user_id)
        await query.answer("Корзина очищена")
        return cast(int, await show_cart_fn(update, context))

    elif query.data == CB_CHECKOUT:
        status, message = await cart_service.validate_cart(user_id)

        if status == CartValidationResult.CLEARED_OLD:
            await query.answer("Корзина устарела и была очищена.", show_alert=True)
            assert message is not None
            await query.edit_message_text(message)
            return ConversationHandler.END

        if status == CartValidationResult.ITEM_UNAVAILABLE:
            await query.answer("В корзине есть недоступные товары!", show_alert=True)
            return cast(int, await show_cart_fn(update, context))

        cart = await cart_service.get_cart(user_id)
        if not cart:
            await query.answer("Корзина пуста!", show_alert=True)
            return cart_view_state

        courier_enabled = await s_service.get_setting('courier_enabled', 'false') == 'true'

        await query.answer()
        await query.edit_message_text(
            "🚚 <b>Выберите способ доставки:</b>",
            reply_markup=get_delivery_method_keyboard(courier_enabled),
            parse_mode=ParseMode.HTML,
        )
        if context.user_data is not None:
            context.user_data['last_global_menu_id'] = query.message.message_id
        return delivery_method_state

    return cart_view_state


async def show_cart_quantity_grid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    answer_bad_callback_fn: Any,
    cart_view_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return cart_view_state
    if query.data is None:
        return cart_view_state
    if query.message is None:
        return cart_view_state
    if update.effective_user is None:
        return cart_view_state
    if update.effective_chat is None:
        return cart_view_state

    await query.answer()

    try:
        product_id = int(query.data.replace(CB_PREFIX_CART_QTY_GRID, ""))
    except (ValueError, TypeError):
        await answer_bad_callback_fn(query, query.data, "invalid cart quantity grid payload")
        return cart_view_state

    reply_markup = get_cart_quantity_grid_keyboard(product_id)

    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_cart.py] TelegramError: {e}")
    return cart_view_state


async def handle_cart_preset_qty(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    answer_bad_callback_fn: Any,
    show_cart_edit_mode_fn: Any,
    cart_view_state: int,
) -> int:
    query = update.callback_query
    if query is None:
        return cart_view_state
    if query.data is None:
        return cart_view_state
    if query.message is None:
        return cart_view_state
    if update.effective_user is None:
        return cart_view_state
    if update.effective_chat is None:
        return cart_view_state
    user_id = update.effective_user.id

    data = query.data.replace(CB_PREFIX_CART_SET_QTY, "")
    try:
        product_id, value = map(int, data.split('_'))
    except (ValueError, TypeError):
        await answer_bad_callback_fn(query, query.data, "invalid cart preset payload")
        return cart_view_state

    cart_service: CartService = cast(CartService, context.bot_data.get('cart_service'))
    await cart_service.update_item(user_id, product_id, value)

    await query.answer(f"Обновлено: {value} шт. 🛒")
    return cast(int, await show_cart_edit_mode_fn(update, context))
