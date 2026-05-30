import json
import logging
import time
from typing import Any, Optional

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from tg_bot.app_config import get_app_config
from tg_bot.bot_services.cart_service import CartService
from tg_bot.bot_services.delivery_service import DeliveryService
from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.payment_service import PaymentService
from tg_bot.bot_services.settings_service import SettingsService
from tg_bot.bot_services.user_address_service import UserAddressService
from tg_bot.bot_services.user_service import UserService
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import get_delivery_method_keyboard, get_webapp_keyboard
from tg_bot.tenant.config import FeatureFlags

logger = logging.getLogger(__name__)


async def calculate_order_totals(
    user_id: int,
    delivery_price: float,
    context: ContextTypes.DEFAULT_TYPE,
    get_and_cache_all_products_fn: Any,
) -> Any:
    """Вспомогательная функция: Получает корзину и считает суммы."""
    cart_service: CartService = context.bot_data['cart_service']
    cart = await cart_service.get_cart(user_id)

    if not cart:
        return None

    all_products_dict = await get_and_cache_all_products_fn(context)
    products_in_cart = {pid: all_products_dict[pid] for pid in [int(k) for k in cart.keys()] if pid in all_products_dict}

    cart_total = 0.0
    for _, item in cart.items():
        cart_total += float(item['price']) * int(item['quantity'])

    final_total = cart_total + delivery_price
    return cart, products_in_cart, cart_total, final_total


async def persist_order(
    user_id: int,
    cart: dict[str, Any],
    totals: tuple[float, float],
    delivery_data: tuple[Any, ...],
    context: ContextTypes.DEFAULT_TYPE,
    is_gift: bool = False,
    gift_comment: Optional[str] = None,
) -> Any:
    """Вспомогательная функция: Создает или Обновляет заказ в БД."""
    logger.debug("_persist_order: is_gift=%s, comment=%s", is_gift, gift_comment)
    cart_total, final_total = totals
    delivery_type, delivery_address, delivery_price, delivery_point_id, delivery_info = delivery_data

    order_service: OrderService = context.bot_data['order_service']
    user_data: dict[str, Any] = context.user_data or {}
    editing_order_id = user_data.get('editing_order_id')

    if editing_order_id:
        logger.info(f"📝 Обновляем существующий заказ #{editing_order_id}")
        order = await order_service.update_order_delivery(
            order_id=editing_order_id,
            total_amount=final_total,
            delivery_type=delivery_type,
            delivery_address=delivery_address,
            delivery_price=delivery_price,
            delivery_point_id=delivery_point_id,
            delivery_info=delivery_info,
            is_gift=is_gift,
            gift_comment=gift_comment,
        )
        del user_data['editing_order_id']
        msg_prefix = f"✅ <b>Заказ #{order.id} успешно обновлен!</b>"
    else:
        logger.info(f"🆕 Создаем новый заказ. Подарок: {is_gift}")
        order = await order_service.create_order(
            user_id=user_id,
            cart=cart,
            total_amount=final_total,
            delivery_type=delivery_type,
            delivery_address=delivery_address,
            delivery_price=delivery_price,
            delivery_point_id=delivery_point_id,
            delivery_info=delivery_info,
            is_gift=is_gift,
            gift_comment=gift_comment,
        )
        msg_prefix = f"✅ <b>Заказ #{order.id} успешно оформлен!</b>"

    return order, msg_prefix


