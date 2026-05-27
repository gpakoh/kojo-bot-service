# Tg_bot/handlers/order_product_view.py
import logging
from typing import Any, Optional, cast

import telegram
from telegram import InputMediaPhoto, Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from tg_bot.bot_services.cart_service import CartService
from tg_bot.bot_services.product_service import ProductService
from tg_bot.bot_services.product_sync_service import KOJO_ROOT
from tg_bot.bot_services.user_service import UserService
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import (
    CB_GALLERY_ADD,
    CB_GALLERY_NEXT,
    CB_GALLERY_PREV,
    CB_PREFIX_IMG_GRID,
    CB_PREFIX_PROD_IMG,
    CB_PREFIX_QTY_GRID,
    CB_PREFIX_SELECT_PRODUCT,
    CB_PREFIX_SET_QTY,
    CB_PRODUCT_CLEAR,
    get_gallery_keyboard,
    get_image_grid_keyboard,
    get_product_view_keyboard,
    get_quantity_grid_keyboard,
)
from utils.image_cache import get_media_payload, update_cache_from_message
from utils.ui_formatters import format_product_card_html

logger = logging.getLogger(__name__)


def truncate_caption(text: str, limit: int = 1010) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False

    truncated = text[:limit]
    last_paragraph = truncated.rfind('\n\n')

    if last_paragraph > 200:
        return text[:last_paragraph] + "\n\n...", True

    last_space = truncated.rfind(' ')
    return text[:last_space] + "...", True


def resolve_product_params(query: Any, product_id: Any, category: Any) -> Any:
    if product_id is not None:
        return product_id, category

    if not query or not query.data:
        raise ValueError("Callback data is missing")

    data: str = query.data
    if data.startswith(CB_PREFIX_SELECT_PRODUCT):
        parts = data.replace(CB_PREFIX_SELECT_PRODUCT, '').split('_')
    elif data.startswith((CB_PREFIX_QTY_GRID, CB_PREFIX_SET_QTY)):
        prefix = CB_PREFIX_QTY_GRID if data.startswith(CB_PREFIX_QTY_GRID) else CB_PREFIX_SET_QTY
        parts = data.replace(prefix, '').split('_')
    else:
        parts = data.split('_')
        if len(parts) < 2:
            raise ValueError(f"Malformed callback data: {data}")
        return int(parts[-2]), parts[-1]

    if len(parts) < 2:
        raise ValueError(f"Malformed callback data: {data}")
    return int(parts[0]), parts[1]


async def answer_bad_callback(query: Any, raw_data: str, reason: str) -> None:
    logger.warning(f"Bad callback payload '{raw_data}': {reason}")
    try:
        await query.answer("Кнопка устарела. Откройте карточку заново.", show_alert=True)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")


def get_image_context(context: Any, query: Any, product: Any, product_id: int) -> Any:
    user_data: dict[str, Any] = context.user_data or {}
    last_viewed_id = user_data.get('viewed_product_id')

    if last_viewed_id != product_id or not query.data.startswith(CB_PREFIX_PROD_IMG):
        img_index = 0
    else:
        img_index = user_data.get('prod_img_index', 0)

    if not product.images or img_index >= len(product.images):
        img_index = 0

    context.user_data['prod_img_index'] = img_index
    context.user_data['viewed_product_id'] = product_id
    photo_path = (KOJO_ROOT / product.images[img_index]) if product.images else None

    return img_index, photo_path


def build_product_caption(product: Any, show_details: bool) -> Any:
    full_formatted_text = format_product_card_html(product)

    if not show_details:
        parts = full_formatted_text.split('\n\n')
        summary_text = "\n\n".join(parts[:2])
        if product.variants:
            summary_text += f"\n\n💰 Цена: <b>{product.variants[0].price}₽</b>"
        return summary_text, False

    return truncate_caption(full_formatted_text)


