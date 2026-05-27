# Tg_bot/handlers/staff.py
import asyncio
import logging
from typing import Any

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import tg_bot.bot_services.product_sync_service as sync_service
from tg_bot.bot_services.notification_service import NotificationService
from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.user_service import UserService
from tg_bot.decorators import auth_guard
from tg_bot.keyboards import (
    CB_ADMIN_BACK_TO_MAIN,
    CB_ADMIN_BACK_TO_STAFF_MENU,
    CB_CLOSE_GENERIC,
    get_order_details_keyboard,
)
from tg_bot.models import OrderStatus, UserRole

logger = logging.getLogger(__name__)

@auth_guard(staff_only=True)
async def show_active_orders_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Шорткат-команда (/orders) для персонала.
    Показывает заказы, требующие активной работы (Оплаченные и Готовые к выдаче).
    """
    order_service: OrderService = context.bot_data['order_service']
    # Изменено: ищем заказы в двух активных статусах
    active_statuses = [OrderStatus.PAID, OrderStatus.READY_FOR_PICKUP]
    active_orders = await order_service.get_orders_for_staff_view(active_statuses)  # type: ignore[arg-type]

    # Responder может быть как сообщением, так и результатом колбека
    query = update.callback_query
    if query is not None:
        responder = query.message
    else:
        responder = update.message
    if responder is None:
        return

    if not active_orders:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]])
        sent_message = await responder.reply_text(
            "✅ Все активные заказы обработаны.",
            reply_markup=reply_markup
        )

        async def _delete_message_after_delay(msg: Any, delay: int) -> None:
            await asyncio.sleep(delay)
            try:
                await msg.delete()
            except (ValueError, KeyError, telegram.error.TelegramError) as e:
                logger.warning(f"Не удалось автоматически удалить сообщение: {e}")

        asyncio.create_task(_delete_message_after_delay(sent_message, 60))
        if update.callback_query:
            await update.callback_query.answer()
        return

    await responder.reply_text(f"🧾 *Активные заказы ({len(active_orders)} шт.):*", parse_mode=ParseMode.MARKDOWN)
    for order_data in active_orders:
        # Изменено: используем новую, более надежную клавиатуру из admin_panel
        # Вместо старой клавиатуры с одной кнопкой "выдать"
        from tg_bot.models import Order  # Локальный импорт
        mock_order = Order.construct(id=order_data['id'], status=OrderStatus.PAID) # Создаем mock-объект для клавиатуры

        reply_markup = get_order_details_keyboard(mock_order, OrderStatus.PAID.name) # Генерируем полную клавиатуру действий

        order_text = (
            f"<b>Заказ №{order_data['id']}</b>\n"
            f"От: {order_data['user_fio']}\n"
            f"Состав: {order_data['items_str']}\n"
            f"Сумма: {order_data['total_amount']}₽"
        )
        await responder.reply_text(order_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    if update.callback_query:
        await update.callback_query.answer()


@auth_guard(staff_only=True)
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Показывает статистику по заказам с новыми статусами."""
    order_service: OrderService = context.bot_data['order_service']
    stats = await order_service.get_order_counts_by_status()

    # Изменено: используем новые статусы
    _s_awaiting = stats.get(OrderStatus.AWAITING_PAYMENT, 0)  # type: ignore[call-overload]
    _s_paid = stats.get(OrderStatus.PAID, 0)  # type: ignore[call-overload]
    _s_ready = stats.get(OrderStatus.READY_FOR_PICKUP, 0)  # type: ignore[call-overload]
    _s_completed = stats.get(OrderStatus.COMPLETED, 0)  # type: ignore[call-overload]
    _s_cancelled = stats.get(OrderStatus.CANCELLED, 0)  # type: ignore[call-overload]

    text = (f"📊 **Статистика по статусам:**\n\n"
            f"⌛️ Ожидают оплаты: {_s_awaiting}\n"
            f"✅ Оплачено: {_s_paid}\n"
            f"📦 Готовы к выдаче: {_s_ready}\n"
            f"🏁 Завершено: {_s_completed}\n"
            f"❌ Отменено: {_s_cancelled}")

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в панель", callback_data=CB_ADMIN_BACK_TO_MAIN)]
    ])

    query = update.callback_query
    if query is not None:
        responder = query.message
        if responder is None:
            return
        await responder.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        await query.answer()
    else:
        message = update.message
        if message is None:
            return
        await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


@auth_guard(staff_only=True)
async def show_my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Показывает профиль сотрудника (карточка-удостоверение).
    """
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    user_service: UserService = context.bot_data['user_service']

    # Получаем данные пользователя из бд
    user = await user_service.get_user(user_id)

    if not user:
        await query.edit_message_text("Ошибка: Профиль не найден.")
        return

    # Красивое форматирование ролей
    role_emoji = "👑" if user.role == UserRole.ADMIN else "👨‍💼"
    role_name = "Администратор" if user.role == UserRole.ADMIN else "Менеджер"

    # Формируем текст карточки
    text = (
        f"👤 <b>Личная карточка сотрудника</b>\n"
        f"──────────────────────\n"
        f"<b>ФИО:</b> {user.fio}\n"
        f"<b>Роль:</b> {role_emoji} {role_name}\n"
        f"<b>Статус:</b> ✅ Активен\n\n"
        f"📱 <b>Телефон:</b> {user.phone}\n"
        f"📧 <b>Email:</b> {user.email}\n"
        f"🆔 <b>ID:</b> {user.telegram_id}\n"
        f"📅 <b>В системе с:</b> {user.created_at.strftime('%d.%m.%Y')}\n"
        f"──────────────────────"
    )

    # Кнопка возврата в меню персонала (не в админ-панель, а в главное меню кнопок)
    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data=CB_ADMIN_BACK_TO_STAFF_MENU)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@auth_guard(staff_only=True)
async def trigger_manual_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Ручной запуск синхронизации товаров и рассылки уведомлений.
    Команда: /sync
    """
    # Отправляем сообщение, что процесс пошел (так как это может занять пару секунд)
    if update.message is None:
        return
    status_msg = await update.message.reply_text("⏳ <b>Начинаю синхронизацию каталога...</b>", parse_mode=ParseMode.HTML)

    try:
        pool = context.bot_data['db_pool']
        notif_service: NotificationService | None = context.bot_data.get('notification_service')

        # 1. синхронизация файлов и бд
        # Этот процесс читает product.txt и обновляет таблицу products
        await sync_service.sync_products(pool)

        await status_msg.edit_text("🔄 Каталог обновлен. Проверяю листы ожидания...")

        # 2. рассылка уведомлений
        # Если товары появились в наличии, подписчики получат сообщения
        if notif_service:
            await notif_service.process_restock_notifications()
            await status_msg.edit_text("✅ <b>Синхронизация и рассылка успешно завершены!</b>", parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text("⚠️ Каталог обновлен, но сервис уведомлений не найден. Рассылка пропущена.", parse_mode=ParseMode.HTML)

    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"Manual sync error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ <b>Ошибка при синхронизации:</b>\n<code>{e}</code>", parse_mode=ParseMode.HTML)
