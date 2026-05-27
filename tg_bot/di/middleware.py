# Tg_bot/di/middleware.py
import logging

from telegram import Update
from telegram.ext import Application, ContextTypes

from tg_bot.di.provider import get_container

logger = logging.getLogger(__name__)


def inject_di(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Inject Container into context before each handler execution.

    This is called by Telegram's before_process_update hook.
    It makes the container available via context.di in all handlers.

    Note: We inject the same container instance to all contexts.
    This is appropriate because Container is thread-safe for reading services.
    """
    try:
        container = get_container()
        context.di = container  # type: ignore[attr-defined]
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"DI injection failed: {e}")


def register_di_middleware(application: Application) -> None:
    """
    Register DI injection via before_process_update hook (PTB 20+ compatible).

    Call this in main.py after building the application:
        register_di_middleware(application)
    """
    application.before_process_update(inject_di)  # type: ignore[attr-defined]
    logger.info("DI Middleware Registered Via Before_process_update")


__all__ = ['inject_di', 'register_di_middleware', 'get_container']
