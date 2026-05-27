import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from tg_bot.core.fsm_router import FSMRouter
from tg_bot.core.state_manager import BotState
from tg_bot.di import get_from_context

logger = logging.getLogger(__name__)

COMMAND_TO_STATE = {
    "menu": BotState.BROWSE_CATEGORIES,
}

CALLBACK_TO_STATE = {
    "user_start_ordering": BotState.BROWSE_CATEGORIES,
    "cb_user_start_ordering": BotState.BROWSE_CATEGORIES,
    "staff_make_order": BotState.BROWSE_CATEGORIES,
    "cb_staff_make_order": BotState.BROWSE_CATEGORIES,
    "view_cart": BotState.CART,
    "cb_view_cart": BotState.CART,
    "favorites_menu": BotState.FAVORITES,
    "cb_favorites_menu": BotState.FAVORITES,
    "search_products": BotState.BROWSE_PRODUCTS,
    "cb_search_products": BotState.BROWSE_PRODUCTS,
    "fav_recipes_list": BotState.BROWSE_PRODUCTS,
    "cb_fav_recipes_list": BotState.BROWSE_PRODUCTS,
    "user_show_main_menu": BotState.BROWSE_CATEGORIES,
    "cb_user_show_main_menu": BotState.BROWSE_CATEGORIES,
    "back_to_categories": BotState.BROWSE_CATEGORIES,
    "cb_back_to_categories": BotState.BROWSE_CATEGORIES,
    "back_to_product_list": BotState.BROWSE_PRODUCTS,
    "cb_back_to_product_list": BotState.BROWSE_PRODUCTS,
    "edit_cart": BotState.CART,
    "cb_edit_cart": BotState.CART,
    "checkout": BotState.CHECKOUT,
    "cb_checkout": BotState.CHECKOUT,
    "user_panel": BotState.USER_PANEL,
    "cb_user_panel": BotState.USER_PANEL,
    "ai_chat": BotState.AI_CHAT,
    "cb_ai_chat": BotState.AI_CHAT,
    "registration_start": BotState.REGISTRATION,
    "cb_registration_start": BotState.REGISTRATION,
    "user_my_orders": BotState.USER_PANEL,
    "cb_user_my_orders": BotState.USER_PANEL,
    "user_settings": BotState.USER_PANEL,
    "cb_user_settings": BotState.USER_PANEL,
    "user_addresses": BotState.USER_PANEL,
    "cb_user_addresses": BotState.USER_PANEL,
    "user_logout_menu": BotState.USER_PANEL,
    "cb_user_logout_menu": BotState.USER_PANEL,
}

CALLBACK_PREFIX_TO_STATE = {
    "cb_sel_cat_": BotState.BROWSE_PRODUCTS,
    "cb_cat_list_": BotState.BROWSE_PRODUCTS,
    "cb_sel_prod_": BotState.VIEW_PRODUCT,
    "cb_product_": BotState.VIEW_PRODUCT,
    "cb_fav_prod_list": BotState.FAVORITES,
    "cb_ord_details_": BotState.USER_PANEL,
    "cb_ord_action_": BotState.USER_PANEL,
    "cb_approve_": BotState.REGISTRATION,
    "cb_decline_": BotState.REGISTRATION,
}


class FSMRouteHandler:
    """Handler that routes to FSM state instead of direct callbacks."""

    def _get_router(self, context: ContextTypes.DEFAULT_TYPE) -> Any:
        """Get router from DI (context.di)."""
        from tg_bot.core.fsm_router import FSMRouter
        from tg_bot.di import get_from_context
        return get_from_context(context, FSMRouter)

    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /menu and other commands."""
        if not update.message:
            return

        text = update.message.text
        if text is None:
            return
        command = text.lstrip("/").split()[0]
        target_state = COMMAND_TO_STATE.get(command)

        if target_state:
            logger.info(f"FSM Route: /{command} -> {target_state.value}")
            router = self._get_router(context)
            await router.navigate_to(update, context, target_state)
        else:
            logger.debug(f"FSM Route: unknown command /{command}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callbacks via FSM."""
        query = update.callback_query
        if not query:
            return

        await query.answer()

        data = query.data
        target_state: BotState | None = None

        if data is not None:
            if data in CALLBACK_TO_STATE:
                target_state = CALLBACK_TO_STATE[data]
            else:
                for prefix, state in CALLBACK_PREFIX_TO_STATE.items():
                    if data.startswith(prefix):
                        target_state = state
                        break

        display_data = (data or "")[:30]
        if target_state:
            logger.info(f"FSM Route: callback {display_data} -> {target_state.value}")
            router = self._get_router(context)
            await router.navigate_to(update, context, target_state)
        else:
            logger.debug(f"FSM Route: unhandled callback {display_data}")


def register_fsm_routes(application: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register FSM-based route handlers."""
    handler = FSMRouteHandler()

    application.add_handler(
        CommandHandler("menu", handler.handle_command),
        group=1
    )

    for callback_pattern in CALLBACK_TO_STATE.keys():
        application.add_handler(
            CallbackQueryHandler(handler.handle_callback, pattern=f"^{callback_pattern}$"),
            group=1
        )

    for prefix in CALLBACK_PREFIX_TO_STATE.keys():
        application.add_handler(
            CallbackQueryHandler(handler.handle_callback, pattern=f"^{prefix}"),
            group=1
        )

    logger.info("FSM Routes Registered")


async def navigate_to_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: BotState,
    data: dict[str, Any] | None = None,
    force: bool = False
) -> BotState:
    """Navigate to a state via FSM router (via DI)."""
    router = get_from_context(context, FSMRouter)
    return await router.navigate_to(update, context, state, data, force)


async def navigate_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Navigate to categories view."""
    return await navigate_to_state(update, context, BotState.BROWSE_CATEGORIES)


async def navigate_to_products(
    update: Update, context: ContextTypes.DEFAULT_TYPE, category: str | None = None
) -> BotState:
    """Navigate to products view."""
    data = {"category": category} if category else None
    return await navigate_to_state(update, context, BotState.BROWSE_PRODUCTS, data)


async def navigate_to_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int) -> BotState:
    """Navigate to product detail view."""
    return await navigate_to_state(update, context, BotState.VIEW_PRODUCT, {"product_id": product_id})


async def navigate_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Navigate to cart view."""
    return await navigate_to_state(update, context, BotState.CART)


async def navigate_to_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Navigate to checkout view."""
    return await navigate_to_state(update, context, BotState.CHECKOUT)


async def navigate_to_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Navigate to favorites view."""
    return await navigate_to_state(update, context, BotState.FAVORITES)


async def navigate_to_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Navigate to AI chat view."""
    return await navigate_to_state(update, context, BotState.AI_CHAT)


async def navigate_to_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Navigate to user panel view."""
    return await navigate_to_state(update, context, BotState.USER_PANEL)