async def get_product_for_view(product_id: int, context: ContextTypes.DEFAULT_TYPE) -> Any:
    user_data: dict[str, Any] = context.user_data or {}
    cached_dict = user_data.get('products', {})
    if product_id in cached_dict:
        return cached_dict[product_id]

    product_service: ProductService = context.bot_data['product_service']
    product = await product_service.get_product_by_id(product_id)

    if product:
        cached_dict[product_id] = product
        ud = cast(dict[str, Any], context.user_data)
        ud['products'] = cached_dict

    return product


async def render_product_ui(update: Update, context: ContextTypes.DEFAULT_TYPE, product: Any, category: str, show_details: bool) -> None:
    if update.effective_user is None:
        return
    if update.effective_chat is None:
        return
    user_id = update.effective_user.id
    query = update.callback_query
    user_data: dict[str, Any] = context.user_data or {}
    user_service: UserService = context.bot_data['user_service']
    is_guest = user_data.get('is_guest', False)

    img_index, photo_path = get_image_context(context, query, product, product.id)
    display_text, has_overflow = build_product_caption(product, show_details)

    ud = cast(dict[str, Any], context.user_data)
    cart = await context.bot_data['cart_service'].get_cart(user_id)
    is_fav = await context.bot_data['favorite_service'].is_favorite(user_id, product.id)
    qty = user_data.get('viewed_product_quantity', 1)
    if category == 'cartedit':
        qty = cart.get(str(product.id), {}).get('quantity', 1)

    reply_markup = get_product_view_keyboard(
        product.id,
        category,
        qty,
        cart,
        details_shown=show_details,
        is_staff=user_data.get('is_staff_order', False),
        is_favorite=is_fav,
        has_overflow=has_overflow,
        img_index=img_index,
        img_total=len(product.images),
        is_guest=is_guest,
    )

    try:
        if photo_path and photo_path.exists():
            media_payload, file_to_close = get_media_payload(photo_path, context.bot_data)
            try:
                if query and query.message and query.message.photo:
                    msg = await query.edit_message_media(
                        media=InputMediaPhoto(media=media_payload, caption=display_text, parse_mode=ParseMode.HTML),
                        reply_markup=reply_markup,
                        read_timeout=40,
                        write_timeout=40,
                        connect_timeout=40,
                    )
                    if file_to_close and isinstance(msg, Message):
                        update_cache_from_message(context.bot_data, photo_path, msg)
                else:
                    msg = await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=media_payload,
                        caption=display_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML',
                        read_timeout=40,
                        write_timeout=40,
                        connect_timeout=40,
                    )
                    if file_to_close:
                        update_cache_from_message(context.bot_data, photo_path, msg)

                    new_id = msg.message_id
                    ud['last_global_menu_id'] = new_id
                    await user_service.save_registration_message_id(user_id, new_id)

                    if query and query.message:
                        try:
                            await query.message.delete()
                        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                            logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")
                    await cleanup_previous_menu(context, user_id, exclude_id=new_id)
            finally:
                if file_to_close:
                    file_to_close.close()
        else:
            if query and query.message and query.message.photo:
                msg = await context.bot.send_message(
                    chat_id=user_id, text=display_text, reply_markup=reply_markup, parse_mode='HTML'
                )
                new_id = msg.message_id

                ud['last_global_menu_id'] = new_id
                await user_service.save_registration_message_id(user_id, new_id)

                try:
                    await query.message.delete()
                except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")
                await cleanup_previous_menu(context, user_id, exclude_id=new_id)
            else:
                if query:
                    await query.edit_message_text(text=display_text, reply_markup=reply_markup, parse_mode='HTML')
                else:
                    msg = await context.bot.send_message(
                        user_id, text=display_text, reply_markup=reply_markup, parse_mode='HTML'
                    )
                    ud['last_global_menu_id'] = msg.message_id
                    await user_service.save_registration_message_id(user_id, msg.message_id)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Render Error for product {product.id}: {e}")


