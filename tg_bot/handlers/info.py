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
from tg_bot.keyboards import (
    CB_INFO_MENU,
    CB_PREFIX_INFO_GO,
    CB_PREFIX_INFO_ADD,
    CB_USER_SHOW_MAIN_MENU,
    CB_CMS_MODE_TOGGLE,
    CB_CMS_ITEM_OPTS,
    CB_CMS_MOVE_UP,
    CB_CMS_MOVE_DOWN,
    get_cms_item_options_keyboard,
    get_cms_keyboard,
)
from tg_bot.decorators import auth_guard

import logging
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
    context.user_data.pop("info_edit_mode", None)
    context.user_data.pop("cms_page_id", None)
    context.user_data.pop("cms_parent_id", None)
    await show_info_menu(update, context)


@auth_guard(staff_only=True)
async def toggle_edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = bool(context.user_data.get("info_edit_mode"))
    context.user_data["info_edit_mode"] = not current
    await show_info_menu(update, context)


@auth_guard(staff_only=True)
async def show_item_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None:
        return
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    item_id = _parse_item_id(query.data, CB_CMS_ITEM_OPTS) if query else None
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
    if update.effective_user is None:
        return
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    callback_data = query.data if query else ""
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
async def cancel_cms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in ("cms_action", "cms_title", "cms_parent_id", "cms_page_id"):
        context.user_data.pop(key, None)

    if update.message:
        await update.message.reply_text("Действие отменено.")
    elif update.callback_query:
        await update.callback_query.answer("Действие отменено", show_alert=True)

    return ConversationHandler.END


@auth_guard(staff_only=True)
async def start_add_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None:
        return ConversationHandler.END
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except (ValueError, KeyError, telegram.error.TelegramError):
            pass

    data = query.data.replace(CB_PREFIX_INFO_ADD, "") if query else "root"
    parent_id = int(data) if data != "root" else None
    context.user_data["cms_action"] = "create"
    context.user_data["cms_parent_id"] = parent_id

    if query:
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
    text = update.message.text if update.message else ""
    if not text:
        await update.message.reply_text("Название не может быть пустым. Попробуйте ещё раз:")
        return AWAITING_TITLE

    if len(text) > 100:
        await update.message.reply_text(
            f"❌ Слишком длинное название ({len(text)} симв.). Максимум 100. Попробуйте короче:"
        )
        return AWAITING_TITLE

    context.user_data["cms_title"] = text

    await update.message.reply_text(
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
    action = context.user_data.get("cms_action")
    if action != "create":
        await update.message.reply_text("Сценарий редактирования пока не активен.")
        return ConversationHandler.END

    try:
        await update.message.delete()
    except (ValueError, KeyError, telegram.error.TelegramError):
        pass

    info_service: InfoService = context.bot_data["info_service"]
    title = context.user_data.get("cms_title", "Без названия")
    parent_id = context.user_data.get("cms_parent_id")

    content = None
    photo = None

    if update.message.text == "/skip":
        content = None
        photo = None
    elif update.message.photo:
        photo = update.message.photo[-1].file_id
        content = update.message.caption or ""
    else:
        content = update.message.text or ""
        photo = None

    await info_service.create_page(parent_id, title, content, photo)

    for key in ("cms_action", "cms_title", "cms_parent_id"):
        context.user_data.pop(key, None)

    await update.message.reply_text(
        "✅ Страница создана!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Вернуться к списку", callback_data=CB_INFO_MENU)]
        ]),
    )

    return ConversationHandler.END


info_cms_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_add_page, pattern=f"^{CB_PREFIX_INFO_ADD}"),
    ],
    states={
        AWAITING_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_creation_input),
        ],
        AWAITING_CONTENT: [
            MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_content_input),
            CommandHandler("skip", handle_content_input),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_cms),
    ],
    name="info_cms_conversation",
    persistent=False,
)
