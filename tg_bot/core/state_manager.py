import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class BotState(str, Enum):
    IDLE = "idle"
    BROWSE_CATEGORIES = "browse_categories"
    BROWSE_PRODUCTS = "browse_products"
    VIEW_PRODUCT = "view_product"
    CART = "cart"
    CHECKOUT = "checkout"
    ORDER_SUCCESS = "order_success"
    FAVORITES = "favorites"
    AI_CHAT = "ai_chat"
    REGISTRATION = "registration"
    USER_PANEL = "user_panel"


@dataclass
class UserContext:
    """Immutable snapshot of user state at a point in time."""
    user_id: int
    state: BotState
    data: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class StateManager:
    """
    Manages user state in Redis.
    All state transitions happen here — single source of truth.
    Works across multiple pods via Redis.
    """

    STATE_KEY_PREFIX = "bot:state"
    DATA_KEY_PREFIX = "bot:ctx"
    STATE_TTL = 3600

    def __init__(self, redis_url: str = "redis://localhost:6379/2") -> None:
        self.redis_url = redis_url
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def _state_key(self, user_id: int) -> str:
        return f"{self.STATE_KEY_PREFIX}:{user_id}"

    def _data_key(self, user_id: int) -> str:
        return f"{self.DATA_KEY_PREFIX}:{user_id}"

    async def get_state(self, user_id: int) -> BotState:
        """Get current state for user. Returns IDLE if not found."""
        r = await self._get_redis()
        state_val = await r.get(self._state_key(user_id))
        if state_val is None:
            return BotState.IDLE
        try:
            return BotState(state_val)
        except ValueError:
            return BotState.IDLE

    async def set_state(self, user_id: int, state: BotState) -> None:
        """Set new state for user."""
        r = await self._get_redis()
        await r.set(self._state_key(user_id), state.value, ex=self.STATE_TTL)
        logger.debug(f"State: user={user_id} -> {state.value}")

    async def get_data(self, user_id: int) -> dict[str, Any]:
        """Get context data for user."""
        r = await self._get_redis()
        data = await r.hgetall(self._data_key(user_id))  # type: ignore[misc]
        return {k: v for k, v in data.items() if v}

    async def set_data(self, user_id: int, key: str, value: Any) -> None:
        """Set a single data key."""
        r = await self._get_redis()
        import json
        try:
            serialized = json.dumps(value, default=str)
        except (TypeError, ValueError):
            serialized = str(value)
        await r.hset(self._data_key(user_id), key, serialized)  # type: ignore[misc]
        await r.expire(self._data_key(user_id), self.STATE_TTL)

    async def set_data_batch(self, user_id: int, data: dict[str, Any]) -> None:
        """Set multiple data keys at once."""
        if not data:
            return
        r = await self._get_redis()
        import json
        encoded = {}
        for k, v in data.items():
            try:
                encoded[k] = json.dumps(v, default=str)
            except (TypeError, ValueError):
                encoded[k] = str(v)
        if encoded:
            await r.hset(self._data_key(user_id), mapping=encoded)  # type: ignore[misc]
            await r.expire(self._data_key(user_id), self.STATE_TTL)

    async def clear_data(self, user_id: int, key: str | None = None) -> None:
        """Clear specific data key or all data."""
        r = await self._get_redis()
        if key:
                await r.hdel(self._data_key(user_id), key)  # type: ignore[misc, arg-type]
        else:
            await r.delete(self._data_key(user_id))

    async def reset(self, user_id: int) -> None:
        """Reset user to IDLE state."""
        r = await self._get_redis()
        await r.delete(self._state_key(user_id))
        await r.delete(self._data_key(user_id))

    async def get_context(self, user_id: int) -> UserContext:
        """Get full context snapshot for user."""
        import time
        state = await self.get_state(user_id)
        data = await self.get_data(user_id)
        return UserContext(
            user_id=user_id,
            state=state,
            data=data,
            created_at=time.time(),
        )


class TransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class StateMachine:
    """
    FSM for valid state transitions.
    Defines which states can follow which.
    """

    TRANSITIONS = {
        BotState.IDLE: {
            BotState.BROWSE_CATEGORIES,
            BotState.REGISTRATION,
        },
        BotState.BROWSE_CATEGORIES: {
            BotState.BROWSE_PRODUCTS,
            BotState.CART,
            BotState.FAVORITES,
            BotState.AI_CHAT,
            BotState.USER_PANEL,
            BotState.IDLE,
        },
        BotState.BROWSE_PRODUCTS: {
            BotState.VIEW_PRODUCT,
            BotState.BROWSE_CATEGORIES,
            BotState.CART,
            BotState.FAVORITES,
            BotState.AI_CHAT,
            BotState.USER_PANEL,
            BotState.IDLE,
        },
        BotState.VIEW_PRODUCT: {
            BotState.BROWSE_PRODUCTS,
            BotState.CART,
            BotState.BROWSE_CATEGORIES,
            BotState.AI_CHAT,
        },
        BotState.CART: {
            BotState.CHECKOUT,
            BotState.BROWSE_PRODUCTS,
            BotState.BROWSE_CATEGORIES,
            BotState.FAVORITES,
            BotState.IDLE,
        },
        BotState.CHECKOUT: {
            BotState.ORDER_SUCCESS,
            BotState.CART,
            BotState.BROWSE_PRODUCTS,
        },
        BotState.ORDER_SUCCESS: {
            BotState.BROWSE_CATEGORIES,
            BotState.USER_PANEL,
            BotState.IDLE,
        },
        BotState.FAVORITES: {
            BotState.BROWSE_CATEGORIES,
            BotState.BROWSE_PRODUCTS,
            BotState.CART,
            BotState.IDLE,
        },
        BotState.AI_CHAT: {
            BotState.BROWSE_CATEGORIES,
            BotState.IDLE,
        },
        BotState.REGISTRATION: {
            BotState.BROWSE_CATEGORIES,
            BotState.IDLE,
        },
        BotState.USER_PANEL: {
            BotState.BROWSE_CATEGORIES,
            BotState.IDLE,
        },
    }

    @classmethod
    def can_transition(cls, from_state: BotState, to_state: BotState) -> bool:
        if from_state == to_state:
            return True
        allowed = cls.TRANSITIONS.get(from_state, set[Any]())
        return to_state in allowed

    @classmethod
    def validate(cls, from_state: BotState, to_state: BotState) -> None:
        if not cls.can_transition(from_state, to_state):
            raise TransitionError(
                f"Invalid transition: {from_state.value} -> {to_state.value}"
            )