async def get_gallery_state(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Any:
    user_data: dict[str, Any] = context.user_data or {}
    product_ids = user_data.get('gallery_product_ids', [])
    if not product_ids:
        return None

    index = user_data.get('gallery_index', 0)
    index = max(0, min(index, len(product_ids) - 1))
    ud = cast(dict[str, Any], context.user_data)
    ud['gallery_index'] = index

    product_id = product_ids[index]
    product = await get_product_for_view(product_id, context)
    if not product:
        return None

    cart = await context.bot_data['cart_service'].get_cart(user_id)
    is_fav = await context.bot_data['favorite_service'].is_favorite(user_id, product.id)
    quantity = user_data.get('viewed_product_quantity', 1)
    category = user_data.get('current_category', 'all')

    logger.debug("Gallery State: Product=%s, Index=%s/%s, Qty=%s", product.id, index, len(product_ids), quantity)

    return {
        "product": product,
        "index": index,
        "total": len(product_ids),
        "cart": cart,
        "is_fav": is_fav,
        "quantity": quantity,
        "category": category,
    }


async def render_gallery_media(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict[str, Any]) -> None:
    if update.effective_user is None:
        return
    if update.effective_chat is None:
        return
    query = update.callback_query
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']
    product = state['product']

    price_str = f"{product.variants[0].price}₽" if product.variants else "---"
    text = f"<b>{product.name}</b>\n💰 Цена: <b>{price_str}</b>\n\n{product.short_description or ''}"
    reply_markup = get_gallery_keyboard(
        product.id,
        state['index'],
        state['total'],
        state['cart'],
        state['category'],
        is_favorite=state['is_fav'],
        quantity=state['quantity'],
    )

    photo_path = (KOJO_ROOT / product.images[0]) if product.images else None
    ud = cast(dict[str, Any], context.user_data)

    if photo_path and photo_path.exists():
        media_payload, file_to_close = get_media_payload(photo_path, context.bot_data)
        try:
            if query and query.message and query.message.photo:
                msg = await query.edit_message_media(
                    media=InputMediaPhoto(media=media_payload, caption=text, parse_mode=ParseMode.HTML),
                    reply_markup=reply_markup,
                    read_timeout=40,
                    write_timeout=40,
                    connect_timeout=40,
                )
                if file_to_close and isinstance(msg, Message):
                    update_cache_from_message(context.bot_data, photo_path, msg)
            else:
                msg = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=media_payload,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    read_timeout=40,
                    write_timeout=40,
                    connect_timeout=40,
                )
                if file_to_close:
                    update_cache_from_message(context.bot_data, photo_path, msg)

                new_id = msg.message_id
                ud['last_global_menu_id'] = new_id
                await user_service.save_registration_message_id(user_id, new_id)
                if query and query.message:
                    try:
                        await query.message.delete()
                    except (ValueError, KeyError, telegram.error.TelegramError) as e:
                        logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")
                await cleanup_previous_menu(context, user_id, exclude_id=new_id)
        finally:
            if file_to_close:
                file_to_close.close()
    else:
        if query and query.message and query.message.photo:
            msg = await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
            new_id = msg.message_id

            ud['last_global_menu_id'] = new_id
            await user_service.save_registration_message_id(user_id, new_id)

            try:
                await query.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")
            await cleanup_previous_menu(context, user_id, exclude_id=new_id)
        elif query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def show_gallery_view(update: Update, context: ContextTypes.DEFAULT_TYPE, show_product_list_fn: Any, showing_products_state: int) -> int:
    if update.effective_user is None:
        return showing_products_state
    user_id = update.effective_user.id
    state = await get_gallery_state(context, user_id)
    if not state:
        return cast(int, await show_product_list_fn(update, context))

    await render_gallery_media(update, context, state)
    return showing_products_state