async def send_order_success_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: Any,
    msg_prefix: str,
    totals: tuple[float, float],
    delivery_address: str,
    payment_url: str,
    save_delivery_address_callback: str,
    order_action_cancel_callback: str,
    order_action_change_delivery_callback: str,
    go_to_main_menu_callback: str,
) -> Any:
    """Формирует текст и клавиатуру успешного заказа с проверкой на дубликаты ПВЗ."""
    cart_total, final_total = totals
    delivery_price = final_total - cart_total
    if update.effective_user is None:
        return
    user_id = update.effective_user.id

    address_service: UserAddressService = context.bot_data['address_service']
    delivery = order.delivery
    is_pvz_saved = False

    if delivery and delivery.point_id:
        provider = 'cdek' if 'cdek' in delivery.delivery_type else 'yandex'
        saved_addresses = await address_service.get_addresses(user_id, provider)
        is_pvz_saved = any(addr['point_id'] == delivery.point_id for addr in saved_addresses)

    logger.debug("Order #%s final screen. PVZ %s is_saved=%s", order.id, delivery.point_id if delivery else None, is_pvz_saved)

    result_text = (
        f"{msg_prefix}\n\n"
        f"📦 Товары: {cart_total}₽\n"
        f"🚚 Доставка: {delivery_price}₽\n"
        f"📍 Адрес: {delivery_address}\n"
        f"💰 <b>Итого к оплате: {final_total}₽</b>"
    )

    keyboard = []
    if delivery and delivery.delivery_type in ['cdek_point', 'yandex_point'] and delivery.point_id and not is_pvz_saved:
        keyboard.append([InlineKeyboardButton("💾 Сохранить этот ПВЗ", callback_data=save_delivery_address_callback)])

    if payment_url and not payment_url.startswith("#error"):
        result_text += "\n\n👇 <b>Нажмите кнопку ниже для оплаты:</b>"
        keyboard.append([InlineKeyboardButton("💳 Оплатить сейчас", url=payment_url)])
    else:
        result_text += "\n\n⚠️ <i>Ошибка генерации ссылки. Менеджер свяжется с вами для оплаты.</i>"

    keyboard.append([InlineKeyboardButton("❌ Отменить заказ", callback_data=order_action_cancel_callback)])
    keyboard.append([InlineKeyboardButton("⬅️ Изменить способ доставки", callback_data=order_action_change_delivery_callback)])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data=go_to_main_menu_callback)])

    user_data: dict[str, Any] = context.user_data or {}
    markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query

    try:
        if query:
            if query.message is None:
                return
            await query.edit_message_text(text=result_text, reply_markup=markup, parse_mode=ParseMode.HTML)
            user_data['last_global_menu_id'] = query.message.message_id
        else:
            msg = await context.bot.send_message(chat_id=user_id, text=result_text, reply_markup=markup, parse_mode=ParseMode.HTML)
            user_data['last_global_menu_id'] = msg.message_id
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error sending final order message: {e}")


