import html
import logging
from typing import Any, Optional

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tg_bot.bot_services.info_service import InfoService
from tg_bot.decorators import auth_guard
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.keyboards import (
    CB_CMS_ITEM_OPTS,
    CB_CMS_MOVE_DOWN,
    CB_CMS_MOVE_UP,
    CB_CMS_RENAME,
    CB_EDIT_CONTENT,
    CB_EDIT_ORDER,
    CB_EDIT_TITLE,
    CB_INFO_MENU,
    CB_PREFIX_INFO_ADD,
    CB_PREFIX_INFO_DEL,
    CB_PREFIX_INFO_EDIT,
    CB_PREFIX_INFO_GO,
    get_cms_item_options_keyboard,
    get_cms_keyboard,
)

logger = logging.getLogger(__name__)

AWAITING_TITLE, AWAITING_RENAME, AWAITING_ORDER, AWAITING_CONTENT = range(4)


async def _check_is_staff(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    from tg_bot.models import UserRole
    user_service = context.bot_data.get('user_service')
    if not user_service:
        return False
    user = await user_service.get_user(user_id)
    return user is not None and user.role in (UserRole.ADMIN, UserRole.MANAGER)


def _resolve_navigation(query: Any, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    if context.user_data is None:
        return None
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

    if context.user_data is None:
        return

    query = update.callback_query
    if query is None:
        return
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
            try:
                await query.edit_message_media(media=media, reply_markup=reply_markup)
            except (ValueError, KeyError, telegram.error.TelegramError) as exc:
                logger.warning("Failed to edit media in _render_page_content: %s", exc)
                photo_msg = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_id,
                    caption=text[:1024],
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
                context.user_data['last_global_menu_id'] = photo_msg.message_id
                if user_service:
                    await user_service.save_registration_message_id(user_id, photo_msg.message_id)
                if query and query.message:
                    try:
                        await query.message.delete()
                    except (ValueError, KeyError, telegram.error.TelegramError):
                        pass
                await cleanup_previous_menu(context, update.effective_chat.id, exclude_id=photo_msg.message_id)

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
            except (ValueError, KeyError, telegram.error.TelegramError) as exc:
                logger.warning("Failed to edit text in _render_page_content: %s", exc)
                message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                context.user_data['last_global_menu_id'] = message.message_id
                if user_service:
                    await user_service.save_registration_message_id(user_id, message.message_id)
                await cleanup_previous_menu(context, update.effective_chat.id, exclude_id=message.message_id)

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
    if update.effective_chat is None:
        return

    page_id = _resolve_navigation(query, context)

    info_service: InfoService = context.bot_data['info_service']
    is_staff = await _check_is_staff(context, update.effective_user.id)
    edit_mode = bool(context.user_data.get("info_edit_mode"))

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

    reply_markup = get_cms_keyboard(children, page_id, parent_id, is_staff, edit_mode)
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


def _parse_item_id(callback_data: str, prefix: str) -> int | None:
    if callback_data.startswith(prefix):
        val = callback_data.replace(prefix, "")
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return None


@auth_guard(staff_only=True)
async def return_to_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data is None:
        return
    context.user_data.pop("info_edit_mode", None)
    context.user_data.pop("cms_page_id", None)
    context.user_data.pop("cms_parent_id", None)
    await show_info_menu(update, context)


@auth_guard(staff_only=True)
async def toggle_edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data is None:
        return
    current = bool(context.user_data.get("info_edit_mode"))
    context.user_data["info_edit_mode"] = not current
    await show_info_menu(update, context)


@auth_guard(staff_only=True)
async def show_item_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    if query.data is None:
        await show_info_menu(update, context)
        return
    item_id = _parse_item_id(query.data, CB_CMS_ITEM_OPTS)
    if item_id is None:
        await show_info_menu(update, context)
        return

    info_service: InfoService = context.bot_data["info_service"]
    page = await info_service.get_page(item_id)
    if not page:
        await show_info_menu(update, context)
        return

    parent_id = page.get("parent_id")
    children = await info_service.get_children(parent_id)

    lines = []
    for child in children:
        if child["id"] == item_id:
            lines.append(f"👉 <b>{child['title']}</b>")
        else:
            lines.append(f"   {child['title']}")

    text = (
        f"⚙️ Настройка пункта: <b>{page['title']}</b>\n\n"
        f"📋 <b>Текущий порядок:</b>\n"
        + "\n".join(lines)
        + "\n\nИспользуйте стрелки, чтобы переместить пункт:"
    )

    reply_markup = get_cms_item_options_keyboard(item_id, parent_id)

    try:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass


@auth_guard(staff_only=True)
async def move_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    callback_data = query.data
    item_id = None
    direction = None
    if CB_CMS_MOVE_UP in callback_data:
        item_id = _parse_item_id(callback_data, CB_CMS_MOVE_UP)
        direction = "up"
    elif CB_CMS_MOVE_DOWN in callback_data:
        item_id = _parse_item_id(callback_data, CB_CMS_MOVE_DOWN)
        direction = "down"

    if item_id is None or direction is None:
        return

    info_service: InfoService = context.bot_data["info_service"]
    await info_service.move_page(item_id, direction)
    await show_item_options(update, context)


@auth_guard(staff_only=True)
async def delete_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    page_id = _parse_item_id(query.data, CB_PREFIX_INFO_DEL)
    if page_id is None:
        await show_info_menu(update, context)
        return ConversationHandler.END

    info_service: InfoService = context.bot_data["info_service"]
    await info_service.delete_page(page_id)

    await show_info_menu(update, context)
    return ConversationHandler.END


@auth_guard(staff_only=True)
async def start_edit_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    page_id = _parse_item_id(query.data, CB_PREFIX_INFO_EDIT)
    if page_id is None:
        await show_info_menu(update, context)
        return ConversationHandler.END

    if context.user_data is None:
        return ConversationHandler.END
    context.user_data["cms_page_id"] = page_id

    info_service: InfoService = context.bot_data["info_service"]
    page = await info_service.get_page(page_id)
    if not page:
        await show_info_menu(update, context)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🅰️ Изменить название", callback_data=CB_EDIT_TITLE)],
        [InlineKeyboardButton("📝 Изменить содержимое", callback_data=CB_EDIT_CONTENT)],
        [InlineKeyboardButton("🔢 Изменить порядок", callback_data=CB_EDIT_ORDER)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"{CB_PREFIX_INFO_GO}{page.get('parent_id')}" if page.get('parent_id') else CB_INFO_MENU)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            f"✏️ Редактирование: <b>{page['title']}</b>\n\nЧто вы хотите изменить?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    return ConversationHandler.END


@auth_guard(staff_only=True)
async def ask_edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END

    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    context.user_data["cms_action"] = "edit_title"

    if query and query.message:
        try:
            await query.message.reply_text(
                "🅰️ Введите новое название страницы.\n"
                "Или /cancel, чтобы отменить.",
            )
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    return AWAITING_RENAME


@auth_guard(staff_only=True)
async def start_quick_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END

    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    page_id = _parse_item_id(query.data, CB_CMS_RENAME)
    if page_id is not None:
        context.user_data["cms_page_id"] = page_id
    context.user_data["cms_action"] = "edit_title"

    if query.message:
        try:
            await query.message.reply_text(
                "🅰️ Введите новое название страницы.\n"
                "Или /cancel, чтобы отменить.",
            )
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    return AWAITING_RENAME


@auth_guard(staff_only=True)
async def ask_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    context.user_data["cms_action"] = "edit_content"

    page_id: Optional[int] = context.user_data.get("cms_page_id")
    if page_id is None:
        if query and query.message:
            try:
                await query.message.reply_text("Ошибка: страница не выбрана.")
            except (ValueError, KeyError, telegram.error.TelegramError):
                pass
        return ConversationHandler.END

    info_service: InfoService = context.bot_data["info_service"]
    page = await info_service.get_page(page_id)
    current_content = page.get("body_text") if page else ""

    safe_content = html.escape(html.unescape(current_content or ""))
    truncated = safe_content[:200] + "…" if len(safe_content) > 200 else safe_content or "пусто"

    if query and query.message:
        try:
            await query.message.reply_text(
                f"📝 Текущее содержимое:\n<code>{truncated}</code>\n\n"
                "Отправьте новый текст или фото с подписью.\n"
                "/skip — оставить текст пустым\n"
                "/del_photo — удалить фото\n"
                "/cancel — отменить",
                parse_mode=ParseMode.HTML,
            )
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    return AWAITING_CONTENT


async def ask_edit_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    context.user_data["cms_action"] = "edit_order"

    if query and query.message:
        try:
            await query.message.reply_text(
                "🔢 Введите новый порядковый номер (целое число).\n"
                "Или /cancel, чтобы отменить.",
            )
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    return AWAITING_ORDER


@auth_guard(staff_only=True)
async def handle_rename_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    message = update.message
    if message is None:
        return ConversationHandler.END
    text = message.text or ""
    if not text:
        await message.reply_text("Название не может быть пустым. Попробуйте ещё раз:")
        return AWAITING_RENAME

    if len(text) > 100:
        await message.reply_text(
            f"❌ Слишком длинное название ({len(text)} симв.). Максимум 100. Попробуйте короче:"
        )
        return AWAITING_RENAME

    info_service: InfoService = context.bot_data["info_service"]
    page_id = context.user_data.get("cms_page_id")

    if page_id is None:
        await message.reply_text("Ошибка: страница не выбрана.")
        return ConversationHandler.END

    await info_service.update_page_title(page_id, text)

    for key in ("cms_action", "cms_page_id"):
        context.user_data.pop(key, None)

    await message.reply_text(
        "✅ Название обновлено!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Вернуться к списку", callback_data=CB_INFO_MENU)]
        ]),
    )

    return ConversationHandler.END