async def handle_gallery_nav(update: Update, context: ContextTypes.DEFAULT_TYPE, show_gallery_view_fn: Any) -> int:
    if update.effective_user is None:
        return 0
    query = update.callback_query
    if query is None or query.data is None:
        return 0
    action: str = query.data
    user_data: dict[str, Any] = context.user_data or {}
    ud = cast(dict[str, Any], context.user_data)
    total = len(user_data.get('gallery_product_ids', []))

    if action == CB_GALLERY_NEXT:
        ud['gallery_index'] = (user_data.get('gallery_index', 0) + 1) % total
    elif action == CB_GALLERY_PREV:
        ud['gallery_index'] = (user_data.get('gallery_index', 0) - 1) % total
    elif action.startswith(CB_GALLERY_ADD):
        product_id = int(action.replace(f"{CB_GALLERY_ADD}_", ""))
        cart_service: CartService = context.bot_data['cart_service']
        current_cart = await cart_service.get_cart(update.effective_user.id)
        current_qty = current_cart.get(str(product_id), {}).get('quantity', 0)
        await cart_service.update_item(update.effective_user.id, product_id, current_qty + 1)
        await query.answer("Добавлено в корзину! 🛒")

    return cast(int, await show_gallery_view_fn(update, context))


async def open_gallery_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, show_product_list_fn: Any) -> int:
    query = update.callback_query
    if query is None:
        return 0
    await query.answer()
    ud = cast(dict[str, Any], context.user_data)
    ud['gallery_selecting'] = True
    return cast(int, await show_product_list_fn(update, context))


async def handle_gallery_selection(update: Any, context: Any, product_id: int, show_gallery_view_fn: Any) -> Any:
    gallery_ids = context.user_data.get('gallery_product_ids', [])
    try:
        context.user_data['gallery_index'] = gallery_ids.index(product_id)
    except ValueError:
        context.user_data['gallery_index'] = 0
    context.user_data['gallery_selecting'] = False
    return await show_gallery_view_fn(update, context)


async def show_product_view(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_product_list_fn: Any,
    handle_gallery_selection_fn: Any,
    showing_products_state: int,
    viewing_product_state: int,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
    force_details: Optional[bool] = None,
) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")

    try:
        resolved = resolve_product_params(query, product_id, category)
        product_id = cast(int, resolved[0])
        category = cast(str, resolved[1])
    except (ValueError, KeyError, telegram.error.TelegramError):
        return showing_products_state

    user_data: dict[str, Any] = context.user_data or {}
    if user_data.get('gallery_selecting', False):
        return cast(int, await handle_gallery_selection_fn(update, context, product_id))

    product = await get_product_for_view(product_id, context)
    if not product:
        logger.warning(f"Product {product_id} not found, returning to list")
        return cast(int, await show_product_list_fn(update, context))

    show_details = force_details if force_details is not None else (bool(query and query.data and "_details" in query.data))
    await render_product_ui(update, context, product, category, show_details)
    return viewing_product_state


async def handle_product_image_nav(update: Update, context: ContextTypes.DEFAULT_TYPE, viewing_product_state: int) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return viewing_product_state
    await query.answer()

    data: str = query.data.replace(CB_PREFIX_PROD_IMG, "")
    try:
        product_id, new_index = map(int, data.split('_'))
    except (ValueError, TypeError):
        await answer_bad_callback(query, query.data, "invalid product image payload")
        return viewing_product_state

    ud = cast(dict[str, Any], context.user_data)
    ud['prod_img_index'] = new_index
    product = await get_product_for_view(product_id, context)
    if not product:
        await answer_bad_callback(query, query.data, "product not found")
        return viewing_product_state

    user_data: dict[str, Any] = context.user_data or {}
    category = user_data.get('current_category', 'all')
    keyboard_rows = query.message.reply_markup.inline_keyboard if query.message and query.message.reply_markup else []
    details_shown = any("Скрыть детали" in str(btn.text) for row in keyboard_rows for btn in row)

    await render_product_ui(update, context, product, category, details_shown)
    return viewing_product_state


