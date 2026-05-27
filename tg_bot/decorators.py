# Tg_bot/decorators.py
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

from .bot_services.user_service import UserService
from .di import get_from_context
from .models import UserStatus
from .navigation import NavigationRegistry, ScreenType

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])

# Fallback Gate Handler (inline) If No Registry Handler Exists
async def _default_unauthorized_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Default handler for unauthorized users - shows login prompt."""
    from .handlers.common import cleanup_previous_menu

    user_id = update.effective_user.id if update.effective_user else 0
    await cleanup_previous_menu(context, user_id)

    text = "🔐 Требуется авторизация.\nНажмите /start для начала."
    await context.bot.send_message(chat_id=user_id, text=text)


def _get_gate_handler(screen_type: ScreenType, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Get gate handler from NavigationRegistry or return default."""
    registry: NavigationRegistry = context.bot_data.get('navigation_registry', NavigationRegistry())
    handler = registry.get_handler(screen_type)
    if handler:
        return handler
    return _default_unauthorized_gate

def auth_guard(staff_only: bool = False) -> Callable[[F], F]:
    """
    Декоратор доступа.
    Использует централизованный реестр UI-функций (ui_actions) для предотвращения циклических импортов.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
            user_tg = update.effective_user
            if not user_tg:
                return

            user_service = get_from_context(context, UserService)
            admin_ids: list[int] = context.bot_data.get('admin_ids', [])
            user_db = await user_service.get_user(user_tg.id)

            GUEST_ALLOWED_FUNCTIONS = [
                'start_user_order',
                'show_categories',
                'show_product_list',
                'show_product_view',
                'handle_product_image_nav',
                'show_sort_menu',
                'apply_sort',
            ]

            async def _cleanup_incoming() -> None:
                if update.message:
                    try:
                        await update.message.delete()
                    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                        logger.debug(f"Delete message failed: {e}")

            logger.info(f"[AuthGuard] User {user_tg.id} accessing '{func.__name__} (StaffOnly={staff_only})'. Status: {user_db.status if user_db else 'None'}")

            if user_db and user_db.status == UserStatus.BLOCKED:
                await _cleanup_incoming()
                gate_action = _get_gate_handler(ScreenType.MAIN_MENU, context)
                if gate_action:
                    return await gate_action(update, context)
                return

            if staff_only:
                if user_service.has_staff_privileges(user_db, admin_ids):
                    if context.user_data is not None:
                        context.user_data['is_guest'] = False
                    return await func(update, context, *args, **kwargs)
                else:
                    logger.warning(f"[AuthGuard] Access denied for {user_tg.id}: Staff only.")
                    if update.callback_query:
                        await update.callback_query.answer("🛑 Доступ только персоналу.", show_alert=True)
                    else:
                        await _cleanup_incoming()
                        from .handlers.common import cleanup_previous_menu
                        await cleanup_previous_menu(context, user_tg.id)
                        msg = await context.bot.send_message(user_tg.id, "🛑 Доступ только сотрудникам.")
                        await user_service.save_registration_message_id(user_tg.id, msg.message_id)
                    return

            if user_db and user_db.status == UserStatus.APPROVED:
                if context.user_data is not None:
                    context.user_data['is_guest'] = False
                return await func(update, context, *args, **kwargs)

            if func.__name__ in GUEST_ALLOWED_FUNCTIONS:
                logger.info(f"[AuthGuard] Allowing GUEST access for {user_tg.id} to '{func.__name__}'")
                if context.user_data is not None:
                    context.user_data['is_guest'] = True
                return await func(update, context, *args, **kwargs)

            if update.callback_query:
                try:
                    await update.callback_query.answer("Требуется регистрация.", show_alert=False)
                except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                    logger.debug(f"Callback answer failed: {e}")

            await _cleanup_incoming()
            gate_action = _get_gate_handler(ScreenType.MAIN_MENU, context)
            if gate_action:
                logger.info(f"[AuthGuard] Redirecting {user_tg.id} to Gate (Status: {user_db.status if user_db else 'Not found'}).")
                return await gate_action(update, context)
            logger.info(f"[AuthGuard] Redirecting {user_tg.id} to Gate (Status: {user_db.status if user_db else 'Not found'}).")

        return wrapper  # type: ignore[return-value]
    return decorator