@auth_guard(staff_only=True)
async def handle_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    message = update.message
    if message is None:
        return ConversationHandler.END
    text = message.text or ""
    try:
        order = int(text)
    except (ValueError, TypeError):
        await message.reply_text("❌ Введите целое число. Попробуйте ещё раз:")
        return AWAITING_ORDER

    info_service: InfoService = context.bot_data["info_service"]
    page_id = context.user_data.get("cms_page_id")

    if page_id is None:
        await message.reply_text("Ошибка: страница не выбрана.")
        return ConversationHandler.END

    await info_service.update_page_order(page_id, order)

    for key in ("cms_action", "cms_page_id"):
        context.user_data.pop(key, None)

    await message.reply_text(
        "✅ Порядок обновлён!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Вернуться к списку", callback_data=CB_INFO_MENU)]
        ]),
    )

    return ConversationHandler.END


@auth_guard(staff_only=True)
async def cancel_cms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    for key in ("cms_action", "cms_title", "cms_parent_id", "cms_page_id"):
        context.user_data.pop(key, None)

    if update.message:
        await update.message.reply_text("Действие отменено.")
    elif update.callback_query:
        await update.callback_query.answer("Действие отменено", show_alert=True)

    return ConversationHandler.END


@auth_guard(staff_only=True)
async def start_add_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    try:
        await query.answer()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    data = query.data.replace(CB_PREFIX_INFO_ADD, "")
    parent_id = int(data) if data != "root" else None
    context.user_data["cms_action"] = "create"
    context.user_data["cms_parent_id"] = parent_id

    if query.message:
        try:
            await query.message.reply_text(
                "🆕 Введите название новой страницы.\n"
                "Или /cancel, чтобы отменить.",
            )
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    return AWAITING_TITLE


