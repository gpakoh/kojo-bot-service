# Tg_bot/bot_services/notification_service.py
import asyncio
import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from tg_bot.keyboards import CB_PREFIX_SELECT_PRODUCT

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, application: Application) -> None:  # type: ignore[type-arg]
        self.app = application
        # Получаем доступ к сервису избранного через bot_data
        self.fav_service = application.bot_data.get('favorite_service')

    async def process_restock_notifications(self) -> Any:
        """
        Проверяет наличие товаров и рассылает уведомления подписчикам.
        Этот метод должен вызываться после синхронизации товаров.
        """
        if not self.fav_service:
            logger.error("Favoriteservice Not Found In Bot_data")
            return

        logger.info("🔔 запуск проверки уведомлений о поступлении товаров...")

        try:
            # 1. получаем список тех, кого надо уведомить
            pending = await self.fav_service.get_pending_notifications()

            if not pending:
                logger.info("🔕 нет ожидающих уведомлений.")
                return

            logger.info(f"🔔 Найдено {len(pending)} уведомлений для отправки.")

            count = 0
            for item in pending:
                user_id = item['user_id']
                product_id = item['product_id']
                product_name = item['product_name']

                # 2. формируем сообщение
                text = (
                    f"🎉 <b>Товар снова в наличии!</b>\n\n"
                    f"☕️ {product_name}\n\n"
                    f"Вы просили сообщить, когда он появится. Успейте заказать!"
                )

                # Кнопка перехода к товару
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🛍 Перейти к товару", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_fav")
                ]])

                # 3. отправляем
                try:
                    await self.app.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    count += 1

                    # 4. отключаем уведомление, чтобы не спамить повторно
                    await self.fav_service.disable_notification(user_id, product_id)

                    # Небольшая пауза, чтобы не упереться в лимиты телеграма (30 msg/sec)
                    await asyncio.sleep(0.1)

                except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                    logger.error(f"❌ Не удалось отправить уведомление user={user_id}: {e}")
                    # Если юзер заблокировал бота, можно удалить его из избранного, но пока оставим

            logger.info(f"✅ Рассылка завершена. Отправлено: {count}/{len(pending)}")

        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Error processing notifications: {e}", exc_info=True)
