import logging

from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


ORDER_STATUS_LABELS = {
    "ACCEPTED": "принят",
    "AWAITING_PAYMENT": "ожидает оплаты",
    "PAID": "оплачен",
    "ASSEMBLING": "в обработке",
    "READY_FOR_PICKUP": "готов к выдаче",
    "SHIPPED": "передан в доставку",
    "COMPLETED": "завершён",
    "CANCELLED": "отменён",
}


async def notify_user_order_status_changed(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    order_id: int,
    new_status: str,
) -> None:
    status_label = ORDER_STATUS_LABELS.get(new_status, new_status)
    text = (
        f"🔔 Статус вашего заказа <b>#{order_id}</b> изменен на: <b>{status_label}</b>"
    )
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
        )
    except TelegramError as exc:
        logger.warning(
            "Failed to notify user %s about order %s status %s: %s",
            user_id,
            order_id,
            new_status,
            exc,
        )