async def finalize_order_and_pay(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    delivery_type: str,
    delivery_price: float,
    delivery_address: str,
    get_and_cache_all_products_fn: Any,
    send_order_success_message_fn: Any,
    order_created_state: int,
    delivery_point_id: Optional[str] = None,
    delivery_info: Optional[dict[str, Any]] = None,
    is_gift: bool = False,
    gift_comment: Optional[str] = None,
) -> int:
    """
    Главная функция-оркестратор финализации заказа.
    Теперь с визуальным фидбеком 'Сохраняем данные...'.
    """
    logger.debug("_finalize_order_and_pay: Starting. Gift=%s, PVZ=%s", is_gift, delivery_point_id)
    query = update.callback_query
    if update.effective_user is None:
        return ConversationHandler.END
    user_id = update.effective_user.id

    if query:
        try:
            if query.message is None:
                return ConversationHandler.END
            await query.edit_message_text(
                "⏳ <b>Пожалуйста, подождите. Сохраняем данные заказа и формируем ссылку на оплату...</b>",
                parse_mode=ParseMode.HTML,
            )
        except (ValueError, KeyError, telegram.error.TelegramError):
            logger.warning("[databases/kojo/tg_bot/handlers/order_delivery_checkout.py] Telegramerror")

    calc_result = await calculate_order_totals(
        user_id=user_id,
        delivery_price=delivery_price,
        context=context,
        get_and_cache_all_products_fn=get_and_cache_all_products_fn,
    )
    if not calc_result:
        logger.warning(f"User {user_id} tried to finalize with empty cart.")
        if query:
            await query.answer("Ваша корзина пуста!", show_alert=True)
        return ConversationHandler.END

    cart, products_in_cart, cart_total, final_total = calc_result

    delivery_data = (delivery_type, delivery_address, delivery_price, delivery_point_id, delivery_info)
    try:
        order, msg_prefix = await persist_order(
            user_id=user_id,
            cart=cart,
            totals=(cart_total, final_total),
            delivery_data=delivery_data,
            context=context,
            is_gift=is_gift,
            gift_comment=gift_comment,
        )
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Critical error in _persist_order: {e}", exc_info=True)
        await context.bot.send_message(
            user_id,
            "❌ Произошла ошибка при сохранении в базу данных. Пожалуйста, обратитесь в поддержку.",
        )
        return ConversationHandler.END

    cart_service: CartService = context.bot_data['cart_service']
    await cart_service.clear_cart(user_id)
    user_data: dict[str, Any] = context.user_data or {}
    user_data['current_active_order_id'] = order.id

    user_service: UserService = context.bot_data['user_service']
    payment_service: PaymentService = context.bot_data['payment_service']
    order_service: OrderService = context.bot_data['order_service']

    user = await user_service.get_user(user_id)
    user_fio = user.fio if user else "Клиент"

    logger.debug("Requesting payment URL for order #%s", order.id)
    payment_url = await payment_service.create_payment_url(
        order_id=order.id,
        total_amount=final_total,
        cart=cart,
        products=products_in_cart,
        user_fio=user_fio,
    )

    if payment_url and not payment_url.startswith("#error"):
        await order_service.set_payment_url(order.id, payment_url)
    else:
        logger.error(f"Failed to generate payment URL for order {order.id}: {payment_url}")

    await send_order_success_message_fn(
        update,
        context,
        order,
        msg_prefix,
        (cart_total, final_total),
        delivery_address,
        payment_url,
    )

    # Feature Flag: Auto-approve Orders (skip Moderation)
    app_config = get_app_config(context)
    flags = FeatureFlags(config=app_config)
    if await flags.is_enabled("auto_approve_orders"):
        from tg_bot.domain.order import OrderStatus
        await order_service.update_order_status(order.id, OrderStatus.AWAITING_PAYMENT)
        logger.info("Auto-approve: order %s set to AWAITING_PAYMENT", order.id)

    return order_created_state


async def handle_order_created_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order_action_cancel_callback: str,
    order_action_change_delivery_callback: str,
    order_restore_prefix: str,
    user_show_main_menu_callback: str,
    order_created_state: int,
    delivery_method_state: int,
) -> int:
    """Обрабатывает кнопки 'Отменить' и 'Изменить доставку'."""
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
    await query.answer()

    user_id = update.effective_user.id
    user_data: dict[str, Any] = context.user_data or {}
    order_id = user_data.get('current_active_order_id')

    if not order_id:
        await query.edit_message_text("Ошибка контекста. Заказ не найден.")
        return ConversationHandler.END

    order_service: OrderService = context.bot_data['order_service']
    order_details = await order_service.get_full_order_details(order_id)
    if not order_details:
        await query.edit_message_text("Заказ не найден.")
        return ConversationHandler.END

    _, items = order_details

    if query.data == order_action_cancel_callback:
        await order_service.cancel_order_with_reason(order_id, "Отменен пользователем")
        logger.info(f"[ORDER] Order #{order_id} cancelled by user.")

        keyboard = [
            [InlineKeyboardButton("↩️ Восстановить заказ", callback_data=f"{order_restore_prefix}{order_id}")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data=user_show_main_menu_callback)],
        ]
        await query.edit_message_text(
            f"❌ <b>Заказ #{order_id} был отменен.</b>\n\nВы можете восстановить его, если нажали кнопку случайно.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
        return order_created_state

    elif query.data == order_action_change_delivery_callback:
        logger.info(f"🔄 Пользователь редактирует доставку для заказа #{order_id}.")
        cart_service: CartService = context.bot_data['cart_service']
        await cart_service.clear_cart(user_id)
        for item in items:
            await cart_service.update_item(user_id, item.product_id, item.quantity)
        user_data['editing_order_id'] = order_id
        await query.edit_message_text(
            "🚚 <b>Редактирование заказа.</b>\nВыберите новый способ доставки:",
            reply_markup=get_delivery_method_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return delivery_method_state

    return order_created_state


async def handle_self_pickup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    delivery_method_state: int,
) -> int:
    """Показывает клиенту только ВКЛЮЧЕННЫЕ точки самовывоза."""
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

    s_service: SettingsService = context.bot_data['settings_service']
    pickup_points_json = await s_service.get_setting('pickup_points', '[]')
    if pickup_points_json is None:
        pickup_points_json = '[]'
    all_points = json.loads(pickup_points_json)
    active_points = [p for p in all_points if p.get('is_active', True)]

    if not active_points:
        await query.answer("⚠️ К сожалению, сейчас нет доступных пунктов для самовывоза.", show_alert=True)
        return delivery_method_state

    from tg_bot.keyboards import get_pickup_points_keyboard

    text = "🏃 <b>Выберите пункт самовывоза:</b>"
    await query.edit_message_text(text, reply_markup=get_pickup_points_keyboard(active_points), parse_mode='HTML')
    return delivery_method_state


async def handle_pickup_point_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    pickup_point_select_callback: str,
    handle_self_pickup_fn: Any,
    finalize_pickup_choice_fn: Any,
) -> Any:
    """Финализирует выбор конкретной точки самовывоза."""
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
    await query.answer()

    idx = int(query.data.replace(pickup_point_select_callback, ""))

    s_service: SettingsService = context.bot_data['settings_service']
    pickup_points_json = await s_service.get_setting('pickup_points', '[]')
    if pickup_points_json is None:
        pickup_points_json = '[]'
    points = json.loads(pickup_points_json)

    if idx < 0 or idx >= len(points):
        return await handle_self_pickup_fn(update, context)

    selected_point = points[idx]
    return await finalize_pickup_choice_fn(update, context, selected_point)


