# Utils/retry.py
import asyncio
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from httpx import RequestError, TimeoutException
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (RequestError, TimeoutException, TelegramError, OSError),
) -> Callable[[F], F]:
    """
    Декоратор для асинхронных функций с экспоненциальной задержкой.
    Перехватывает указанные исключения и повторяет запрос с увеличением задержки.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(
                            f"❌ [{func.__name__}] All {max_attempts} attempts failed: {e}"
                        )
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(
                        f"⚠️ [{func.__name__}] Attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            return None
        return wrapper  # type: ignore[return-value]
    return decorator