@auth_guard(staff_only=True)
async def handle_title_creation_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    message = update.message
    if message is None:
        return ConversationHandler.END
    text = message.text or ""
    if not text:
        await message.reply_text("Название не может быть пустым. Попробуйте ещё раз:")
        return AWAITING_TITLE

    if len(text) > 100:
        await message.reply_text(
            f"❌ Слишком длинное название ({len(text)} симв.). Максимум 100. Попробуйте короче:"
        )
        return AWAITING_TITLE

    context.user_data["cms_title"] = text

    await message.reply_text(
        f"Название: <b>{text}</b>.\n\n"
        "Теперь отправьте содержимое страницы.\n\n"
        "Можно отправить:\n"
        "• текст;\n"
        "• фото с подписью;\n"
        "• /skip — создать страницу без содержимого.",
        parse_mode=ParseMode.HTML,
    )

    return AWAITING_CONTENT


@auth_guard(staff_only=True)
async def handle_content_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is None:
        return ConversationHandler.END
    message = update.message
    if message is None:
        return ConversationHandler.END

    action = context.user_data.get("cms_action")

    try:
        await message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    info_service: InfoService = context.bot_data["info_service"]

    if action == "create":
        title = context.user_data.get("cms_title", "Без названия")
        parent_id = context.user_data.get("cms_parent_id")

        content = None
        photo = None

        if message.text == "/skip":
            content = None
            photo = None
        elif message.photo:
            photo = message.photo[-1].file_id
            content = message.caption or ""
        else:
            content = message.text or ""
            photo = None

        await info_service.create_page(parent_id, title, content, photo)

        for key in ("cms_action", "cms_title", "cms_parent_id"):
            context.user_data.pop(key, None)

        await message.reply_text(
            "✅ Страница создана!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Вернуться к списку", callback_data=CB_INFO_MENU)]
            ]),
        )

    elif action == "edit_content":
        page_id = context.user_data.get("cms_page_id")
        if page_id is None:
            await message.reply_text("Ошибка: страница не выбрана.")
            return ConversationHandler.END

        current_page = await info_service.get_page(page_id)
        existing_image = current_page.get("image_id") if current_page else None

        new_text = None
        new_image = None

        if message.text == "/skip":
            new_text = ""
            new_image = existing_image
        elif message.text == "/del_photo":
            new_text = current_page.get("body_text") if current_page else ""
            new_image = None
        elif message.photo:
            new_image = message.photo[-1].file_id
            new_text = message.caption or ""
        else:
            new_text = message.text or ""
            new_image = existing_image

        await info_service.update_page_content(page_id, new_text, new_image)

        for key in ("cms_action", "cms_page_id"):
            context.user_data.pop(key, None)

        await message.reply_text(
            "✅ Содержимое обновлено!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Вернуться к списку", callback_data=CB_INFO_MENU)]
            ]),
        )

    else:
        await message.reply_text("Сценарий не активен.")
        return ConversationHandler.END

    return ConversationHandler.END


info_cms_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_add_page, pattern=f"^{CB_PREFIX_INFO_ADD}"),
        CallbackQueryHandler(start_edit_page, pattern=f"^{CB_PREFIX_INFO_EDIT}"),
        CallbackQueryHandler(ask_edit_title, pattern=f"^{CB_EDIT_TITLE}$"),
        CallbackQueryHandler(ask_edit_content, pattern=f"^{CB_EDIT_CONTENT}$"),
        CallbackQueryHandler(ask_edit_order, pattern=f"^{CB_EDIT_ORDER}$"),
        CallbackQueryHandler(start_quick_rename, pattern=f"^{CB_CMS_RENAME}"),
        CallbackQueryHandler(delete_page_handler, pattern=f"^{CB_PREFIX_INFO_DEL}"),
    ],
    states={
        AWAITING_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_creation_input),
        ],
        AWAITING_RENAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rename_input),
        ],
        AWAITING_ORDER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_input),
        ],
        AWAITING_CONTENT: [
            MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_content_input),
            CommandHandler("skip", handle_content_input),
            CommandHandler("del_photo", handle_content_input),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_cms),
    ],
    name="info_cms_conversation",
    persistent=False,
)
