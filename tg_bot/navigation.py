# Navigation Layer With Screen And Backstack - Manages UI Flow
# Uses Context.user_data For Persistence (survives Restarts With PTB Persistence)
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from telegram.ext import ContextTypes


class ScreenType(str, Enum):
    """Screen types in the bot."""
    MAIN_MENU = "main_menu"
    CATEGORIES = "categories"
    PRODUCT_LIST = "product_list"
    PRODUCT_VIEW = "product_view"
    CART = "cart"
    FAVORITES = "favorites"
    ORDER_CHECKOUT = "order_checkout"
    ORDER_SUCCESS = "order_success"
    USER_PANEL = "user_panel"
    SEARCH = "search"
    FAVORITES_LIST = "favorites_list"
    GIFT_CHECKOUT = "gift_checkout"
    ORDER_DELIVERY = "order_delivery"
    REGISTRATION = "registration"
    AI_CHAT = "ai_chat"
    ADMIN_PANEL = "admin_panel"


@dataclass
class Screen:
    """Represents a single screen in the navigation flow."""
    screen_type: ScreenType
    data: Dict[str, Any] = field(default_factory=dict)
    callback_data: Optional[str] = None

    @property
    def key(self) -> str:
        """Unique key for this screen instance."""
        return f"{self.screen_type.value}:{self.callback_data or 'default'}"

    def to_dict(self) -> dict[str, Any]:
        return {
            'screen_type': self.screen_type.value,
            'data': self.data,
            'callback_data': self.callback_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Screen:
        return cls(
            screen_type=ScreenType(data['screen_type']),
            data=data.get('data', {}),
            callback_data=data.get('callback_data'),
        )


@dataclass
class NavigationState:
    """Current navigation state for a user."""
    user_id: int
    current_screen: Optional[Screen] = None
    back_stack: List[Screen] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BackStack:
    """
    Manages navigation back stack per user using context.user_data.
    Survives restarts with PTB Persistence.
    """

    _KEY = "_nav_state"

    @classmethod
    def _get_state(cls, context: ContextTypes.DEFAULT_TYPE) -> NavigationState:
        """Get or create navigation state from context.user_data."""
        user_data = context.user_data
        if user_data is None:
            user_data = {}
        if cls._KEY not in user_data:
            user_id = context.effective_user.id if context.effective_user else 0  # type: ignore[attr-defined]
            user_data[cls._KEY] = NavigationState(user_id=user_id)
        result: NavigationState = user_data[cls._KEY]
        return result

    @classmethod
    def get_state(cls, context: ContextTypes.DEFAULT_TYPE) -> NavigationState:
        """Get navigation state for current user."""
        return cls._get_state(context)

    @classmethod
    def get_state_by_user_id(cls, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> NavigationState:
        """Get state by user_id (for background operations)."""
        state = cls._get_state(context)
        if state.user_id != user_id:
            state.user_id = user_id
        return state

    @classmethod
    def push(cls, context: ContextTypes.DEFAULT_TYPE, screen: Screen) -> None:
        """Push a new screen onto the stack."""
        state = cls._get_state(context)
        if state.current_screen:
            state.back_stack.append(state.current_screen)
        state.current_screen = screen
        logger.debug(f"Navigation: pushed {screen.screen_type.value} for user {state.user_id}")

    @classmethod
    def pop(cls, context: ContextTypes.DEFAULT_TYPE) -> Optional[Screen]:
        """Pop the previous screen from stack."""
        state = cls._get_state(context)
        if state.back_stack:
            prev = state.back_stack.pop()
            state.current_screen = prev
            logger.debug(f"Navigation: popped to {prev.screen_type.value} for user {state.user_id}")
            return prev
        return None

    @classmethod
    def replace(cls, context: ContextTypes.DEFAULT_TYPE, screen: Screen) -> None:
        """Replace current screen without adding to back stack."""
        state = cls._get_state(context)
        state.current_screen = screen
        logger.debug(f"Navigation: replaced with {screen.screen_type.value} for user {state.user_id}")

    @classmethod
    def can_go_back(cls, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if back navigation is possible."""
        state = cls._get_state(context)
        return len(state.back_stack) > 0

    @classmethod
    def go_back(cls, context: ContextTypes.DEFAULT_TYPE) -> Optional[Screen]:
        """Go back one screen. Returns the new current screen."""
        return cls.pop(context)

    @classmethod
    def clear(cls, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear entire navigation stack."""
        user_id = context.effective_user.id if context.effective_user else 0  # type: ignore[attr-defined]
        context.user_data[cls._KEY] = NavigationState(user_id=user_id)  # type: ignore[index]

    @classmethod
    def get_current(cls, context: ContextTypes.DEFAULT_TYPE) -> Optional[Screen]:
        """Get current screen without modifying stack."""
        state = cls._get_state(context)
        return state.current_screen

    @classmethod
    def get_stack_size(cls, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get current stack size."""
        state = cls._get_state(context)
        return len(state.back_stack)


class NavigationRegistry:
    """
    Registry of screen handlers.
    Maps screen types to handler functions.
    Stored in bot_data as bot_data['navigation_registry'].
    """

    def __init__(self) -> None:
        self._handlers: Dict[ScreenType, Callable[..., Any]] = {}
        self._fallback_handlers: Dict[ScreenType, Callable[..., Any]] = {}

    def register(self, screen_type: ScreenType) -> Any:
        """Decorator to register a screen handler."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._handlers[screen_type] = func
            return func
        return decorator

    def register_fallback(self, screen_type: ScreenType) -> Any:
        """Decorator to register fallback handler for errors."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._fallback_handlers[screen_type] = func
            return func
        return decorator

    def get_handler(self, screen_type: ScreenType) -> Optional[Callable[..., Any]]:
        """Get handler for screen type."""
        return self._handlers.get(screen_type)

    def get_fallback_handler(self, screen_type: ScreenType) -> Optional[Callable[..., Any]]:
        """Get fallback handler for screen type."""
        return self._fallback_handlers.get(screen_type)

    def has_handler(self, screen_type: ScreenType) -> bool:
        """Check if handler exists."""
        return screen_type in self._handlers


class Navigation:
    """
    Main navigation interface.
    Provides high-level navigation methods.
    Uses context.user_data for persistence.
    """

    @staticmethod
    def _get_registry(context: ContextTypes.DEFAULT_TYPE) -> NavigationRegistry:
        """Get registry from bot_data."""
        key = 'navigation_registry'
        if key not in context.bot_data:
            context.bot_data[key] = NavigationRegistry()
        result: NavigationRegistry = context.bot_data[key]
        return result

    @staticmethod
    async def navigate_to(
        context: ContextTypes.DEFAULT_TYPE,
        screen_type: ScreenType,
        data: Optional[Dict[str, Any]] = None,
        callback_data: Optional[str] = None,
        update: Any = None,
    ) -> bool:
        """Navigate to a screen. Returns True if handler succeeded."""
        screen = Screen(
            screen_type=screen_type,
            data=data or {},
            callback_data=callback_data,
        )
        BackStack.push(context, screen)

        registry = Navigation._get_registry(context)
        handler = registry.get_handler(screen_type)
        if handler and context:
            try:
                await handler(update, context)
                return True
            except Exception as e:
                logger.error(f"Navigation handler failed for {screen_type.value}: {e}")
                fallback = registry.get_fallback_handler(screen_type)
                if fallback:
                    await fallback(update, context)
        return False

    @staticmethod
    async def go_back(
        context: ContextTypes.DEFAULT_TYPE,
        update: Any = None,
    ) -> bool:
        """Go back to previous screen."""
        if not BackStack.can_go_back(context):
            user_id = context.effective_user.id if context.effective_user else 0  # type: ignore[attr-defined]
            logger.info(f"Cannot go back: no screens in stack for user {user_id}")
            return False

        prev_screen = BackStack.go_back(context)
        if prev_screen:
            registry = Navigation._get_registry(context)
            handler = registry.get_handler(prev_screen.screen_type)
            if handler and context:
                try:
                    await handler(update, context)
                    return True
                except Exception as e:
                    logger.error(f"Go back handler failed: {e}")
        return False

    @staticmethod
    def can_go_back(context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if back navigation is available."""
        return BackStack.can_go_back(context)

    @staticmethod
    def reset(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reset navigation for user."""
        BackStack.clear(context)


def navigate_to(
    screen_type: ScreenType,
    data: Optional[dict[str, Any]] = None,
    callback_data: Optional[str] = None,
) -> Any:
    """
    Decorator for handlers that navigate to a screen.
    Pushes screen to BackStack automatically.

    Usage:
        @navigate_to(ScreenType.CATEGORIES)
        async def show_categories(update, context):
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(update: Any, context: Any) -> None:
            await Navigation.navigate_to(
                context=context,
                screen_type=screen_type,
                data=data,
                callback_data=callback_data,
                update=update,
            )
        return wrapper
    return decorator


def navigate_back(fallback_key: Optional[str] = None) -> Any:
    """
    Decorator for "Back" button handlers.
    Tries BackStack.pop() first, falls back to user_data[fallback_key].

    Usage:
        @navigate_back(fallback_key='last_global_menu_id')
        async def handle_back(update, context):
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(update: Any, context: Any) -> None:
            if BackStack.can_go_back(context):
                await Navigation.go_back(context, update=update)
            else:
                await func(update, context)
        return wrapper
    return decorator


def get_previous_screen(context: ContextTypes.DEFAULT_TYPE) -> Optional[Screen]:
    """Get previous screen without popping."""
    state = BackStack.get_state(context)
    if state.back_stack:
        return state.back_stack[-1]
    return None


def get_or_create_back_target(context: ContextTypes.DEFAULT_TYPE, fallback_key: str) -> Optional[str]:
    """
    Backward compatibility: tries BackStack first, falls back to user_data.
    Returns the message_id to edit/delete for back navigation.
    """
    if BackStack.can_go_back(context):
        prev = get_previous_screen(context)
        if prev:
            return prev.data.get('message_id')

    return context.user_data.get(fallback_key) if context.user_data else None