async def finalize_pickup_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, point: dict[str, Any], prompt_gift_choice_fn: Any) -> Any:
    """Формирует описание точки с учетом графика и дней."""
    days = point.get('days', 0)
    ready_text = f"{days} дн." if days > 0 else "сегодня"

    full_address = (
        f"🏃 Самовывоз: {point['name']}\n"
        f"📍 Адрес: {point['address']}\n"
        f"🕒 График: {point.get('schedule', 'не указан')}\n"
        f"⏱ Готовность: через {ready_text} после оплаты"
    )

    return await prompt_gift_choice_fn(update, context, {
        'delivery_type': 'self_pickup',
        'delivery_price': 0.0,
        'delivery_address': full_address,
        'delivery_info': point,
    })


async def handle_cdek_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_and_cache_all_products_fn: Any,
    delivery_method_state: int,
    delivery_webapp_state: int,
    delivery_back_callback: str,
) -> int:
    """Подготовка и показ виджета СДЭК."""
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

    delivery_service: DeliveryService = context.bot_data['delivery_service']
    cart_service: CartService = context.bot_data['cart_service']
    address_service: UserAddressService = context.bot_data['address_service']

    token = await delivery_service.init_cdek_session_raw(user_id)
    if not token:
        logger.error(f"[Delivery] Failed to init CDEK session for {user_id}")
        await query.edit_message_text(
            "⚠️ Ошибка связи со службой доставки (СДЭК). Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=delivery_back_callback)]]),
        )
        return delivery_method_state

    user_data: dict[str, Any] = context.user_data or {}
    user_data['cdek_token'] = token

    cart = await cart_service.get_cart(user_id)
    products = await get_and_cache_all_products_fn(context)
    total_weight = delivery_service.calculate_cart_weight(cart, products)

    webapp_url = (
        f"{delivery_service.map_url}"
        f"?token={token}"
        f"&apikey={delivery_service.yandex_key}"
        f"&weight={total_weight}"
        f"&_v={int(time.time())}"
    )

    default_addr = await address_service.get_default_address(user_id, 'cdek')
    reply_markup = get_webapp_keyboard(webapp_url, default_address=default_addr)

    await query.edit_message_text(
        "📍 <b>СДЭК</b>\nВыберите пункт выдачи на карте или используйте сохраненный:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )

    user_data['webapp_msg_id'] = query.message.message_id
    return delivery_webapp_state


async def handle_yandex_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_and_cache_all_products_fn: Any,
    delivery_webapp_state: int,
) -> int:
    """Подготовка и показ виджета Яндекс."""
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

    delivery_service: DeliveryService = context.bot_data['delivery_service']
    cart_service: CartService = context.bot_data['cart_service']
    address_service: UserAddressService = context.bot_data['address_service']

    cart = await cart_service.get_cart(user_id)
    products = await get_and_cache_all_products_fn(context)
    total_weight = delivery_service.calculate_cart_weight(cart, products)

    from tg_bot.infrastructure.secrets_loader import SecretsLoader
    yandex_url = SecretsLoader.get("WEBAPP_YANDEX_URL", "https://kojo.xloud.ru/web/yandex_widget.html")
    webapp_url = (
        f"{yandex_url}"
        f"?apikey={delivery_service.yandex_key}"
        f"&weight={total_weight}"
        f"&user_id={user_id}"
        f"&_v={int(time.time())}"
    )

    default_addr = await address_service.get_default_address(user_id, 'yandex')
    reply_markup = get_webapp_keyboard(webapp_url, default_address=default_addr)

    await query.edit_message_text(
        "🟡 <b>Яндекс Доставка</b>\nВыберите пункт выдачи на карте или используйте сохраненный:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )

    user_data: dict[str, Any] = context.user_data or {}
    user_data['webapp_msg_id'] = query.message.message_id
    return delivery_webapp_state


async def choose_delivery_method(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    show_cart_fn: Any,
    handle_self_pickup_fn: Any,
    handle_cdek_selection_fn: Any,
    handle_yandex_selection_fn: Any,
    delivery_back_callback: str,
    delivery_type_self_callback: str,
    delivery_type_pickup_callback: str,
    delivery_type_yandex_callback: str,
    delivery_type_courier_callback: str,
    delivery_method_state: int,
) -> Any:
    """Маршрутизатор выбора способа доставки."""
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
    await query.answer()

    data = query.data

    if data == delivery_back_callback:
        return await show_cart_fn(update, context)
    elif data == delivery_type_self_callback:
        return await handle_self_pickup_fn(update, context)
    elif data == delivery_type_pickup_callback:
        return await handle_cdek_selection_fn(update, context)
    elif data == delivery_type_yandex_callback:
        return await handle_yandex_selection_fn(update, context)
    elif delivery_type_courier_callback and data == delivery_type_courier_callback:
        return await handle_courier_selection(update, context, delivery_back_callback, delivery_method_state)

    logger.warning(f"Unknown delivery method: {data}")
    return delivery_method_state


async def check_webapp_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    finalize_order_and_pay_fn: Any,
    delivery_method_state: int,
    delivery_webapp_state: int,
) -> Any:
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
    await query.answer()

    logger.info(f"[Delivery] User {update.effective_user.id} clicked 'Confirm CDEK Choice' button.")

    user_data: dict[str, Any] = context.user_data or {}
    token = user_data.get('cdek_token')
    if not token:
        await query.edit_message_text("Сессия истекла. Начните выбор заново.")
        return delivery_method_state

    delivery_service: DeliveryService = context.bot_data['delivery_service']
    choice = await delivery_service.get_user_choice(token)

    if choice:
        logger.info(f"[Delivery] Got CDEK choice: {choice}")
        await cleanup_previous_menu(context, update.effective_chat.id)
        return await finalize_order_and_pay_fn(
            update=update,
            context=context,
            delivery_type='cdek_point',
            delivery_price=float(choice.get('price', 0)),
            delivery_address=f"СДЭК: {choice.get('city_name')}, {choice.get('address')} ({choice.get('pvz_code')})",
            delivery_point_id=choice.get('pvz_code'),
            delivery_info=choice,
        )

    await query.answer("Вы еще не подтвердили выбор в окне карты!", show_alert=True)
    return delivery_webapp_state


