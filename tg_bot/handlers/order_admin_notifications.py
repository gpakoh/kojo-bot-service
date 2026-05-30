import logging

import telegram
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def notify_admins_about_cancelled_order(
    context: ContextTypes.DEFAULT_TYPE,
    order_id: int,
    user_id: int,
    reason: str,
    customer_name: str | None = None,
) -> None:
    admin_targets: set[int] = set()
    gen_chat_id = context.bot_data.get('admin_chat_id')
    if gen_chat_id:
        admin_targets.add(int(gen_chat_id))
    individual_ids = context.bot_data.get('admin_ids', [])
    for a_id in individual_ids:
        admin_targets.add(int(a_id))

    if not admin_targets:
        logger.warning("No admin targets configured, skipping cancellation #%s notification", order_id)
        return

    if customer_name:
        customer_line = f"<b>Клиент:</b> {customer_name}\n<b>Telegram ID:</b> {user_id}"
    else:
        customer_line = f"<b>Клиент:</b> id {user_id}"

    text = (
        f"❌ <b>Заказ #{order_id} отменён</b>\n\n"
        f"{customer_line}\n"
        f"<b>Причина:</b> {reason}"
    )

    from tg_bot.keyboards import get_admin_order_keyboard
    markup = get_admin_order_keyboard(order_id)

    for target_id in admin_targets:
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML',
            )
        except telegram.error.TelegramError as exc:
            logger.warning(
                "Failed to notify admin %s about cancellation #%s: %s",
                target_id, order_id, exc,
            )
