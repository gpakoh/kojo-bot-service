from typing import Any, Optional

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from tg_bot.bot_services.info_service import InfoService
from tg_bot.keyboards import (
    CB_INFO_MENU,
    CB_PREFIX_INFO_GO,
    CB_USER_SHOW_MAIN_MENU,
    get_cms_keyboard,
)

import logging
logger = logging.getLogger(__name__)


async def _check_is_staff(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    from tg_bot.models import UserRole
    user_service = context.bot_data.get('user_service')
    if not user_service:
        return False
    user = await user_service.get_user(user_id)
    return user is not None and user.role in (UserRole.ADMIN, UserRole.MANAGER)


def _resolve_navigation(query: Any, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    page_id = None
    is_explicit = False

    if query and (query.data == CB_INFO_MENU or query.data == f"{CB_PREFIX_INFO_GO}root"):
        page_id = None
        is_explicit = True
        context.user_data.pop('cms_current_view_id', None)

    elif query and query.data.startswith(CB_PREFIX_INFO_GO):
        val = query.data.replace(CB_PREFIX_INFO_GO, '')
        if val != 'None' and val != 'root':
            try:
                page_id = int(val)
                is_explicit = True
            except (ValueError, TypeError):
                pass

    if is_explicit:
        if page_id is not None:
            context.user_data['cms_current_view_id'] = page_id
    else:
        page_id = context.user_data.get('cms_current_view_id')

    return page_id


async def _render_page_content(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    image_id: Optional[str],
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Умная логика отправки сообщения. Строгое соблюдение 'Правила iOS' (сначала Send, потом Delete)."""
    if update.effective_user is None:
        return
    if update.effective_chat is None:
        return

    query = update.callback_query
    has_old_photo = bool(query and query.message and query.message.photo)
    is_long_text = len(text) > 1000
    user_id = update.effective_user.id
    user_service = context.bot_data.get('user_service')

    stale_photo_id = context.user_data.pop('cms_last_photo_msg_id', None)

    if image_id and is_long_text:
        photo_msg = await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_id)
        context.user_data['cms_last_photo_msg_id'] = photo_msg.message_id

        text_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

        context.user_data['last_global_menu_id'] = text_msg.message_id
        if user_service:
            await user_service.save_registration_message_id(user_id, text_msg.message_id)

        if query and query.message:
            try:
                await query.message.delete()
            except (ValueError, KeyError, telegram.error.TelegramError):
                pass
        if stale_photo_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=stale_photo_id)
            except (ValueError, KeyError, telegram.error.TelegramError):
                pass

    elif image_id:
        if has_old_photo:
            media = InputMediaPhoto(media=image_id, caption=text[:1024], parse_mode=ParseMode.HTML)
            await query.edit_message_media(media=media, reply_markup=reply_markup)

            if stale_photo_id:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=stale_photo_id)
                except (ValueError, KeyError, telegram.error.TelegramError):
                    pass
        else:
            photo_msg = await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=image_id,
                caption=text[:1024],
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

            context.user_data['last_global_menu_id'] = photo_msg.message_id
            if user_service:
                await user_service.save_registration_message_id(user_id, photo_msg.message_id)

            if query and query.message:
                try:
                    await query.message.delete()
                except (ValueError, KeyError, telegram.error.TelegramError):
                    pass
            if stale_photo_id:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=stale_photo_id)
                except (ValueError, KeyError, telegram.error.TelegramError):
                    pass

    else:
        if has_old_photo:
            text_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )

            context.user_data['last_global_menu_id'] = text_msg.message_id
            if user_service:
                await user_service.save_registration_message_id(user_id, text_msg.message_id)

            if query and query.message:
                try:
                    await query.message.delete()
                except (ValueError, KeyError, telegram.error.TelegramError):
                    pass
            if stale_photo_id:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=stale_photo_id)
                except (ValueError, KeyError, telegram.error.TelegramError):
                    pass
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            except (ValueError, KeyError, telegram.error.TelegramError):
                pass

            if stale_photo_id:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=stale_photo_id)
                except (ValueError, KeyError, telegram.error.TelegramError):
                    pass


async def show_info_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает корневое меню информационных страниц или список страниц."""
    if update.effective_user is None:
        return
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    if context.user_data is None:
        context.user_data = {}

    page_id = _resolve_navigation(query, context)

    info_service: InfoService = context.bot_data['info_service']
    is_staff = await _check_is_staff(context, update.effective_user.id)

    current_page = await info_service.get_page(page_id) if page_id else None
    children = await info_service.get_children(page_id)
    parent_id = current_page['parent_id'] if current_page else None

    text = ""
    if current_page:
        title = current_page['title']
        body = current_page.get('body_text')
        text = f"📂 <b>{title}</b>\n\n"
        if body:
            text += f"{body}"
    else:
        if children:
            text = "ℹ️ <b>О нас / Информация</b>\nВыберите пункт:"
        else:
            text = "ℹ️ <b>Информационные страницы пока не добавлены.</b>"

    reply_markup = get_cms_keyboard(children, page_id, parent_id, is_staff)
    image_id = current_page['image_id'] if current_page else None

    try:
        await _render_page_content(update, context, text, image_id, reply_markup)
    except (ValueError, KeyError, telegram.error.TelegramError) as e:
        logger.error(f"CMS Render Error: {e}")
        safe_text = text + "\n\n⚠️ <b>Ошибка отображения (HTML)</b>. Проверьте теги."
        try:
            if image_id:
                msg = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_id,
                    caption=safe_text[:1024],
                    reply_markup=reply_markup
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=safe_text,
                    reply_markup=reply_markup
                )

            context.user_data['last_global_menu_id'] = msg.message_id
            user_service = context.bot_data.get('user_service')
            if user_service:
                await user_service.save_registration_message_id(update.effective_user.id, msg.message_id)

            if query and query.message:
                await query.message.delete()
        except (ValueError, KeyError, telegram.error.TelegramError) as e2:
            logger.error(f"CMS Critical Fallback Error: {e2}")
