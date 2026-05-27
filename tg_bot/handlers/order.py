# Tg_bot/handlers/order.py
import logging
import re
from typing import TYPE_CHECKING, Any, Optional

import telegram
from telegram import (
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

import tg_bot.handlers.order_brew as order_brew
import tg_bot.handlers.order_cart as order_cart
import tg_bot.handlers.order_delivery_checkout as order_delivery_checkout
import tg_bot.handlers.order_gift as order_gift
import tg_bot.handlers.order_product_view as order_product_view
import tg_bot.handlers.order_search_sort as order_search_sort
import tg_bot.handlers.order_ui_helpers as order_ui_helpers
from tg_bot.bot_services.cart_service import CartService
from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.product_service import ProductService
from tg_bot.callback_validator import validate_callback
from tg_bot.decorators import auth_guard
from tg_bot.handlers.common import cleanup_previous_menu

# Import Handlers From Favorites (needed At Runtime For Callbackqueryhandler)
from tg_bot.handlers.favorites import (
    STATE_HOME,
    delete_recipe_action,
    handle_fav_cart_change,
    handle_fav_cart_clear,
    handle_fav_preset_qty,
    remove_favorite_item,
    show_fav_quantity_grid,
    show_favorite_products,
    show_favorites_menu,
    show_saved_recipe_details,
    show_saved_recipes_list,
    toggle_favorite_in_card,
    toggle_notification,
    undo_remove_favorite,
)
from tg_bot.keyboards import (
    CB_ADD_TO_CART,
    CB_AI_GIFT_HELP,
    CB_AI_GIFT_RETRY,
    CB_BACK_TO_CART_SUMMARY,
    CB_BACK_TO_CATEGORIES,
    CB_BACK_TO_PRODUCT_LIST,
    CB_BREW_GUIDE,
    CB_BREW_METHOD_SELECT,
    CB_CART_UNDO_RM,
    CB_CHECKOUT,
    CB_CLEAR_CART,
    CB_CLOSE_GENERIC,
    CB_DELIVERY_BACK,
    CB_DELIVERY_COURIER_CITY,
    CB_DELIVERY_TYPE_COURIER,
    CB_DELIVERY_TYPE_PICKUP,
    CB_DELIVERY_TYPE_SELF,
    CB_DELIVERY_TYPE_YANDEX,
    CB_EDIT_CART,
    CB_FAV_ADD_CART,
    CB_FAV_CART_CLEAR,
    CB_FAV_DEC_CART,
    CB_FAV_INC_CART,
    CB_FAV_PRODUCTS_LIST,
    CB_FAV_RECIPES_LIST,
    CB_FAV_UNDO_RM,
    CB_FAVORITES_MENU,
    CB_GALLERY_ADD,
    CB_GALLERY_NEXT,
    CB_GALLERY_OPEN_LIST,
    CB_GALLERY_PREV,
    CB_GIFT_AS_PRESENT,
    CB_GIFT_BACK,
    CB_GIFT_FOR_ME,
    CB_GIFT_SKIP,
    CB_GO_TO_MAIN_MENU,
    CB_OPEN_SORT_MENU,
    CB_ORDER_RESTORE,
    CB_PICKUP_POINT_SEL,
    CB_PREFIX_AI_GIFT_SELECT,
    CB_PREFIX_CART_DEC,
    CB_PREFIX_CART_DEL,
    CB_PREFIX_CART_INC,
    CB_PREFIX_CART_QTY_GRID,
    CB_PREFIX_CART_SET_QTY,
    CB_PREFIX_CATEGORY_LIST,
    CB_PREFIX_CHANGE_QUANTITY,
    CB_PREFIX_FAV_QTY_GRID,
    CB_PREFIX_FAV_SET_QTY,
    CB_PREFIX_IMG_GRID,
    CB_PREFIX_NOTIFY_FAV,
    CB_PREFIX_PROD_IMG,
    CB_PREFIX_QTY_GRID,
    CB_PREFIX_RM_FAV,
    CB_PREFIX_SELECT_CATEGORY,
    CB_PREFIX_SELECT_PRODUCT,
    CB_PREFIX_SET_QTY,
    CB_PREFIX_SET_SORT,
    CB_PREFIX_TOGGLE_FAV,
    CB_PRODUCT_CLEAR,
    CB_READ_FULL_DESC,
    CB_RECIPE_DELETE,
    CB_RECIPE_SAVE,
    CB_RECIPE_VIEW_SAVED,
    CB_REPEAT_ORDER,
    CB_SAVE_DELIVERY_ADDRESS,
    CB_SEARCH_PRODUCTS,
    CB_SEARCH_SEMANTIC,
    CB_SHOW_ALL_PRODUCTS,
    CB_STAFF_PANEL,
    CB_TOGGLE_VIEW,
    CB_USE_DEFAULT_ADDRESS,
    CB_USER_SHOW_MAIN_MENU,
    CB_USER_START_ORDERING,
    CB_VIEW_CART,
    get_category_keyboard,
    get_icon,
    get_product_list_keyboard,
)
from tg_bot.models import OrderStatus, Product

if TYPE_CHECKING:
    # Type Checking Only Imports (if Any Remain)
    pass

logger = logging.getLogger(__name__)

# Состояния conversationhandler
SHOWING_CATEGORIES, SHOWING_PRODUCTS, VIEWING_PRODUCT, CART_VIEW, \
DELIVERY_METHOD, DELIVERY_WEBAPP, ASKING_GIFT, AWAITING_GIFT_COMMENT, ORDER_CREATED, AWAITING_SEARCH = range(10)
# Внутренние колбеки для новых кнопок действий с заказом
CB_ORDER_ACTION_CANCEL = "ord_act_cancel"
CB_ORDER_ACTION_CHANGE_DELIVERY = "ord_act_change_dlv"
AWAITING_GIFT_AI_DATA = 10 # Новое состояние для сбора пожеланий по открытке через AI

# Вспомогательные функции
def _extract_sca_score(description: str) -> float:
    if not description:
        return 0.0
    match = re.search(r"(?i)sca.*?(\d+(?:\.\d+)?)", description)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0

def get_cart_text_and_total(cart: dict[str, Any], products: dict[str, Any]) -> tuple[str, float]:
    return order_cart.get_cart_text_and_total(cart, products)


async def _get_and_cache_all_products(context: ContextTypes.DEFAULT_TYPE) -> Any:
    user_data: dict[str, Any] = context.user_data or {}
    if 'products' not in user_data:
        product_service: ProductService = context.bot_data['product_service']
        all_products = await product_service.get_available_products()
        user_data['products'] = {p.id: p for p in all_products}
    return user_data['products']


async def send_order_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup: Any) -> Any:
    """
    Универсальная отправка меню с защитой от баннера iOS.
    Сначала отправляет новое, затем удаляет старое.
    """
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    user_service = context.bot_data['user_service']
    query = update.callback_query
    user_data: dict[str, Any] = context.user_data or {}

    try:
        if query and query.message:
            # Проверяем наличие медиа (визитка может быть видео или фото)
            has_media = bool(query.message.photo or query.message.video or query.message.animation)

            if has_media:
                # [правило ios] 1. сначала отправляем новое текстовое сообщение
                msg = await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )

                # 2. сразу фиксируем новый id как главный якорь
                user_data['last_global_menu_id'] = msg.message_id
                await user_service.save_registration_message_id(user_id, msg.message_id)

                # 3. и только теперь удаляем старое медиа-сообщение
                try:
                    await query.message.delete()
                except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.debug(f"Could not delete old media message: {e}")
            else:
                # Если это был текст — редактируем плавно в том же окне
                await query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
                user_data['last_global_menu_id'] = query.message.message_id
        else:
            # Вызов через текст (поиск) или команды
            if update.effective_chat is None:
                return
            chat_id = update.effective_chat.id

            # [правило ios] 1. сначала шлем новое сообщение
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            new_id = msg.message_id

            # 2. чистим ввод пользователя, если он еще есть
            if update.message:
                try:
                    await update.message.delete()
                except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/handlers/order.py] TelegramError: {e}")

            # [правило ios] 3. теперь удаляем старые якоря
            await cleanup_previous_menu(context, chat_id, exclude_id=new_id)

            # 4. обновляем бд
            user_data['last_global_menu_id'] = new_id
            await user_service.save_registration_message_id(user_id, new_id)

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        if 'Message is not modified' not in str(e):
            logger.error(f"send_order_menu_message error: {e}", exc_info=True)
            # Фолбек: при любой ошибке шлем новое сообщение, чтобы не бросать пользователя
            try:
                sent_msg = await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode='HTML')
                await user_service.save_registration_message_id(user_id, sent_msg.message_id)
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/handlers/order.py] TelegramError: {e}")

    logger.info(f"UI Menu updated for {user_id}. Order: New-Send then Delete-Old.")