async def handle_webapp_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt_gift_choice_fn: Any,
    delivery_webapp_state: int,
) -> Any:
    logger.info("🏁 [order handler] сработал обработчик handle_webapp_data!")

    if not update.message or not update.message.web_app_data:
        return delivery_webapp_state

    try:
        raw_data = update.message.web_app_data.data

        # [правило ios] мы не удаляем старое меню с кнопкой webapp (webapp_msg_id) здесь.
        # Если удалить его сейчас, экран моргнет. удаление перенесено в prompt_gift_choice.

        if update.message.message_id > 0:
            try:
                await update.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/order_delivery_checkout.py] TelegramError: {e}")

        data = json.loads(raw_data)
        logger.info(f"✅ [WebApp Payload]: {data}")

        delivery_price = 0.0
        delivery_address = "Самовывоз"
        point_id = None
        delivery_type = 'pickup'

        delivery_service: DeliveryService = context.bot_data['delivery_service']
        assembly_days = delivery_service.assembly_days
        data_type = data.get('type')

        if data_type == 'cdek_point':
            delivery_type = 'cdek_point'
            point_id = data.get('pvz_code')
            if data.get('price'):
                delivery_price = float(data.get('price'))

            cdek_days = int(data.get('days', 0))
            total_days = cdek_days + assembly_days
            days_str = f"{total_days} дн." if cdek_days > 0 else "уточняется"

            delivery_address = (
                f"СДЭК: {data.get('city_name')}, {data.get('address')}\n"
                f"Код: {point_id}\n"
                f"Срок: ~{days_str}"
            )

        elif data_type in ['yandex_point', 'yandex_delivery']:
            delivery_type = 'yandex_point'
            point_id = data.get('pvz_code')

            try:
                delivery_price = float(data.get('price', 0))
            except ValueError:
                delivery_price = 0.0

            y_days = int(data.get('days', 2))
            total_days = y_days + assembly_days

            addr_text = data.get('address', 'Адрес не указан')
            delivery_address = (
                f"Яндекс/ПВЗ: {addr_text}\n"
                f"Срок: ~{total_days} дн."
            )

            logger.info(f"📦 Распознан Яндекс: {delivery_price}₽, {addr_text}")
        else:
            logger.warning(f"⚠️ Неизвестный тип доставки: {data_type}. Используем дефолт.")

        return await prompt_gift_choice_fn(update, context, {
            'delivery_type': delivery_type,
            'delivery_price': delivery_price,
            'delivery_address': delivery_address,
            'delivery_point_id': point_id,
            'delivery_info': data,
        })

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"❌ [Order Handler] Critical Error: {e}", exc_info=True)
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка при обработке данных. Попробуйте еще раз.",
            )
        return ConversationHandler.END

