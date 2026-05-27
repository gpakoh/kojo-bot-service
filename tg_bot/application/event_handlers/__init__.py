# Tg_bot/application/event_handlers/__init__.py
"""
Event Handlers Package.

Contains handlers for domain events that perform side effects:
- Notifications (Telegram, Email)
- Search index updates
- Analytics updates
- Webhook triggers
"""
from tg_bot.application.event_handlers.order_event_handler import (
    OrderEventHandler,
    create_order_event_handler,
)

__all__ = [
    'OrderEventHandler',
    'create_order_event_handler',
]