async def _calculate_order_totals(user_id: int, delivery_price: float, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_delivery_checkout.calculate_order_totals(
        user_id,
        delivery_price,
        context,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
    )


async def _persist_order(
    user_id: int,
    cart: dict[str, Any],
    totals: tuple[Any, ...],
    delivery_data: tuple[Any, ...],
    context: ContextTypes.DEFAULT_TYPE,
    is_gift: bool = False,
    gift_comment: Optional[str] = None
) -> Any:
    return await order_delivery_checkout.persist_order(
        user_id=user_id,
        cart=cart,
        totals=totals,
        delivery_data=delivery_data,
        context=context,
        is_gift=is_gift,
        gift_comment=gift_comment,
    )


# Tg_bot/handlers/order.py

async def _send_order_success_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: Any,
    msg_prefix: str,
    totals: tuple[Any, ...],
    delivery_address: str,
    payment_url: str
) -> Any:
    return await order_delivery_checkout.send_order_success_message(
        update=update,
        context=context,
        order=order,
        msg_prefix=msg_prefix,
        totals=totals,
        delivery_address=delivery_address,
        payment_url=payment_url,
        save_delivery_address_callback=CB_SAVE_DELIVERY_ADDRESS,
        order_action_cancel_callback=CB_ORDER_ACTION_CANCEL,
        order_action_change_delivery_callback=CB_ORDER_ACTION_CHANGE_DELIVERY,
        go_to_main_menu_callback=CB_GO_TO_MAIN_MENU,
    )


async def _finalize_order_and_pay(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  delivery_type: str, delivery_price: float, delivery_address: str,
                                  delivery_point_id: Optional[str] = None, delivery_info: Optional[dict[str, Any]] = None,
                                  is_gift: bool = False,
                                  gift_comment: Optional[str] = None) -> int:
    return await order_delivery_checkout.finalize_order_and_pay(
        update=update,
        context=context,
        delivery_type=delivery_type,
        delivery_price=delivery_price,
        delivery_address=delivery_address,
        delivery_point_id=delivery_point_id,
        delivery_info=delivery_info,
        is_gift=is_gift,
        gift_comment=gift_comment,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
        send_order_success_message_fn=_send_order_success_message,
        order_created_state=ORDER_CREATED,
    )


async def handle_order_created_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_order_created_actions(
        update=update,
        context=context,
        order_action_cancel_callback=CB_ORDER_ACTION_CANCEL,
        order_action_change_delivery_callback=CB_ORDER_ACTION_CHANGE_DELIVERY,
        order_restore_prefix=CB_ORDER_RESTORE,
        user_show_main_menu_callback=CB_USER_SHOW_MAIN_MENU,
        order_created_state=ORDER_CREATED,
        delivery_method_state=DELIVERY_METHOD,
    )