async def save_delivery_address_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    save_delivery_address_callback: str,
    order_created_state: int,
) -> int:
    """Сохраняет адрес доставки из текущего активного заказа."""
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
    user_data: dict[str, Any] = context.user_data or {}
    order_id = user_data.get('current_active_order_id')

    if not order_id:
        await query.answer("Ошибка: заказ не найден в контексте.", show_alert=True)
        return order_created_state

    order_service: OrderService = context.bot_data['order_service']
    address_service: UserAddressService = context.bot_data['address_service']

    order_details = await order_service.get_full_order_details(order_id)
    if not order_details:
        await query.answer("Ошибка получения данных заказа.", show_alert=True)
        return order_created_state

    order, _ = order_details
    delivery = order.delivery
    if not delivery or not delivery.point_id:
        await query.answer("У этого заказа нет ID точки доставки.", show_alert=True)
        return order_created_state

    provider = 'cdek' if 'cdek' in delivery.delivery_type else 'yandex'
    clean_address = delivery.address or ''
    if delivery.info:
        info = delivery.info
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"[databases/kojo/tg_bot/handlers/order_delivery_checkout.py] TelegramError: {e}")
        if isinstance(info, dict):
            clean_address = info.get('address', clean_address)

    try:
        await address_service.add_address(
            user_id=user_id,
            provider=provider,
            point_id=delivery.point_id,
            address_text=clean_address,
            custom_name=f"ПВЗ {provider.capitalize()}",
        )

        await query.answer("✅ Адрес успешно сохранен!", show_alert=True)

        new_keyboard = []
        reply_markup = query.message.reply_markup
        if reply_markup:
            for row in reply_markup.inline_keyboard:
                new_row = []
                for btn in row:
                    if btn.callback_data != save_delivery_address_callback:
                        new_row.append(btn)
                if new_row:
                    new_keyboard.append(new_row)

        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            logger.warning(f"[databases/kojo/tg_bot/handlers/order_delivery_checkout.py] TelegramError: {e}")

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Error saving address: {e}")
        await query.answer("Ошибка при сохранении.", show_alert=True)

    return order_created_state


