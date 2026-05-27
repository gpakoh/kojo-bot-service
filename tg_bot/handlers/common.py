# Tg_bot/handlers/common.py
import logging
from typing import Any, Optional

import telegram
from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.bot_services.user_service import UserService
from tg_bot.models import UserStatus

logger = logging.getLogger(__name__)

# Вспомогательные функции
def clean_response(text: str) -> str:
    """Удаляет лишние пробелы по краям текста."""
    return text.strip()

# Ядро взаимодействия с ai-сервером
async def cleanup_previous_menu(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, exclude_id: Optional[int] = None
) -> Any:
    """
    Глобальный киллер старых меню и промптов.
    Удаляет якорь из БД и активный prompt_msg_id из сессии.
    """
    user_service: UserService | None = context.bot_data.get('user_service')

    # 1. получаем список id на удаление
    targets_to_delete = set()

    # А. берем основной якорь из бд
    if user_service:
        user_db = await user_service.get_user(chat_id)
        if user_db and user_db.registration_message_id:
            targets_to_delete.add(user_db.registration_message_id)

    # Б. берем временный промпт из сессии (фио, email и т.д.)
    user_data: dict[str, Any] = context.user_data or {}
    session_prompt = user_data.get('prompt_msg_id')
    if session_prompt:
        targets_to_delete.add(session_prompt)

    # 2. выполняем зачистку
    for msg_id in targets_to_delete:
        # [правило ios] не удаляем то, что только что отправили
        if msg_id == exclude_id:
            continue

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.debug("Cleanup: Message %s deleted.", msg_id)
        except (ValueError, KeyError, telegram.error.TelegramError) as e:
            # Игнорируем ошибки если сообщение уже удалено
            logger.debug(f"Cleanup skip for {msg_id}: {e}")

    # 3. обнуляем ссылки (если не предоставили новый exclude_id)
    if not exclude_id:
        user_data.pop('prompt_msg_id', None)

    logger.info(f"Cleanup finished for {chat_id}. Targets found: {len(targets_to_delete)}")


# Заглушка, если safe_delete_message импортируется в order.py из common
async def safe_delete_message(context: Any, chat_id: int, message_id: int) -> bool:
    """Удаляет сообщение с защитой от ошибок (если уже удалено или слишком старое)."""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        # Логируем только критические ошибки, не 400
        if "Message to delete not found" not in str(e):
            logger.debug(f"Safe delete info: {e}")
        return False


async def handle_stale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Глобальный Janitor: оживляет 'мертвые' кнопки.
    Соблюдает правило 1 экрана: не удаляет сообщение сразу, а передает его в start() для мягкой замены.
    """
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None:
        return
    user_id = update.effective_user.id

    logger.info(f"🧹 Janitor: Оживление кнопки '{query.data}' для user={user_id}")

    # Проверка блокировки
    user_service: UserService = context.bot_data['user_service']
    user_db = await user_service.get_user(user_id)
    if user_db and user_db.status == UserStatus.BLOCKED:
        await query.answer("Ваш аккаунт заблокирован.", show_alert=True)
        return

    # Информируем пользователя
    await query.answer("Восстанавливаю меню...")

    # [правило ios] ни в коем случае не удаляем query.message здесь!
    # Мы записываем id этого мертвого сообщения в бд как главный якорь.
    # Когда функция start() пришлет новое меню, она сама удалит это старое окно.
    if query.message:
        await user_service.save_registration_message_id(user_id, query.message.message_id)

    # Перезапускаем флоу
    from tg_bot.handlers.registration import start
    return await start(update, context)
