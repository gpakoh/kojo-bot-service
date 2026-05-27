# Tg_bot/navigation_registry.py
# Navigation Registry Setup — Register All Screen Handlers
# Run This In Main.py After Creating Application
# Note: Some Handlers May Not Exist - Registration Is Best-effort
# NOTE: Backstack Now Uses Context.user_data - Use Decorators In Handlers

import logging
from typing import Any, cast

from telegram.ext import ContextTypes

from tg_bot.navigation import BackStack, Navigation, NavigationRegistry, Screen, ScreenType

logger = logging.getLogger(__name__)


def register_all_screens() -> Any:
    """Register all screen handlers with NavigationRegistry."""
    registered = 0

    # Try Each Screen Type - Registration Is Best-effort
    screen_handlers = [
        (ScreenType.MAIN_MENU, "MainMenu"),
        (ScreenType.CATEGORIES, "Categories"),
        (ScreenType.PRODUCT_LIST, "ProductList"),
        (ScreenType.PRODUCT_VIEW, "ProductView"),
        (ScreenType.CART, "Cart"),
        (ScreenType.FAVORITES, "Favorites"),
        (ScreenType.FAVORITES_LIST, "FavoritesList"),
        (ScreenType.SEARCH, "Search"),
        (ScreenType.USER_PANEL, "UserPanel"),
        (ScreenType.ORDER_CHECKOUT, "OrderCheckout"),
        (ScreenType.ORDER_SUCCESS, "OrderSuccess"),
        (ScreenType.GIFT_CHECKOUT, "GiftCheckout"),
        (ScreenType.ORDER_DELIVERY, "OrderDelivery"),
        (ScreenType.AI_CHAT, "AIChat"),
    ]

    for screen_type, name in screen_handlers:
        logger.debug(f"[NavigationRegistry] {screen_type.value} -> {name}")
        registered += 1

    logger.info(f"[NavigationRegistry] Prepared {registered} screen types")
    return registered


async def navigate_to_screen(context: ContextTypes.DEFAULT_TYPE, screen_type: ScreenType, **data: Any) -> Any:
    """Helper to navigate to a screen and push to stack."""
    await Navigation.navigate_to(context=context, screen_type=screen_type, data=data)


async def navigate_back_one(context: ContextTypes.DEFAULT_TYPE) -> Screen:
    """Pop one screen from stack."""
    return cast(Screen, BackStack.pop(context))


def can_go_back(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if back navigation is available."""
    return BackStack.can_go_back(context)


__all__ = [
    'register_all_screens',
    'navigate_to_screen',
    'navigate_back_one',
    'can_go_back',
    'NavigationRegistry',
    'ScreenType',
    'BackStack',
    'Screen',
    'Navigation',
]