async def use_saved_address(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    get_and_cache_all_products_fn: Any,
    prompt_gift_choice_fn: Any,
    delivery_webapp_state: int,
) -> Any:
    """Использование сохраненного адреса для быстрого заказа."""
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
    await query.answer()

    user_id = update.effective_user.id
    address_service: UserAddressService = context.bot_data['address_service']
    delivery_service: DeliveryService = context.bot_data['delivery_service']
    cart_service: CartService = context.bot_data['cart_service']

    msg_text = query.message.text.lower() if query.message.text else ""
    provider = 'yandex' if 'яндекс' in msg_text else 'cdek'

    saved_addr = await address_service.get_default_address(user_id, provider)
    if not saved_addr:
        await query.edit_message_text("Ошибка: сохраненный адрес не найден. Выберите на карте.")
        return delivery_webapp_state

    await query.edit_message_text(f"⏳ Выбран адрес: {saved_addr['address_text']}. Считаем стоимость...")

    cart = await cart_service.get_cart(user_id)
    products = await get_and_cache_all_products_fn(context)
    weight = delivery_service.calculate_cart_weight(cart, products)

    price = 0.0
    if provider == 'yandex':
        price = await delivery_service.calc_yandex_price_server_side(saved_addr['point_id'], weight)
        delivery_type = 'yandex_point'
    else:
        price = 0.0
        delivery_type = 'cdek_point'

    return await prompt_gift_choice_fn(update, context, {
        'delivery_type': delivery_type,
        'delivery_price': price,
        'delivery_address': saved_addr['address_text'],
        'delivery_point_id': saved_addr['point_id'],
        'delivery_info': {'source': 'saved_address'},
    })


async def handle_courier_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    delivery_back_callback: str,
    delivery_method_state: int,
) -> int:
    """Показывает список доступных городов для курьерской доставки."""
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
    await query.answer()

    s_service: SettingsService = context.bot_data['settings_service']
    courier_cities_json = await s_service.get_setting('courier_cities', '[]')
    if courier_cities_json is None:
        courier_cities_json = '[]'
    cities = json.loads(courier_cities_json)

    if not cities:
        await query.edit_message_text(
            "⚠️ К сожалению, курьерская доставка сейчас не настроена для вашего региона.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=delivery_back_callback)]]),
        )
        return delivery_method_state

    from tg_bot.keyboards import get_courier_cities_keyboard

    await query.edit_message_text(
        "🏘 <b>Выберите ваш город:</b>",
        reply_markup=get_courier_cities_keyboard(cities),
        parse_mode=ParseMode.HTML,
    )
    return delivery_method_state


async def handle_courier_city_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    delivery_courier_city_callback: str,
    handle_courier_selection_fn: Any,
    prompt_gift_choice_fn: Any,
) -> Any:
    """Финализирует выбор города."""
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
    city_name = query.data.replace(delivery_courier_city_callback, "")

    s_service: SettingsService = context.bot_data['settings_service']
    courier_cities_json = await s_service.get_setting('courier_cities', '[]')
    if courier_cities_json is None:
        courier_cities_json = '[]'
    cities = json.loads(courier_cities_json)
    city = next((c for c in cities if c['name'] == city_name), None)

    if not city:
        return await handle_courier_selection_fn(update, context)

    return await prompt_gift_choice_fn(update, context, {
        'delivery_type': 'courier',
        'delivery_price': float(city['cost']),
        'delivery_address': f"Курьер: {city['name']}",
        'delivery_info': city,
    })