# Обычные хендлеры
@auth_guard()
async def start_user_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в каталог. Чистим команду /menu."""
    if update.effective_user is None:
        return SHOWING_CATEGORIES
    # [критично] удаляем /menu
    if update.message:
        try:
            await update.message.delete()
            logger.debug("Order: Incoming Command Deleted.")
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/order.py] TelegramError: {e}")

    user_data: dict[str, Any] = context.user_data or {}
    user_data['is_staff_order'] = False
    return await show_categories(update, context)

@auth_guard(staff_only=True)
async def start_staff_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None:
        return SHOWING_CATEGORIES
    user_data: dict[str, Any] = context.user_data or {}
    user_data['is_staff_order'] = True
    return await show_categories(update, context)

@auth_guard()
async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None:
        return SHOWING_CATEGORIES
    user_id = update.effective_user.id
    query = update.callback_query
    user_data: dict[str, Any] = context.user_data or {}

    if query:
        await query.answer()

    # Получаем состояние гостя
    is_guest = user_data.get('is_guest', False)

    product_service: ProductService = context.bot_data['product_service']
    cart_service: CartService = context.bot_data['cart_service']

    category_tree = await product_service.get_category_tree()
    await _get_and_cache_all_products(context)
    cart = await cart_service.get_cart(user_id)

    target_category = None
    if query and query.data and query.data.startswith(CB_PREFIX_SELECT_CATEGORY):
        target_category = query.data.replace(CB_PREFIX_SELECT_CATEGORY, '')
    elif query and query.data and query.data == CB_BACK_TO_CATEGORIES:
        last_cat = user_data.get('current_category')
        if last_cat:
            for root, children in category_tree.items():
                if last_cat in children:
                    target_category = root
                    break
                if last_cat == root and children:
                    target_category = None
                    break

    categories_to_show: list[str] = []
    text = ""
    is_root_view = True

    if not target_category:
        categories_to_show = sorted(list(category_tree.keys()))
        text = "Выберите категорию:"
        is_root_view = True
        user_data.pop('current_category', None)
    elif target_category in category_tree:
        subcategories = category_tree[target_category]
        if subcategories:
            if len(subcategories) == 1:
                user_data['current_category'] = subcategories[0]
                return await show_product_list(update, context)
            user_data['current_category'] = target_category
            categories_to_show = subcategories
            text = f"{get_icon(target_category)}Категория {target_category}:"
            is_root_view = False
        else:
            user_data['current_category'] = target_category
            return await show_product_list(update, context)
    else:
        user_data['current_category'] = target_category
        return await show_product_list(update, context)

    fav_service = context.bot_data.get('favorite_service')
    has_favs = False
    if fav_service:
        has_favs = await fav_service.has_any_favorites(user_id)

    is_staff = user_data.get('is_staff_order', False)

    # Передаем флаг is_guest в клавиатуру
    reply_markup = get_category_keyboard(
        categories_to_show, cart, is_staff=is_staff,
        back_to_main=is_root_view,
        current_category=target_category if not is_root_view else None,
        has_favorites=has_favs,
        is_guest=is_guest
    )
    await send_order_menu_message(update, context, text, reply_markup)

    # [debug] сохраняем твой оригинальный принт, дополнив его
    logger.debug("UI Categories: Rendered for user %s. GuestMode: %s", user_id, is_guest)
    return SHOWING_CATEGORIES


@auth_guard()
async def show_product_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает список товаров.
    Учитывает: выбранную категорию, результаты поиска, сортировку и режим (список/галерея).
    """
    if update.effective_user is None:
        return SHOWING_PRODUCTS
    user_id = update.effective_user.id
    query = update.callback_query
    user_data: dict[str, Any] = context.user_data or {}

    # Получаем состояние гостя
    is_guest = user_data.get('is_guest', False)

    # Принудительный сброс режима для гостя
    view_mode = user_data.get('view_mode', 'list')
    if is_guest and view_mode == 'gallery':
        view_mode = 'list'
        user_data['view_mode'] = 'list'
        logger.debug("UI Guest: Force switched from Gallery to List for %s", user_id)

    # 1. определяем текущую категорию или режим поиска
    category = user_data.get('current_category', 'all')
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/order.py] TelegramError: {e}")

        if query.data and query.data.startswith(CB_PREFIX_SELECT_CATEGORY):
            category = query.data.replace(CB_PREFIX_SELECT_CATEGORY, '')
        elif query.data and query.data.startswith(CB_PREFIX_CATEGORY_LIST):
            category = query.data.replace(CB_PREFIX_CATEGORY_LIST, '')
        elif query.data and query.data == CB_SHOW_ALL_PRODUCTS:
            category = 'all'
        elif query.data and query.data.startswith(CB_BACK_TO_PRODUCT_LIST):
            category = query.data.replace(CB_BACK_TO_PRODUCT_LIST, '') or user_data.get('current_category', 'all')

    user_data['current_category'] = category
    all_products_dict = await _get_and_cache_all_products(context)

    # 2. фильтрация товаров
    if category == 'all':
        products_to_show = list(all_products_dict.values())
        title = "Все товары"
    elif category == 'search':
        products_to_show = user_data.get('search_results', [])
        search_query = user_data.get('last_search_query', '')
        title = f"🔍 Результаты: «{search_query}»" if search_query else "Результаты поиска"
        logger.info(f"UI Search: Displaying {len(products_to_show)} results for user {user_id}")
    else:
        category_lower = category.lower()
        products_to_show = [p for p in all_products_dict.values() if p.chapters and category_lower in [ch.lower() for ch in p.chapters]]
        title = category.capitalize()

    # 3. применение сортировки
    sort_mode = user_data.get('sort_mode', 'default')
    if sort_mode == 'price_asc':
        products_to_show.sort(key=lambda p: float(p.variants[0].price) if p.variants else 999999)
    elif sort_mode == 'price_desc':
        products_to_show.sort(key=lambda p: float(p.variants[0].price) if p.variants else 0, reverse=True)
    elif sort_mode == 'name_asc':
        products_to_show.sort(key=lambda p: p.name)
    elif sort_mode == 'name_desc':
        products_to_show.sort(key=lambda p: p.name, reverse=True)
    elif sort_mode == 'sca_desc':
        products_to_show.sort(key=lambda p: _extract_sca_score(p.full_description), reverse=True)
    elif sort_mode == 'sca_asc':
        products_to_show.sort(key=lambda p: _extract_sca_score(p.full_description))

    # 4. выбор режима отображения (галерея или список)
    if view_mode == 'gallery' and not user_data.get('gallery_selecting', False):
        user_data['gallery_product_ids'] = [p.id for p in products_to_show]
        user_data['gallery_index'] = 0
        return await show_gallery_view(update, context)

    # 5. финальный рендеринг
    text = f"📦 <b>{title}</b>\nНайдено позиций: {len(products_to_show)}"
    cart_service: CartService = context.bot_data['cart_service']
    cart = await cart_service.get_cart(user_id)

    # Передаем флаг is_guest в клавиатуру
    reply_markup = get_product_list_keyboard(products_to_show, category, cart, is_guest=is_guest)

    await send_order_menu_message(update, context, text, reply_markup)

    logger.debug("UI List: Rendered '%s' for %s, guest=%s, mode=%s", category, user_id, is_guest, view_mode)
    return SHOWING_PRODUCTS


