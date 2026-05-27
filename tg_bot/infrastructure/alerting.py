"""
Alerting handler: sends Telegram notification on ERROR/CRITICAL logs.
"""
import logging
from typing import Any


class TelegramAlertHandler(logging.Handler):
    """Logging handler that alerts admin chat on ERROR/CRITICAL."""
    def __init__(self, bot_token: str, admin_chat_id: str) -> None:
        super().__init__(level=logging.ERROR)
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id
        self._app: Any = None  # Will be set after bot startup

    def set_application(self, app: Any) -> None:
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        if not self._app:
            return  # Silently skip if bot not ready

        try:
            import asyncio
            message = self._format_alert(record)
            # Fire-and-forget To Not Block Logging
            asyncio.create_task(self._send(message))
        except (RuntimeError, ConnectionError, TimeoutError, OSError):
            self.handleError(record)

    def _format_alert(self, record: logging.LogRecord) -> str:
        emoji = "🔥" if record.levelname == "CRITICAL" else "⚠️"
        return (
            f"{emoji} <b>{record.levelname}</b> in <code>{record.name}</code>\n"
            f"<pre>{record.getMessage()[:400]}</pre>\n"
            f"Module: {record.module}:{record.lineno}"
        )

    async def _send(self, message: str) -> None:
        try:
            await self._app.bot.send_message(
                chat_id=self.admin_chat_id,
                text=message,
                parse_mode="HTML",
            )
        except (RuntimeError, ConnectionError, TimeoutError, OSError):
            # Don't Loop On Logging Errors
            pass


def setup_alerting(app: Any) -> None:
    """Attach Telegram alert handler to root logger."""
    from tg_bot.infrastructure.secrets_loader import get_secret
    token = get_secret("BOT_TOKEN")
    admin_id = get_secret("ADMIN_CHAT_ID")

    if not token or not admin_id:
        logging.warning("Alerting not configured: BOT_TOKEN or ADMIN_CHAT_ID missing")
        return

    handler = TelegramAlertHandler(token, admin_id)
    handler.set_application(app)
    logging.getLogger().addHandler(handler)
    logging.info("Telegram alerting enabled for ERROR/CRITICAL")
