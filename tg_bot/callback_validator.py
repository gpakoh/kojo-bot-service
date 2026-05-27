import logging
import re
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MAX_CALLBACK_BYTES = 64

ALLOWED_PATTERN = re.compile(r'^[A-Za-z0-9_:\-.=,]+$')

DANGEROUS_SUBSTRINGS = [
    '<script', 'javascript:', 'onload=', 'onerror=', 'onclick=',
    'data:text', 'vbscript:', '&#', '\\x', 'eval(', 'expression(',
]


def validate_callback_data(data: Optional[str]) -> str:
    """
    Validate callback data for Telegram.
    Rules:
    - ≤ 64 bytes (Telegram hard limit)
    - Only alphanumeric + _ : - . = ,
    - No dangerous patterns
    """
    if not data:
        return ""

    if len(data.encode('utf-8')) > MAX_CALLBACK_BYTES:
        raise ValueError(f"Callback data exceeds {MAX_CALLBACK_BYTES} bytes: {len(data.encode('utf-8'))}")

    if not ALLOWED_PATTERN.match(data):
        raise ValueError(f"Callback data contains invalid characters: {data!r}")

    lower = data.lower()
    for bad in DANGEROUS_SUBSTRINGS:
        if bad in lower:
            raise ValueError(f"Callback data contains dangerous pattern: {bad}")

    return data


F = TypeVar('F', bound=Callable[..., Any])

def validate_callback(handler: F) -> F:
    """Decorator: validates callback_query.data before handler runs."""
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        if update.callback_query and update.callback_query.data:
            try:
                validate_callback_data(update.callback_query.data)
            except ValueError as exc:
                logger.warning(f"Invalid callback data blocked: {exc}")
                await update.callback_query.answer("⚠️ Некорректный запрос", show_alert=True)
                return None
        return await handler(update, context, *args, **kwargs)
    return wrapper  # type: ignore[return-value]
