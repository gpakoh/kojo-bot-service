# Tg_bot/ui_helpers.py
import logging
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from tg_bot.bot_services.user_service import UserService

logger = logging.getLogger(__name__)


def _handle_telegram_error(e: TelegramError, context: str) -> None:
    """Handle TelegramError with proper logging."""
    if "Message to delete not found" in str(e):
        logger.debug(f"{context}: {e}")
    elif "Message is not modified" in str(e):
        logger.debug(f"{context}: {e}")
    else:
        logger.warning(f"{context}: {e}")


async def cleanup_previous_menu(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, exclude_id: Optional[int] = None
) -> None:
    """
    Глобальный киллер старых меню и промптов.
    Удаляет якорь из БД и активный prompt_msg_id из сессии.
    """
    from tg_bot.di import get_from_context
    user_service = get_from_context(context, UserService)

    targets_to_delete = set()

    if user_service:
        user_db = await user_service.get_user(chat_id)
        if user_db and user_db.registration_message_id:
            targets_to_delete.add(user_db.registration_message_id)

    if context.user_data is None:
        return

    session_prompt = context.user_data.get('prompt_msg_id')
    if session_prompt:
        targets_to_delete.add(session_prompt)

    for msg_id in targets_to_delete:
        if msg_id == exclude_id:
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.debug(f"Cleanup: Message {msg_id} deleted.")
        except TelegramError as e:
            _handle_telegram_error(e, f"Cleanup skip for {msg_id}")
        except Exception as e:
            logger.warning(f"Cleanup unexpected error for {msg_id}: {e}")

    if not exclude_id:
        if user_service:
            await user_service.save_registration_message_id(chat_id, None)  # type: ignore[arg-type]
        context.user_data.pop('prompt_msg_id', None)

    logger.info(f"Cleanup finished for {chat_id}. Targets found: {len(targets_to_delete)}")


async def safe_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> bool:
    """Удаляет сообщение с защитой от ошибок (если уже удалено или слишком старое)."""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramError as e:
        _handle_telegram_error(e, "Safe delete")
        return False
    except Exception as e:
        logger.warning(f"Safe delete unexpected error: {e}")
        return False


async def safe_update_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = 'HTML',
    photo_path: Optional[Path] = None,
    photo_id: Optional[str] = None,
    photo_type: Optional[str] = 'photo',
    exclude_id: Optional[int] = None
) -> Optional[int]:
    """
    Универсальная функция для обновления UI с соблюдением правила iOS:
    1. Отправляем новое сообщение
    2. Удаляем старое сообщение/меню
    3. Очищаем предыдущие меню
    4. Обновляем якорь в БД
    """
    if update.effective_user is None:
        return None
    user_id = update.effective_user.id
    from tg_bot.di import get_from_context
    user_service = get_from_context(context, UserService)
    query = update.callback_query

    if photo_path:
        msg = await context.bot.send_photo(
            chat_id=user_id,
            photo=open(photo_path, 'rb'),
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    elif photo_id:
        if photo_type == "video":
            msg = await context.bot.send_video(
                chat_id=user_id,
                video=photo_id,
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif photo_type == "animation":
            msg = await context.bot.send_animation(
                chat_id=user_id,
                animation=photo_id,
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            msg = await context.bot.send_photo(
                chat_id=user_id,
                photo=photo_id,
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    else:
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    new_id = msg.message_id

    if update.message:
        try:
            await update.message.delete()
        except TelegramError as e:
            _handle_telegram_error(e, "safe_update_ui delete message")
        except Exception as e:
            logger.warning(f"safe_update_ui delete message error: {e}")

    if query and query.message:
        try:
            await query.message.delete()
        except TelegramError as e:
            _handle_telegram_error(e, "safe_update_ui delete query.message")
        except Exception as e:
            logger.warning(f"safe_update_ui delete query.message error: {e}")

    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    await user_service.save_registration_message_id(user_id, new_id)
    if context.user_data is not None:
        context.user_data['last_global_menu_id'] = new_id
    logger.info(f"UI: Rendered {new_id} for {user_id}. iOS Flush applied.")
    return new_id


async def safe_edit_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = 'HTML'
) -> Optional[int]:
    """
    Безопасное редактирование сообщения с fallback на отправку нового.
    """
    query = update.callback_query
    if not query:
        return None

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        if query.message is None:
            return None
        return query.message.message_id
    except TelegramError as e:
        _handle_telegram_error(e, "safe_edit_ui")
        return await safe_update_ui(update, context, text, reply_markup, parse_mode)
    except Exception as e:
        logger.warning(f"safe_edit_ui unexpected error: {e}")
        return await safe_update_ui(update, context, text, reply_markup, parse_mode)