async def _get_gallery_state(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Any:
    return await order_product_view.get_gallery_state(context, user_id)


async def _render_gallery_media(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict[str, Any]) -> Any:
    return await order_product_view.render_gallery_media(update, context, state)


async def show_gallery_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_product_view.show_gallery_view(
        update,
        context,
        show_product_list_fn=show_product_list,
        showing_products_state=SHOWING_PRODUCTS,
    )


@auth_guard()
async def handle_gallery_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_product_view.handle_gallery_nav(
        update,
        context,
        show_gallery_view_fn=show_gallery_view,
    )


@auth_guard()
async def open_gallery_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_product_view.open_gallery_selection(
        update,
        context,
        show_product_list_fn=show_product_list,
    )


def _resolve_product_params(query: Any, product_id: Any, category: Any) -> Any:
    return order_product_view.resolve_product_params(query, product_id, category)


async def _answer_bad_callback(query: Any, raw_data: str, reason: str) -> Any:
    return await order_product_view.answer_bad_callback(query, raw_data, reason)


def _get_image_context(context: Any, query: Any, product: Any, product_id: Any) -> Any:
    return order_product_view.get_image_context(context, query, product, product_id)


def _build_product_caption(product: Any, show_details: Any) -> Any:
    return order_product_view.build_product_caption(product, show_details)


async def _get_product_for_view(product_id: int, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_product_view.get_product_for_view(product_id, context)


async def _render_product_ui(update: Update, context: ContextTypes.DEFAULT_TYPE, product: Any, category: str, show_details: bool) -> Any:
    return await order_product_view.render_product_ui(update, context, product, category, show_details)


@auth_guard()
async def show_product_view(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: Optional[int] = None, category: Optional[str] = None, force_details: Optional[bool] = None) -> int:
    return await order_product_view.show_product_view(
        update,
        context,
        show_product_list_fn=show_product_list,
        handle_gallery_selection_fn=_handle_gallery_selection,
        showing_products_state=SHOWING_PRODUCTS,
        viewing_product_state=VIEWING_PRODUCT,
        product_id=product_id,
        category=category,
        force_details=force_details,
    )


async def _handle_gallery_selection(update: Any, context: Any, product_id: Any) -> Any:
    return await order_product_view.handle_gallery_selection(
        update,
        context,
        product_id,
        show_gallery_view_fn=show_gallery_view,
    )


@auth_guard()
@validate_callback
async def change_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Изменение количества с сохранением режима (Карточка/Галерея) и корректным стейтом."""
    query = update.callback_query
    if query is None or query.data is None:
        return SHOWING_PRODUCTS
    if update.effective_user is None:
        return SHOWING_PRODUCTS
    user_id = update.effective_user.id

    payload = query.data.replace(CB_PREFIX_CHANGE_QUANTITY, '')
    parts = payload.split('_', 2)
    action, product_id, category = parts[0], int(parts[1]), parts[2]

    cart_service: CartService = context.bot_data['cart_service']
    cart = await cart_service.get_cart(user_id)
    p_id_str = str(product_id)

    current_in_cart = cart.get(p_id_str, {}).get('quantity', 0)
    user_data: dict[str, Any] = context.user_data or {}
    view_mode = user_data.get('view_mode', 'list')

    alert_text = ""

    # 1. логика изменения
    if action == 'inc':
        new_qty = current_in_cart + 1
        await cart_service.update_item(user_id, product_id, new_qty)
        user_data['viewed_product_quantity'] = new_qty
        alert_text = "✅ Позиция добавлена"
    elif action == 'dec':
        if current_in_cart > 1:
            new_qty = current_in_cart - 1
            await cart_service.update_item(user_id, product_id, new_qty)
            user_data['viewed_product_quantity'] = new_qty
            alert_text = "➖ Позиция удалена"
        elif current_in_cart == 1:
            await cart_service.remove_item(user_id, product_id)
            user_data['viewed_product_quantity'] = 1
            alert_text = "🗑 Позиция удалена из корзины"
        else:
            alert_text = "🚫 Данной позиции в корзине больше нет"

    await query.answer(alert_text)

    # 2. навигация и стейт
    if view_mode == 'gallery':
        logger.info(f"UI Quantity: Staying in Gallery State for user {user_id}")
        await show_gallery_view(update, context)
        return SHOWING_PRODUCTS # Возвращаем стейт списка!
    else:
        product = await _get_product_for_view(product_id, context)
        if query.message is None or query.message.reply_markup is None:
            return VIEWING_PRODUCT
        details_shown = any("Скрыть детали" in str(btn.text) for row in query.message.reply_markup.inline_keyboard for btn in row)
        await _render_product_ui(update, context, product, category, details_shown)
        return VIEWING_PRODUCT

@validate_callback
@auth_guard()
async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление в корзину из карточки с уведомлением."""
    query = update.callback_query
    if query is None:
        return VIEWING_PRODUCT
    if update.effective_user is None:
        return VIEWING_PRODUCT
    user_id = update.effective_user.id
    user_data: dict[str, Any] = context.user_data or {}
    product_id: Any = user_data.get('viewed_product_id')
    quantity: Any = user_data.get('viewed_product_quantity', 1)
    category: str = user_data.get('current_category', 'all')

    await context.bot_data['cart_service'].update_item(user_id, product_id, quantity)

    # Уведомление пользователю
    await query.answer(f"✅ Позиция добавлена ({quantity} шт.)")

    # Обновляем ui (чтобы кнопка корзины появилась/обновилась)
    product = await _get_product_for_view(product_id, context)
    keyboard_rows = query.message.reply_markup.inline_keyboard if query.message and query.message.reply_markup else []
    details_shown = any("Скрыть детали" in str(btn.text) for row in keyboard_rows for btn in row)

    await _render_product_ui(update, context, product, category, details_shown)
    return VIEWING_PRODUCT

@auth_guard()
async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_cart.show_cart(
        update,
        context,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
        show_categories_fn=show_categories,
        cart_view_state=CART_VIEW,
    )


@auth_guard()
async def show_cart_edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, deleted_id: Optional[int] = None) -> int:
    return await order_cart.show_cart_edit_mode(
        update,
        context,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
        cart_view_state=CART_VIEW,
        deleted_id=deleted_id,
    )


@validate_callback
@auth_guard()
async def handle_cart_edit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_cart.handle_cart_edit_action(
        update,
        context,
        internal_cart_remove_fn=_internal_cart_remove,
        show_cart_edit_mode_fn=show_cart_edit_mode,
    )


async def _internal_cart_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int) -> int:
    return await order_cart.internal_cart_remove(
        update,
        context,
        product_id=product_id,
        show_cart_edit_mode_fn=show_cart_edit_mode,
        cart_view_state=CART_VIEW,
    )