async def show_product_image_grid(update: Update, context: ContextTypes.DEFAULT_TYPE, viewing_product_state: int) -> int:
    if update.effective_user is None:
        return viewing_product_state
    query = update.callback_query
    if query is None or query.data is None:
        return viewing_product_state
    await query.answer()

    data: str = query.data.replace(CB_PREFIX_IMG_GRID, "")
    parts = data.split('_', 1)
    if len(parts) != 2:
        await answer_bad_callback(query, query.data, "invalid image grid payload format")
        return viewing_product_state

    try:
        product_id = int(parts[0])
    except (ValueError, TypeError):
        await answer_bad_callback(query, query.data, "invalid product id in image grid payload")
        return viewing_product_state

    category = parts[1]
    product_service: ProductService = context.bot_data['product_service']
    product = await product_service.get_product_by_id(product_id)

    if not product or not product.images:
        await answer_bad_callback(query, query.data, "product missing or has no images")
        return viewing_product_state

    reply_markup = get_image_grid_keyboard(product_id, len(product.images), category)
    logger.info(f"[ORDER] User {update.effective_user.id} opened image grid for product {product_id}")

    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error showing image grid: {e}")
    return viewing_product_state


async def show_product_quantity_grid(update: Update, context: ContextTypes.DEFAULT_TYPE, viewing_product_state: int) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return viewing_product_state
    await query.answer()

    data: str = query.data.replace(CB_PREFIX_QTY_GRID, "")
    try:
        product_id_raw, category = data.split('_', 1)
        product_id = int(product_id_raw)
    except (ValueError, TypeError):
        await answer_bad_callback(query, query.data, "invalid quantity grid payload")
        return viewing_product_state

    reply_markup = get_quantity_grid_keyboard(product_id, category)
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.warning(f"[databases/kojo/tg_bot/handlers/order_product_view.py] TelegramError: {e}")
    return viewing_product_state


async def handle_set_quantity_preset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_product_view_fn: Any,
    viewing_product_state: int,
) -> int:
    if update.effective_user is None:
        return viewing_product_state
    query = update.callback_query
    if query is None or query.data is None:
        return viewing_product_state
    data: str = query.data.replace(CB_PREFIX_SET_QTY, "")
    parts = data.split('_')
    if len(parts) < 3:
        await answer_bad_callback(query, query.data, "invalid qty preset payload format")
        return viewing_product_state

    try:
        product_id, category, value = int(parts[0]), parts[1], int(parts[2])
    except (ValueError, TypeError):
        await answer_bad_callback(query, query.data, "invalid qty preset payload values")
        return viewing_product_state

    ud = cast(dict[str, Any], context.user_data)
    ud['viewed_product_quantity'] = value
    if category == 'cartedit':
        await context.bot_data['cart_service'].update_item(update.effective_user.id, product_id, value)

    await query.answer(f"Выбрано: {value} шт.")
    return cast(int, await show_product_view_fn(update, context, product_id=product_id, category=category))


async def handle_clear_product_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_product_view_fn: Any,
    internal_cart_remove_fn: Any,
    viewing_product_state: int,
) -> int:
    if update.effective_user is None:
        return viewing_product_state
    query = update.callback_query
    if query is None or query.data is None:
        return viewing_product_state
    data: str = query.data.replace(CB_PRODUCT_CLEAR, "")
    parts = data.split('_')
    if len(parts) < 2:
        await answer_bad_callback(query, query.data, "invalid clear payload format")
        return viewing_product_state

    try:
        product_id, category = int(parts[0]), parts[1]
    except (ValueError, TypeError):
        await answer_bad_callback(query, query.data, "invalid clear payload values")
        return viewing_product_state

    user_id = update.effective_user.id
    if category == 'cartedit':
        return cast(int, await internal_cart_remove_fn(update, context, product_id))

    await context.bot_data['cart_service'].remove_item(user_id, product_id)
    ud = cast(dict[str, Any], context.user_data)
    ud['viewed_product_quantity'] = 1

    await query.answer("Товар удален из корзины 🗑")
    return cast(int, await show_product_view_fn(update, context, product_id=product_id, category=category))
