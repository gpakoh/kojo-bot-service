# Session State Pattern - Separates Guest And Authenticated User Behavior
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """Holds session state for a user."""
    user_id: int
    is_guest: bool = False
    registered_at: Optional[datetime] = None
    last_interaction: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionStrategy(ABC):
    """Abstract base for session strategies."""

    @abstractmethod
    def can_add_to_cart(self) -> bool:
        """Guests cannot add to cart, only view."""
        pass

    @abstractmethod
    def can_view_favorites(self) -> bool:
        """Guests cannot view favorites."""
        pass

    @abstractmethod
    def can_make_order(self) -> bool:
        """Guests cannot make orders."""
        pass

    @abstractmethod
    def can_use_personal_offers(self) -> bool:
        """Guests cannot use personal offers."""
        pass

    @abstractmethod
    def get_view_mode(self, requested_mode: str) -> str:
        """Guests always use list view for consistency."""
        pass

    @abstractmethod
    def get_registration_prompt(self) -> str:
        """Prompt shown to guests."""
        pass

    @abstractmethod
    def get_cart_limit(self) -> int:
        """Guests have limited cart."""
        pass


class GuestSession(SessionStrategy):
    """Session for unauthenticated users - limited functionality."""

    CART_LIMIT = 3
    VIEW_MODE_DEFAULT = 'list'

    def can_add_to_cart(self) -> bool:
        return True

    def can_view_favorites(self) -> bool:
        return False

    def can_make_order(self) -> bool:
        return False

    def can_use_personal_offers(self) -> bool:
        return False

    def get_view_mode(self, requested_mode: str) -> str:
        if requested_mode == 'gallery':
            logger.info("Guest Mode: Forcing List View Instead Of Gallery")
            return self.VIEW_MODE_DEFAULT
        return requested_mode

    def get_registration_prompt(self) -> str:
        return "Для оформления заказа необходимо зарегистрироваться /start"

    def get_cart_limit(self) -> int:
        return self.CART_LIMIT


class UserSession(SessionStrategy):
    """Session for authenticated users - full functionality."""

    CART_LIMIT = 50
    VIEW_MODE_DEFAULT = 'list'

    def can_add_to_cart(self) -> bool:
        return True

    def can_view_favorites(self) -> bool:
        return True

    def can_make_order(self) -> bool:
        return True

    def can_use_personal_offers(self) -> bool:
        return True

    def get_view_mode(self, requested_mode: str) -> str:
        return requested_mode

    def get_registration_prompt(self) -> str:
        return ""

    def get_cart_limit(self) -> int:
        return self.CART_LIMIT


class SessionManager:
    """
    Factory and manager for user sessions.
    Delegates to context.user_data for persistence (survives restarts with PTB Persistence).
    """

    _strategies: Dict[bool, SessionStrategy] = {
        True: GuestSession(),
        False: UserSession(),
    }

    @classmethod
    def _get_user_sessions(cls, context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
        """Get sessions dict from context.user_data (creates if needed)."""
        if context.user_data is None:
            context.user_data = {}
        if 'session_manager_sessions' not in context.user_data:
            context.user_data['session_manager_sessions'] = {}
        sessions: dict[str, Any] = context.user_data['session_manager_sessions']
        return sessions

    @classmethod
    def get_session(cls, user_id: int, is_guest: bool, context: ContextTypes.DEFAULT_TYPE) -> SessionContext:
        """Get or create session for user from context.user_data."""
        sessions = cls._get_user_sessions(context)

        key = str(user_id)

        if key not in sessions:
            sessions[key] = SessionContext(
                user_id=user_id,
                is_guest=is_guest,
            )
        session: SessionContext = sessions[key]
        session.is_guest = is_guest
        session.last_interaction = datetime.now()
        return session

    @classmethod
    def get_strategy(cls, is_guest: bool) -> SessionStrategy:
        """Get appropriate strategy for session type."""
        return cls._strategies[is_guest]

    @classmethod
    def clear_session(cls, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear session data from context.user_data."""
        sessions = cls._get_user_sessions(context)
        key = str(user_id)
        if key in sessions:
            del sessions[key]

    @classmethod
    def set_registered(cls, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Upgrade guest to user after registration."""
        sessions = cls._get_user_sessions(context)
        key = str(user_id)
        if key in sessions:
            sessions[key].is_guest = False
            sessions[key].registered_at = datetime.now()
            logger.info(f"Session upgraded: user {user_id} registered")


def get_session_for_context(context: ContextTypes.DEFAULT_TYPE) -> tuple[SessionContext, SessionStrategy]:
    """
    Helper to get session from bot context.
    Uses context.user_data for persistence (survives restarts with PTB Persistence).
    """
    user_id = context.user_data.get('user_id', 0) if context.user_data else 0
    is_guest = context.user_data.get('is_guest', False) if context.user_data else False

    session: SessionContext = SessionManager.get_session(user_id, is_guest, context)
    strategy: SessionStrategy = SessionManager.get_strategy(is_guest)

    return session, strategy
