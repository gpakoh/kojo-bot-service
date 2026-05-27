import logging
from typing import TYPE_CHECKING, Any, Callable

from tg_bot.core.fsm_router import ViewRenderer as BaseViewRenderer

if TYPE_CHECKING:
    from tg_bot.core.fsm_router import FSMRouter

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from tg_bot.core.state_manager import BotState, StateManager

logger = logging.getLogger(__name__)


class ViewRenderer(BaseViewRenderer):
    """Interface for view layer implementations."""

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        """Render the view for the given state."""
        raise NotImplementedError

    async def _safe_render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, render_fn: Callable[..., Any]) -> None:
        """Wrap render with proper error handling."""
        try:
            await render_fn(update, context)
        except TelegramError as e:
            logger.warning(f"View render TelegramError: {e}")
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"View render failed: {e}", exc_info=True)
            user_id = update.effective_user.id if update.effective_user else None
            if user_id:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="⚠️ Произошла ошибка. Попробуйте /menu для возврата в главное меню."
                    )
                except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                    logger.warning(f"Failed to send error message: {e}")


class CategoriesView(ViewRenderer):
    """Renders categories view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.categories import show_categories_menu
        await self._safe_render(update, context, show_categories_menu)


class ProductsView(ViewRenderer):
    """Renders products list view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.products import show_products_menu
        await self._safe_render(update, context, show_products_menu)


class ProductDetailView(ViewRenderer):
    """Renders product detail view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.products import show_product_detail
        await self._safe_render(update, context, show_product_detail)


class CartView(ViewRenderer):
    """Renders cart view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.cart import show_cart
        await self._safe_render(update, context, show_cart)


class CheckoutView(ViewRenderer):
    """Renders checkout view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.order_delivery_checkout import start_checkout  # type: ignore[attr-defined]
        await self._safe_render(update, context, start_checkout)


class FavoritesView(ViewRenderer):
    """Renders favorites view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.favorites import show_favorites_menu
        await self._safe_render(update, context, show_favorites_menu)


class AIChatView(ViewRenderer):
    """Renders AI chat view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.ai_chat import start_ai_chat
        await self._safe_render(update, context, start_ai_chat)


class UserPanelView(ViewRenderer):
    """Renders user panel view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.user_panel import show_user_panel  # type: ignore[attr-defined]
        await self._safe_render(update, context, show_user_panel)


class RegistrationView(ViewRenderer):
    """Renders registration view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.registration import start_registration  # type: ignore[attr-defined]
        await self._safe_render(update, context, start_registration)


class OrderSuccessView(ViewRenderer):
    """Renders order success view."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        from tg_bot.handlers.order_delivery_checkout import show_order_success  # type: ignore[attr-defined]
        await self._safe_render(update, context, show_order_success)


VIEW_RENDERERS: dict[BotState, type[ViewRenderer]] = {
    BotState.BROWSE_CATEGORIES: CategoriesView,
    BotState.BROWSE_PRODUCTS: ProductsView,
    BotState.VIEW_PRODUCT: ProductDetailView,
    BotState.CART: CartView,
    BotState.CHECKOUT: CheckoutView,
    BotState.FAVORITES: FavoritesView,
    BotState.AI_CHAT: AIChatView,
    BotState.USER_PANEL: UserPanelView,
    BotState.REGISTRATION: RegistrationView,
    BotState.ORDER_SUCCESS: OrderSuccessView,
}


def create_router_with_views(state_manager: StateManager) -> 'FSMRouter':
    """Factory to create router with all view renderers registered."""
    from tg_bot.core.fsm_router import FSMRouter

    router = FSMRouter(state_manager)

    for state, view_class in VIEW_RENDERERS.items():
        renderer = view_class(state_manager)  # type: ignore[call-arg]
        router.register_view(state, renderer)

    return router


class FSMRouterWithViews:
    """Extended router with view support."""

    def __init__(self, state_manager: StateManager) -> None:
        from tg_bot.core.fsm_router import FSMRouter
        self._router = FSMRouter(state_manager)
        self._state_manager = state_manager

        for state, view_class in VIEW_RENDERERS.items():
            renderer = view_class(state_manager)  # type: ignore[call-arg]
            self._router.register_view(state, renderer)

    @property
    def router(self) -> Any:
        return self._router

    async def navigate_to(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_state: BotState, data: dict[str, Any] | None = None, force: bool = False) -> Any:
        return await self._router.navigate_to(update, context, target_state, data, force)

    async def get_current_state(self, user_id: int) -> BotState:
        return await self._router.get_current_state(user_id)
