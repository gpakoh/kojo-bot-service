# Tests For FSM Router (replacing Backstack Tests)
from typing import Any
from unittest.mock import MagicMock

import pytest

from tg_bot.core.fsm_router import FSMRouter, MediatorCommand, ViewRenderer
from tg_bot.core.state_manager import BotState, StateMachine, TransitionError


class MockStateManager:
    """Mock for StateManager with in-memory storage."""
    def __init__(self) -> None:
        self._states = {}
        self._data = {}

    async def get_state(self, user_id: int) -> BotState:
        return self._states.get(user_id, BotState.IDLE)

    async def set_state(self, user_id: int, state: BotState) -> None:
        self._states[user_id] = state

    async def get_data(self, user_id: int) -> dict[str, Any]:
        return self._data.get(user_id, {})

    async def set_data_batch(self, user_id: int, data: dict[str, Any]) -> None:
        self._data[user_id] = data


class MockViewRenderer(ViewRenderer):
    """Mock view renderer for testing."""
    def __init__(self) -> None:
        self.rendered = False
        self.last_state = None
        self.last_data = None

    async def render(self, update, context, state: BotState, data: dict[str, Any]) -> None:
        self.rendered = True
        self.last_state = state
        self.last_data = data


@pytest.fixture
def mock_state_manager() -> Any:
    return MockStateManager()


@pytest.fixture
def fsm_router(mock_state_manager) -> Any:
    router = FSMRouter(mock_state_manager)
    return router


class TestFSMRouter:
    """Tests for FSMRouter navigation."""

    @pytest.mark.asyncio
    async def test_navigate_to_changes_state(self, fsm_router, mock_state_manager) -> Any:
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        context = MagicMock()

        result = await fsm_router.navigate_to(update, context, BotState.BROWSE_CATEGORIES)

        assert result == BotState.BROWSE_CATEGORIES
        assert await mock_state_manager.get_state(123) == BotState.BROWSE_CATEGORIES

    @pytest.mark.asyncio
    async def test_navigate_to_with_data(self, fsm_router, mock_state_manager) -> Any:
        await mock_state_manager.set_state(123, BotState.BROWSE_PRODUCTS)
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.callback_query = None
        context = MagicMock()

        await fsm_router.navigate_to(
            update, context, BotState.VIEW_PRODUCT, {"product_id": 42}
        )

        data = await mock_state_manager.get_data(123)
        assert data.get("product_id") == 42

    @pytest.mark.asyncio
    async def test_navigate_to_with_force_bypasses_validation(self, fsm_router, mock_state_manager) -> Any:
        await mock_state_manager.set_state(123, BotState.IDLE)
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        update.callback_query = None
        context = MagicMock()

        result = await fsm_router.navigate_to(
            update, context, BotState.CHECKOUT, force=True
        )

        assert result == BotState.CHECKOUT

    @pytest.mark.asyncio
    async def test_dispatch_calls_view_renderer(self, fsm_router, mock_state_manager) -> Any:
        renderer = MockViewRenderer()
        fsm_router.register_view(BotState.BROWSE_CATEGORIES, renderer)

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123
        context = MagicMock()

        await fsm_router.navigate_to(update, context, BotState.BROWSE_CATEGORIES)

        assert renderer.rendered is True
        assert renderer.last_state == BotState.BROWSE_CATEGORIES

    @pytest.mark.asyncio
    async def test_get_current_state(self, fsm_router, mock_state_manager) -> Any:
        await mock_state_manager.set_state(123, BotState.CART)

        state = await fsm_router.get_current_state(123)
        assert state == BotState.CART


class TestStateManager:
    """Tests for StateManager state transitions."""

    @pytest.mark.asyncio
    async def test_set_and_get_state(self, mock_state_manager) -> Any:
        await mock_state_manager.set_state(123, BotState.BROWSE_CATEGORIES)
        state = await mock_state_manager.get_state(123)
        assert state == BotState.BROWSE_CATEGORIES

    @pytest.mark.asyncio
    async def test_get_state_returns_idle_for_new_user(self, mock_state_manager) -> Any:
        state = await mock_state_manager.get_state(999)
        assert state == BotState.IDLE


class TestStateMachine:
    """Tests for StateMachine validation."""

    def test_valid_transition_categories_to_products(self) -> Any:
        StateMachine.validate(BotState.BROWSE_CATEGORIES, BotState.BROWSE_PRODUCTS)

    def test_valid_transition_products_to_product_detail(self) -> Any:
        StateMachine.validate(BotState.BROWSE_PRODUCTS, BotState.VIEW_PRODUCT)

    def test_valid_transition_products_to_cart(self) -> Any:
        StateMachine.validate(BotState.BROWSE_PRODUCTS, BotState.CART)

    def test_invalid_transition_idle_to_checkout(self) -> Any:
        with pytest.raises(TransitionError):
            StateMachine.validate(BotState.IDLE, BotState.CHECKOUT)

    def test_invalid_transition_idle_to_cart(self) -> Any:
        with pytest.raises(TransitionError):
            StateMachine.validate(BotState.IDLE, BotState.CART)

    def test_force_bypasses_validation_in_router(self) -> Any:
        """Force flag is handled by router, not validate()."""
        with pytest.raises(TransitionError):
            StateMachine.validate(BotState.IDLE, BotState.CHECKOUT)


class TestMediatorCommand:
    """Tests for MediatorCommand dataclass."""

    def test_command_creation(self) -> Any:
        cmd = MediatorCommand(
            user_id=123,
            target_state=BotState.CART,
            data={"item": "test"},
            force=False
        )
        assert cmd.user_id == 123
        assert cmd.target_state == BotState.CART
        assert cmd.data == {"item": "test"}
        assert cmd.force is False

    def test_command_defaults(self) -> Any:
        cmd = MediatorCommand(user_id=123, target_state=BotState.CART)
        assert cmd.data is None
        assert cmd.force is False