async def _cart_countdown_job(context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_cart.cart_countdown_job(context)


@validate_callback
@auth_guard()
async def handle_cart_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_cart.handle_cart_undo(
        update,
        context,
        show_cart_edit_mode_fn=show_cart_edit_mode,
    )


async def _clear_cart_undo_job(context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_cart.clear_cart_undo_job(context)

@validate_callback
@auth_guard()
async def handle_cart_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_cart.handle_cart_interaction(
        update,
        context,
        show_cart_fn=show_cart,
        cart_view_state=CART_VIEW,
        delivery_method_state=DELIVERY_METHOD,
    )


async def _handle_self_pickup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_self_pickup(
        update=update,
        context=context,
        delivery_method_state=DELIVERY_METHOD,
    )


async def handle_pickup_point_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_pickup_point_choice(  # type: ignore[no-any-return]
        update=update,
        context=context,
        pickup_point_select_callback=CB_PICKUP_POINT_SEL,
        handle_self_pickup_fn=_handle_self_pickup,
        finalize_pickup_choice_fn=_finalize_pickup_choice,
    )


async def _finalize_pickup_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, point: dict[str, Any]) -> int:
    return await order_delivery_checkout.finalize_pickup_choice(  # type: ignore[no-any-return]
        update=update,
        context=context,
        point=point,
        prompt_gift_choice_fn=prompt_gift_choice,
    )


async def _handle_cdek_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_cdek_selection(
        update=update,
        context=context,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
        delivery_method_state=DELIVERY_METHOD,
        delivery_webapp_state=DELIVERY_WEBAPP,
        delivery_back_callback=CB_DELIVERY_BACK,
    )


async def _handle_yandex_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_yandex_selection(
        update=update,
        context=context,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
        delivery_webapp_state=DELIVERY_WEBAPP,
    )


async def choose_delivery_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.choose_delivery_method(  # type: ignore[no-any-return]
        update=update,
        context=context,
        show_cart_fn=show_cart,
        handle_self_pickup_fn=_handle_self_pickup,
        handle_cdek_selection_fn=_handle_cdek_selection,
        handle_yandex_selection_fn=_handle_yandex_selection,
        delivery_back_callback=CB_DELIVERY_BACK,
        delivery_type_self_callback=CB_DELIVERY_TYPE_SELF,
        delivery_type_pickup_callback=CB_DELIVERY_TYPE_PICKUP,
        delivery_type_yandex_callback=CB_DELIVERY_TYPE_YANDEX,
        delivery_method_state=DELIVERY_METHOD,
    )


async def check_webapp_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.check_webapp_choice(  # type: ignore[no-any-return]
        update=update,
        context=context,
        finalize_order_and_pay_fn=_finalize_order_and_pay,
        delivery_method_state=DELIVERY_METHOD,
        delivery_webapp_state=DELIVERY_WEBAPP,
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_webapp_data(  # type: ignore[no-any-return]
        update=update,
        context=context,
        prompt_gift_choice_fn=prompt_gift_choice,
        delivery_webapp_state=DELIVERY_WEBAPP,
    )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_ui_helpers.done(update, context)

@auth_guard(staff_only=True)
async def exit_to_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_ui_helpers.exit_to_panel(update, context)

@auth_guard()
async def exit_to_user_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_ui_helpers.exit_to_user_main_menu(update, context)

@auth_guard()
async def toggle_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_search_sort.toggle_view(  # type: ignore[no-any-return]
        update,
        context,
        show_sort_menu_fn=show_sort_menu,
    )


@auth_guard()
async def show_sort_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_search_sort.show_sort_menu(  # type: ignore[no-any-return]
        update,
        context,
        showing_products_state=SHOWING_PRODUCTS,
    )


async def apply_sort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_search_sort.apply_sort(  # type: ignore[no-any-return]
        update,
        context,
        show_sort_menu_fn=show_sort_menu,
    )


async def save_delivery_address_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.save_delivery_address_action(
        update=update,
        context=context,
        save_delivery_address_callback=CB_SAVE_DELIVERY_ADDRESS,
        order_created_state=ORDER_CREATED,
    )


async def use_saved_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.use_saved_address(  # type: ignore[no-any-return]
        update=update,
        context=context,
        get_and_cache_all_products_fn=_get_and_cache_all_products,
        prompt_gift_choice_fn=prompt_gift_choice,
        delivery_webapp_state=DELIVERY_WEBAPP,
    )

async def prompt_gift_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_data: Optional[dict[str, Any]] = None) -> Any:
    return await order_gift.prompt_gift_choice(
        update=update,
        context=context,
        show_cart_fn=show_cart,
        asking_gift_state=ASKING_GIFT,
        delivery_data=delivery_data,
    )

async def handle_gift_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.handle_gift_skip(
        update=update,
        context=context,
        finalize_order_and_pay_fn=_finalize_order_and_pay,
    )


async def handle_gift_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.handle_gift_choice(
        update=update,
        context=context,
        finalize_order_and_pay_fn=_finalize_order_and_pay,
        gift_for_me_callback=CB_GIFT_FOR_ME,
        gift_as_present_callback=CB_GIFT_AS_PRESENT,
        awaiting_gift_comment_state=AWAITING_GIFT_COMMENT,
    )


async def handle_gift_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.handle_gift_comment(
        update=update,
        context=context,
        finalize_order_and_pay_fn=_finalize_order_and_pay,
    )


def truncate_caption(text: str, limit: int = 1010) -> tuple[str, bool]:
    return order_ui_helpers.truncate_caption(text, limit)

async def show_full_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_ui_helpers.show_full_description(
        update=update,
        context=context,
        read_full_desc_callback=CB_READ_FULL_DESC,
        close_generic_callback=CB_CLOSE_GENERIC,
    )


async def handle_product_image_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_product_view.handle_product_image_nav(
        update,
        context,
        viewing_product_state=VIEWING_PRODUCT,
    )


async def show_product_image_grid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_product_view.show_product_image_grid(
        update,
        context,
        viewing_product_state=VIEWING_PRODUCT,
    )


async def show_product_quantity_grid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_product_view.show_product_quantity_grid(
        update,
        context,
        viewing_product_state=VIEWING_PRODUCT,
    )

async def handle_set_quantity_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_product_view.handle_set_quantity_preset(
        update,
        context,
        show_product_view_fn=show_product_view,
        viewing_product_state=VIEWING_PRODUCT,
    )

async def handle_clear_product_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_product_view.handle_clear_product_action(
        update,
        context,
        show_product_view_fn=show_product_view,
        internal_cart_remove_fn=_internal_cart_remove,
        viewing_product_state=VIEWING_PRODUCT,
    )


@auth_guard()
async def show_cart_quantity_grid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_cart.show_cart_quantity_grid(
        update,
        context,
        answer_bad_callback_fn=_answer_bad_callback,
        cart_view_state=CART_VIEW,
    )

@auth_guard()
async def handle_cart_preset_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_cart.handle_cart_preset_qty(
        update,
        context,
        answer_bad_callback_fn=_answer_bad_callback,
        show_cart_edit_mode_fn=show_cart_edit_mode,
        cart_view_state=CART_VIEW,
    )


async def handle_order_restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возвращает заказу статус 'Принят' и показывает финальный экран."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    await query.answer()

    order_id = int(query.data.replace(CB_ORDER_RESTORE, ""))
    order_service: OrderService = context.bot_data['order_service']

    logger.debug("Restoring order #%s", order_id)

    # 1. возвращаем статус
    await order_service.update_order_status(order_id, OrderStatus.ACCEPTED)  # type: ignore[arg-type]

    # 2. загружаем данные для финального экрана
    details = await order_service.get_full_order_details(order_id)
    if not details:
        await query.edit_message_text("Ошибка при восстановлении.")
        return ConversationHandler.END

    order, items = details
    # Считаем суммы для ui
    cart_total = sum(float(item.price) * item.quantity for item in items)  # type: ignore[arg-type,misc]

    # 3. перерисовываем экран успеха (через нашу обновленную функцию)
    await _send_order_success_message(
        update, context, order,
        f"✅ <b>Заказ #{order_id} успешно восстановлен!</b>",
        (cart_total, order.total_amount),
        order.delivery_address,  # type: ignore[attr-defined]
        order.payment_url  # type: ignore[arg-type]
    )

    logger.info(f"[ORDER] User restored order #{order_id}")
    return ORDER_CREATED


async def handle_repeat_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Клонирует заказ, проверяет актуальность цен и уведомляет об изменениях."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if update.effective_user is None:
        return ConversationHandler.END
    user_id = update.effective_user.id

    await query.answer("Проверяем цены и наличие...")

    order_id = int(query.data.replace(CB_REPEAT_ORDER, ""))

    order_service: OrderService = context.bot_data['order_service']
    cart_service: CartService = context.bot_data['cart_service']
    product_service: ProductService = context.bot_data['product_service']

    # 1. загружаем старый заказ
    details = await order_service.get_full_order_details(order_id)
    if not details:
        if query.message:
            await query.message.reply_text("❌ Ошибка: данные старого заказа не найдены.")
        return ConversationHandler.END
    old_order, old_items = details

    # 2. получаем актуальный каталог
    all_available = await product_service.get_available_products(light_mode=False)
    current_products = {p.id: p for p in all_available}

    # 3. анализируем изменения
    price_changes = []
    unavailable_items = []
    items_to_add = []

    for item in old_items:
        current_p = current_products.get(item.product_id)

        if not current_p or not current_p.is_available:
            unavailable_items.append(f"• {item.product_id} (Нет в наличии)")
            continue

        # Берем цену первого варианта (как основную)
        current_price = float(current_p.variants[0].price) if current_p.variants else 0.0
        old_price = float(item.price)  # type: ignore[arg-type]

        if abs(current_price - old_price) > 0.01:
            price_changes.append(f"• <b>{current_p.name}</b>: {old_price}₽ → {current_price}₽")

        items_to_add.append((item.product_id, item.quantity))

    # 4. формируем отчет для пользователя
    report_lines = []
    if price_changes:
        report_lines.append("📢 <b>Внимание: цены на некоторые товары изменились:</b>")
        report_lines.extend(price_changes)
        report_lines.append("")

    if unavailable_items:
        report_lines.append("⚠️ <b>Следующие товары сейчас недоступны и не добавлены:</b>")
        report_lines.extend(unavailable_items)
        report_lines.append("")

    # 5. очищаем и наполняем корзину
    if items_to_add:
        await cart_service.clear_cart(user_id)
        for p_id, qty in items_to_add:
            await cart_service.update_item(user_id, p_id, qty)

        logger.info(f"[ORDER] User {user_id} repeated order #{order_id}. Items added: {len(items_to_add)}")
    else:
        if query.message:
            await query.message.reply_text("❌ К сожалению, ни одного товара из этого заказа сейчас нет в наличии.")
        return STATE_HOME

    # 6. уведомление о доставке
    report_lines.append("🚛 <i>Стоимость доставки будет пересчитана по текущим тарифам на этапе оформления.</i>")

    # Отправляем уведомление, если были изменения
    if price_changes or unavailable_items:
        await context.bot.send_message(
            chat_id=user_id,
            text="\n".join(report_lines),
            parse_mode=ParseMode.HTML
        )

    # 7. переходим в корзину
    return await show_cart(update, context)


async def ask_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_search_sort.ask_search_query(  # type: ignore[no-any-return]
        update,
        context,
        awaiting_search_state=AWAITING_SEARCH,
    )


async def process_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_search_sort.process_search(  # type: ignore[no-any-return]
        update,
        context,
        show_product_list_fn=show_product_list,
        awaiting_search_state=AWAITING_SEARCH,
    )


async def _handle_courier_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_courier_selection(
        update=update,
        context=context,
        delivery_back_callback=CB_DELIVERY_BACK,
        delivery_method_state=DELIVERY_METHOD,
    )


async def handle_semantic_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_search_sort.handle_semantic_search(
        update,
        context,
        show_categories_fn=show_categories,
        show_product_list_fn=show_product_list,
        showing_categories_state=SHOWING_CATEGORIES,
        awaiting_search_state=AWAITING_SEARCH,
    )


async def handle_courier_city_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_delivery_checkout.handle_courier_city_choice(  # type: ignore[no-any-return]
        update=update,
        context=context,
        delivery_courier_city_callback=CB_DELIVERY_COURIER_CITY,
        handle_courier_selection_fn=_handle_courier_selection,
        prompt_gift_choice_fn=prompt_gift_choice,
    )


async def show_brewing_methods_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_brew.show_brewing_methods_choice(
        update=update,
        context=context,
        get_product_for_view_fn=_get_product_for_view,
        brew_guide_callback=CB_BREW_GUIDE,
        viewing_product_state=VIEWING_PRODUCT,
    )


def _get_brew_method_label(method_code: str) -> str:
    return order_brew.get_brew_method_label(method_code)

async def _prepare_recipe_content(product: Product, method_label: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await order_brew.prepare_recipe_content(product, method_label, context)


async def _display_brewing_guide(query: Any, user_id: Any, full_text: Any, markup: Any, context: Any) -> Any:
    return await order_brew.display_brewing_guide(query, user_id, full_text, markup, context)


async def show_brewing_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_brew.show_brewing_guide(
        update=update,
        context=context,
        get_product_for_view_fn=_get_product_for_view,
        get_brew_method_label_fn=_get_brew_method_label,
        prepare_recipe_content_fn=_prepare_recipe_content,
        display_brewing_guide_fn=_display_brewing_guide,
        brew_method_select_callback=CB_BREW_METHOD_SELECT,
        prefix_select_product_callback=CB_PREFIX_SELECT_PRODUCT,
        viewing_product_state=VIEWING_PRODUCT,
    )


async def save_recipe_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    return await order_brew.save_recipe_action(
        update=update,
        context=context,
        recipe_save_callback=CB_RECIPE_SAVE,
    )


async def start_ai_gift_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.start_ai_gift_help(
        update=update,
        context=context,
        gift_back_callback=CB_GIFT_BACK,
        awaiting_gift_ai_data_state=AWAITING_GIFT_AI_DATA,
    )



async def process_ai_gift_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.process_ai_gift_request(
        update=update,
        context=context,
        gift_as_present_callback=CB_GIFT_AS_PRESENT,
        awaiting_gift_ai_data_state=AWAITING_GIFT_AI_DATA,
    )


async def select_ai_gift_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.select_ai_gift_option(
        update=update,
        context=context,
        finalize_order_and_pay_fn=_finalize_order_and_pay,
        prefix_ai_gift_select_callback=CB_PREFIX_AI_GIFT_SELECT,
        awaiting_gift_comment_state=AWAITING_GIFT_COMMENT,
    )


async def handle_ai_gift_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await order_gift.handle_ai_gift_retry(
        update=update,
        context=context,
        gift_as_present_callback=CB_GIFT_AS_PRESENT,
        awaiting_gift_ai_data_state=AWAITING_GIFT_AI_DATA,
    )


# Импорты для роутера
# Размещены здесь для предотвращения циклических зависимостей.
# К этому моменту функции order.py уже загружены в память.

order_handler = ConversationHandler(
    entry_points=[
        CommandHandler("menu", start_user_order),
        CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
        CallbackQueryHandler(show_fav_quantity_grid, pattern=f"^{CB_FAVORITES_MENU}$"),
        CallbackQueryHandler(handle_repeat_order, pattern=f"^{CB_REPEAT_ORDER}"),
        CallbackQueryHandler(ask_search_query, pattern=f"^{CB_SEARCH_PRODUCTS}$"),
        CallbackQueryHandler(show_saved_recipes_list, pattern=f"^{CB_FAV_RECIPES_LIST}$"),
    ],
    states={
        SHOWING_CATEGORIES: [
            # 1. специфичные действия и навигация
            CallbackQueryHandler(handle_semantic_search, pattern=f"^{CB_SEARCH_SEMANTIC}$"),
            CallbackQueryHandler(ask_search_query, pattern=f"^{CB_SEARCH_PRODUCTS}$"),
            CallbackQueryHandler(show_cart, pattern=f"^{CB_VIEW_CART}$"),
            CallbackQueryHandler(show_favorites_menu, pattern=f"^{CB_FAVORITES_MENU}$"),
            CallbackQueryHandler(show_categories, pattern=f"^{CB_BACK_TO_CATEGORIES}$"),
            CallbackQueryHandler(show_product_list, pattern=f"^({CB_SHOW_ALL_PRODUCTS})$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
            CallbackQueryHandler(save_recipe_action, pattern=f"^{CB_RECIPE_SAVE}"),
            CallbackQueryHandler(show_saved_recipes_list, pattern=f"^{CB_FAV_RECIPES_LIST}$"),
            CallbackQueryHandler(show_saved_recipe_details, pattern=f"^{CB_RECIPE_VIEW_SAVED}"),
            CallbackQueryHandler(delete_recipe_action, pattern=f"^{CB_RECIPE_DELETE}"),
            CallbackQueryHandler(show_favorite_products, pattern=f"^{CB_FAV_PRODUCTS_LIST}$"),
            CommandHandler("menu", start_user_order),
            # 2. префиксы и списки
            CallbackQueryHandler(show_product_view, pattern=f"^{CB_PREFIX_SELECT_PRODUCT}"),
            CallbackQueryHandler(show_categories, pattern=f"^{CB_PREFIX_SELECT_CATEGORY}"),
            CallbackQueryHandler(show_product_list, pattern=f"^{CB_PREFIX_CATEGORY_LIST}"),
            # 3. избранное и повторы
            CallbackQueryHandler(handle_fav_cart_change, pattern=f"^{CB_FAV_ADD_CART}|^{CB_FAV_INC_CART}|^{CB_FAV_DEC_CART}"),
            CallbackQueryHandler(show_fav_quantity_grid, pattern=f"^{CB_PREFIX_FAV_QTY_GRID}"),
            CallbackQueryHandler(handle_fav_preset_qty, pattern=f"^{CB_PREFIX_FAV_SET_QTY}"),
            CallbackQueryHandler(handle_fav_cart_clear, pattern=f"^{CB_FAV_CART_CLEAR}"),
            CallbackQueryHandler(remove_favorite_item, pattern=f"^{CB_PREFIX_RM_FAV}"),
            CallbackQueryHandler(toggle_notification, pattern=f"^{CB_PREFIX_NOTIFY_FAV}"),
            CallbackQueryHandler(undo_remove_favorite, pattern=f"^{CB_FAV_UNDO_RM}"),
            CallbackQueryHandler(handle_repeat_order, pattern=f"^{CB_REPEAT_ORDER}"),
            CommandHandler("menu", start_user_order),
        ],
        SHOWING_PRODUCTS: [
            # 1. сортировка и вид
            CallbackQueryHandler(toggle_favorite_in_card, pattern=f"^{CB_PREFIX_TOGGLE_FAV}"),
            CallbackQueryHandler(show_sort_menu, pattern=f"^{CB_OPEN_SORT_MENU}$"),
            CallbackQueryHandler(apply_sort, pattern=f"^{CB_PREFIX_SET_SORT}"),
            CallbackQueryHandler(toggle_view, pattern=f"^{CB_TOGGLE_VIEW}"),
            # 2. навигация и галерея (сюда добавлены хендлеры количества)
            CallbackQueryHandler(handle_gallery_nav, pattern=f"^{CB_GALLERY_NEXT}$|^{CB_GALLERY_PREV}$|^{CB_GALLERY_ADD}"),
            CallbackQueryHandler(change_quantity, pattern=f"^{CB_PREFIX_CHANGE_QUANTITY}"),
            CallbackQueryHandler(show_product_quantity_grid, pattern=f"^{CB_PREFIX_QTY_GRID}"),
            CallbackQueryHandler(handle_set_quantity_preset, pattern=f"^{CB_PREFIX_SET_QTY}"),
            CallbackQueryHandler(handle_clear_product_action, pattern=f"^{CB_PRODUCT_CLEAR}"),
            CallbackQueryHandler(open_gallery_selection, pattern=f"^{CB_GALLERY_OPEN_LIST}$"),
            CallbackQueryHandler(show_categories, pattern=f"^{CB_BACK_TO_CATEGORIES}$"),
            CallbackQueryHandler(show_product_list, pattern=f"^{CB_BACK_TO_PRODUCT_LIST}$"),
            # 3. общие действия
            CallbackQueryHandler(show_product_view, pattern=f"^{CB_PREFIX_SELECT_PRODUCT}"),
            CallbackQueryHandler(show_favorites_menu, pattern=f"^{CB_FAVORITES_MENU}$"),
            CallbackQueryHandler(show_cart, pattern=f"^{CB_VIEW_CART}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CommandHandler("menu", start_user_order),
        ],
        VIEWING_PRODUCT: [
            # 1. интерактив внутри карточки (фото, количество, описание)
            CallbackQueryHandler(show_brewing_methods_choice, pattern=f"^{CB_BREW_GUIDE}"),
            CallbackQueryHandler(show_brewing_guide, pattern=f"^{CB_BREW_METHOD_SELECT}"),
            CallbackQueryHandler(handle_product_image_nav, pattern=f"^{CB_PREFIX_PROD_IMG}"),
            CallbackQueryHandler(show_product_image_grid, pattern=f"^{CB_PREFIX_IMG_GRID}"),
            CallbackQueryHandler(show_product_quantity_grid, pattern=f"^{CB_PREFIX_QTY_GRID}"),
            CallbackQueryHandler(handle_set_quantity_preset, pattern=f"^{CB_PREFIX_SET_QTY}"),
            CallbackQueryHandler(handle_clear_product_action, pattern=f"^{CB_PRODUCT_CLEAR}"),
            CallbackQueryHandler(change_quantity, pattern=f"^{CB_PREFIX_CHANGE_QUANTITY}"),
            CallbackQueryHandler(show_full_description, pattern=f"^{CB_READ_FULL_DESC}"),
            CallbackQueryHandler(show_favorite_products, pattern=f"^{CB_FAV_PRODUCTS_LIST}$"),
            # 2. действия с товаром
            CallbackQueryHandler(add_to_cart, pattern=f"^{CB_ADD_TO_CART}"),
            CallbackQueryHandler(toggle_favorite_in_card, pattern=f"^{CB_PREFIX_TOGGLE_FAV}"),
            # 3. навигация назад/выход
            CallbackQueryHandler(show_cart_edit_mode, pattern=f"^{CB_EDIT_CART}$"),
            CallbackQueryHandler(show_product_list, pattern=f"^{CB_BACK_TO_PRODUCT_LIST}"),
            CallbackQueryHandler(show_product_view, pattern=f"^{CB_PREFIX_SELECT_PRODUCT}"),
            CallbackQueryHandler(show_favorites_menu, pattern=f"^{CB_FAVORITES_MENU}$"),
            CallbackQueryHandler(show_cart, pattern=f"^{CB_VIEW_CART}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CommandHandler("menu", start_user_order),
            # [критично] добавляем обработку кнопок рецепта внутри карточки
            CallbackQueryHandler(show_brewing_guide, pattern=f"^{CB_BREW_GUIDE}"),
            CallbackQueryHandler(save_recipe_action, pattern=f"^{CB_RECIPE_SAVE}"),
            # 4. избранное и повторы
            CallbackQueryHandler(show_cart_edit_mode, pattern=f"^{CB_EDIT_CART}$"),
            CallbackQueryHandler(show_product_list, pattern=f"^{CB_BACK_TO_PRODUCT_LIST}"),
            CallbackQueryHandler(show_product_view, pattern=f"^{CB_PREFIX_SELECT_PRODUCT}"),
            CallbackQueryHandler(show_favorites_menu, pattern=f"^{CB_FAVORITES_MENU}$"),
            CallbackQueryHandler(show_cart, pattern=f"^{CB_VIEW_CART}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
            CommandHandler("menu", start_user_order),
        ],
        CART_VIEW: [
            # 1. действия оформления
            CallbackQueryHandler(handle_cart_interaction, pattern=f"^{CB_CHECKOUT}$|^{CB_CLEAR_CART}$"),
            CallbackQueryHandler(show_cart_edit_mode, pattern=f"^{CB_EDIT_CART}$"),
            CallbackQueryHandler(show_cart, pattern=f"^{CB_BACK_TO_CART_SUMMARY}$"),
            # 2. редактирование состава
            CallbackQueryHandler(handle_cart_edit_action, pattern=f"^{CB_PREFIX_CART_INC}|^{CB_PREFIX_CART_DEC}|^{CB_PREFIX_CART_DEL}"),
            CallbackQueryHandler(handle_cart_undo, pattern=f"^{CB_CART_UNDO_RM}"),
            CallbackQueryHandler(show_cart_quantity_grid, pattern=f"^{CB_PREFIX_CART_QTY_GRID}"),
            CallbackQueryHandler(handle_cart_preset_qty, pattern=f"^{CB_PREFIX_CART_SET_QTY}"),
            # 3. навигация
            CallbackQueryHandler(show_product_view, pattern=f"^{CB_PREFIX_SELECT_PRODUCT}"),
            CallbackQueryHandler(show_categories, pattern=f"^{CB_BACK_TO_CATEGORIES}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CommandHandler("menu", start_user_order),
        ],
        DELIVERY_METHOD: [
            CallbackQueryHandler(choose_delivery_method, pattern=f"^{CB_DELIVERY_TYPE_PICKUP}|^{CB_DELIVERY_TYPE_COURIER}|^{CB_DELIVERY_BACK}|^{CB_DELIVERY_TYPE_SELF}|^{CB_DELIVERY_TYPE_YANDEX}"),
            CallbackQueryHandler(_handle_courier_selection, pattern=f"^{CB_DELIVERY_TYPE_COURIER}$"),
            CallbackQueryHandler(handle_courier_city_choice, pattern=f"^{CB_DELIVERY_COURIER_CITY}"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
            CallbackQueryHandler(handle_pickup_point_choice, pattern=f"^{CB_PICKUP_POINT_SEL}"),
        ],
        DELIVERY_WEBAPP: [
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data),
            CallbackQueryHandler(use_saved_address, pattern=f"^{CB_USE_DEFAULT_ADDRESS}$"),
            CallbackQueryHandler(check_webapp_choice, pattern="^check_webapp_choice$"),
            CallbackQueryHandler(choose_delivery_method, pattern=f"^{CB_DELIVERY_BACK}"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
        ],
        ASKING_GIFT: [
            CallbackQueryHandler(handle_gift_choice, pattern=f"^{CB_GIFT_FOR_ME}$|^{CB_GIFT_AS_PRESENT}$"),
            CallbackQueryHandler(choose_delivery_method, pattern=f"^{CB_DELIVERY_BACK}"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
        ],
        AWAITING_GIFT_COMMENT: [
            CallbackQueryHandler(start_ai_gift_help, pattern=f"^{CB_AI_GIFT_HELP}$"),
            CallbackQueryHandler(handle_gift_skip, pattern=f"^{CB_GIFT_SKIP}$"),
            CallbackQueryHandler(prompt_gift_choice, pattern=f"^{CB_GIFT_BACK}$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gift_comment),
            CommandHandler("skip", handle_gift_comment),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
        ],
        AWAITING_GIFT_AI_DATA: [
            CallbackQueryHandler(handle_ai_gift_retry, pattern=f"^{CB_AI_GIFT_RETRY}$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_ai_gift_request),
            CallbackQueryHandler(select_ai_gift_option, pattern=f"^{CB_PREFIX_AI_GIFT_SELECT}"),
            CallbackQueryHandler(handle_gift_choice, pattern=f"^{CB_GIFT_AS_PRESENT}$"),
            CallbackQueryHandler(prompt_gift_choice, pattern=f"^{CB_GIFT_BACK}$"),
        ],
        ORDER_CREATED: [
            CallbackQueryHandler(save_delivery_address_action, pattern=f"^{CB_SAVE_DELIVERY_ADDRESS}$"),
            CallbackQueryHandler(handle_order_created_actions, pattern=f"^{CB_ORDER_ACTION_CANCEL}|^{CB_ORDER_ACTION_CHANGE_DELIVERY}"),
            CallbackQueryHandler(handle_order_restore, pattern=f"^{CB_ORDER_RESTORE}"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
        ],
        AWAITING_SEARCH: [
            # [критично] сначала обрабатываем нажатия кнопок (умный поиск, назад)
            CallbackQueryHandler(handle_semantic_search, pattern=f"^{CB_SEARCH_SEMANTIC}$"),
            CallbackQueryHandler(show_categories, pattern=f"^{CB_BACK_TO_CATEGORIES}$"),
            CallbackQueryHandler(start_user_order, pattern=f"^{CB_USER_START_ORDERING}$"),
            # [критично] только потом текст, иначе он перехватит все колбэки
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_search),
        ],
    },
    fallbacks=[
        CommandHandler("done", done),
        CallbackQueryHandler(exit_to_panel, pattern=f"^{CB_STAFF_PANEL}$"),
        CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_GO_TO_MAIN_MENU}$"),
        CallbackQueryHandler(exit_to_user_main_menu, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"),
    ],
    per_user=True,
    per_chat=True,
    persistent=True,
    name="order_conversation",
    allow_reentry=True # Позволяет перезапускать поиск/заказ в любой момент
)

