# Tg_bot/factories/bot_factory.py
import asyncio
import logging
import os
from typing import Any, Optional

from telegram.ext import Application, BasePersistence
from telegram.request import HTTPXRequest

logger = logging.getLogger(__name__)


class BotFactory:
    """Factory for creating and configuring Telegram bot application."""

    def __init__(self, token: str) -> None:
        self.token = token
        self._proxy_url: Optional[str] = None

    def _resolve_proxy_url(self) -> Optional[str]:
        """Resolve proxy URL from environment or proxy pool."""
        use_proxy = os.environ.get("USE_PROXY", "false").lower() == "true"
        env_proxy_url = os.environ.get("TG_PROXY_URL")

        if not use_proxy:
            logger.info("🌐 [direct start] прокси выключен в конфиге (use_proxy: false).")
            return None

        if env_proxy_url:
            logger.info(f"🌐 [PROXY ENV] Бот запускается через прокси: {env_proxy_url}")
            return env_proxy_url

        try:
            from services.proxy_adapter import get_proxy_adapter
            bot_id = os.environ.get("BOT_ID_FOR_QUART", "default")
            adapter = get_proxy_adapter(bot_id)
            selected = asyncio.run(adapter.async_set_proxy())
            if selected:
                logger.info(f"🌐 [PROXY POOL] Выбран прокси из пула: {selected.url}")
                return selected.url
            else:
                logger.warning("⚠️ use_proxy=true, но пул не дал доступных прокси. иду напрямую.")
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"⚠️ Ошибка при выборке прокси (startup): {e}. Иду напрямую.")

        return None

    def create_request(self) -> HTTPXRequest:
        """Create HTTPXRequest with proxy configuration."""
        self._proxy_url = self._resolve_proxy_url()

        return HTTPXRequest(
            connection_pool_size=20,
            connect_timeout=30.0,
            read_timeout=180.0,
            write_timeout=180.0,
            proxy=self._proxy_url,
        )

    def create_application(
        self,
        request: HTTPXRequest,
        persistence: BasePersistence,
        post_init: Optional[Any] = None,
        post_shutdown: Optional[Any] = None,
    ) -> Application:
        """Create and configure the Application."""
        builder = (
            Application.builder()
            .token(self.token)
            .request(request)
            .persistence(persistence)
        )

        if post_init:
            builder = builder.post_init(post_init)
        if post_shutdown:
            builder = builder.post_shutdown(post_shutdown)

        return builder.build()

    @property
    def proxy_url(self) -> Optional[str]:
        """Return resolved proxy URL for external use."""
        return self._proxy_url


def create_bot_factory(token: str) -> BotFactory:
    """Factory function to create BotFactory instance."""
    return BotFactory(token)
