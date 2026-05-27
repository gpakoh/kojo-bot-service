# Tests For Navigation Layer
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.navigation import (
    BackStack,
    Navigation,
    NavigationRegistry,
    NavigationState,
    Screen,
    ScreenType,
    get_or_create_back_target,
    get_previous_screen,
)


class MockContext:
    def __init__(self, user_id: int = 123) -> None:
        self.effective_user = MagicMock()
        self.effective_user.id = user_id
        self.user_data = {}
        self.bot_data = {}
        self.bot = MagicMock()


def make_context(user_id: int = 123) -> MockContext:
    return MockContext(user_id=user_id)


class TestScreen:
    """Tests for Screen value object."""

    def test_screen_creation(self) -> Any:
        screen = Screen(ScreenType.CATEGORIES, {'key': 'value'}, 'callback')
        assert screen.screen_type == ScreenType.CATEGORIES
        assert screen.data == {'key': 'value'}
        assert screen.callback_data == 'callback'

    def test_screen_key(self) -> Any:
        screen = Screen(ScreenType.PRODUCT_VIEW, {}, 'prod_123')
        assert screen.key == 'product_view:prod_123'

    def test_screen_key_no_callback(self) -> Any:
        screen = Screen(ScreenType.MAIN_MENU, {})
        assert screen.key == 'main_menu:default'

    def test_screen_to_dict(self) -> Any:
        screen = Screen(ScreenType.CART, {'item_count': 5})
        d = screen.to_dict()
        assert d['screen_type'] == 'cart'
        assert d['data'] == {'item_count': 5}

    def test_screen_from_dict(self) -> Any:
        data = {'screen_type': 'categories', 'data': {'cat': 'coffee'}, 'callback_data': 'cb'}
        screen = Screen.from_dict(data)
        assert screen.screen_type == ScreenType.CATEGORIES
        assert screen.data == {'cat': 'coffee'}
        assert screen.callback_data == 'cb'


class TestBackStack:
    """Tests for BackStack navigation."""

    def test_push_screen(self) -> Any:
        ctx = make_context()
        screen = Screen(ScreenType.MAIN_MENU)
        BackStack.push(ctx, screen)

        state = BackStack.get_state(ctx)
        assert state.current_screen.screen_type == ScreenType.MAIN_MENU

    def test_push_then_pop(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))

        prev = BackStack.pop(ctx)

        state = BackStack.get_state(ctx)
        assert state.current_screen.screen_type == ScreenType.MAIN_MENU
        assert prev.screen_type == ScreenType.MAIN_MENU

    def test_replace_screen(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))

        BackStack.replace(ctx, Screen(ScreenType.CART))

        state = BackStack.get_state(ctx)
        assert state.current_screen.screen_type == ScreenType.CART
        assert len(state.back_stack) == 1

    def test_can_go_back(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        assert BackStack.can_go_back(ctx) is False

        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))
        assert BackStack.can_go_back(ctx) is True

    def test_go_back_returns_none_when_empty(self) -> Any:
        ctx = make_context()
        result = BackStack.go_back(ctx)
        assert result is None

    def test_clear_stack(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))

        BackStack.clear(ctx)

        state = BackStack.get_state(ctx)
        assert state.current_screen is None
        assert len(state.back_stack) == 0

    def test_get_current(self) -> Any:
        ctx = make_context()
        screen = Screen(ScreenType.MAIN_MENU)
        BackStack.push(ctx, screen)

        current = BackStack.get_current(ctx)
        assert current.screen_type == ScreenType.MAIN_MENU

    def test_get_stack_size(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))

        assert BackStack.get_stack_size(ctx) == 1

    def test_isolated_per_context(self) -> Any:
        ctx1 = make_context(user_id=1)
        ctx2 = make_context(user_id=2)

        BackStack.push(ctx1, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx2, Screen(ScreenType.CATEGORIES))

        assert BackStack.get_current(ctx1).screen_type == ScreenType.MAIN_MENU
        assert BackStack.get_current(ctx2).screen_type == ScreenType.CATEGORIES


class TestNavigationRegistry:
    """Tests for handler registry."""

    def setup_method(self) -> Any:
        self.registry = NavigationRegistry()

    def test_register_handler(self) -> Any:
        async def handler(update, context):
            pass

        self.registry.register(ScreenType.CATEGORIES)(handler)

        assert self.registry.has_handler(ScreenType.CATEGORIES)
        assert self.registry.get_handler(ScreenType.CATEGORIES) == handler

    def test_register_fallback(self) -> Any:
        async def fallback(update, context):
            pass

        self.registry.register_fallback(ScreenType.PRODUCT_VIEW)(fallback)

        assert self.registry.get_handler(ScreenType.PRODUCT_VIEW) is None

    def test_no_handler_for_unknown_screen(self) -> Any:
        assert self.registry.get_handler(ScreenType.SEARCH) is None


class TestNavigationState:
    """Tests for NavigationState."""

    def test_state_creation(self) -> Any:
        state = NavigationState(user_id=123)
        assert state.user_id == 123
        assert state.current_screen is None
        assert len(state.back_stack) == 0
        assert len(state.metadata) == 0

    def test_state_with_initial_screen(self) -> Any:
        screen = Screen(ScreenType.MAIN_MENU)
        state = NavigationState(user_id=123, current_screen=screen)

        assert state.current_screen.screen_type == ScreenType.MAIN_MENU


class TestNavigationRegistryExtra:
    """Additional tests for NavigationRegistry."""

    def setup_method(self) -> Any:
        self.registry = NavigationRegistry()

    def test_get_fallback_handler_returns_handler(self) -> Any:
        async def fallback(update, context):
            pass

        self.registry.register_fallback(ScreenType.PRODUCT_VIEW)(fallback)

        result = self.registry.get_fallback_handler(ScreenType.PRODUCT_VIEW)
        assert result == fallback

    def test_get_fallback_handler_returns_none_when_missing(self) -> Any:
        result = self.registry.get_fallback_handler(ScreenType.SEARCH)
        assert result is None


class TestNavigation:
    """Tests for high-level Navigation class."""

    def test_get_registry_creates_new_if_missing(self) -> Any:
        ctx = make_context()
        assert "navigation_registry" not in ctx.bot_data

        registry = Navigation._get_registry(ctx)

        assert isinstance(registry, NavigationRegistry)
        assert ctx.bot_data["navigation_registry"] is registry

    def test_get_registry_returns_existing(self) -> Any:
        ctx = make_context()
        existing = NavigationRegistry()
        ctx.bot_data["navigation_registry"] = existing

        registry = Navigation._get_registry(ctx)

        assert registry is existing

    @pytest.mark.asyncio
    async def test_navigate_to_handler_success(self) -> Any:
        ctx = make_context()
        handler = AsyncMock(return_value=None)
        registry = Navigation._get_registry(ctx)
        registry.register(ScreenType.CATEGORIES)(handler)
        update = MagicMock()

        result = await Navigation.navigate_to(
            context=ctx,
            screen_type=ScreenType.CATEGORIES,
            data={"cat": "coffee"},
            callback_data="cb_1",
            update=update,
        )

        assert result is True
        handler.assert_awaited_once_with(update, ctx)

        state = BackStack.get_state(ctx)
        assert state.current_screen.screen_type == ScreenType.CATEGORIES
        assert state.current_screen.data == {"cat": "coffee"}
        assert state.current_screen.callback_data == "cb_1"

    @pytest.mark.asyncio
    async def test_navigate_to_handler_failure_with_fallback(self) -> Any:
        ctx = make_context()
        handler = AsyncMock(side_effect=ValueError("handler crashed"))
        fallback = AsyncMock(return_value=None)
        registry = Navigation._get_registry(ctx)
        registry.register(ScreenType.PRODUCT_VIEW)(handler)
        registry.register_fallback(ScreenType.PRODUCT_VIEW)(fallback)
        update = MagicMock()

        result = await Navigation.navigate_to(
            context=ctx,
            screen_type=ScreenType.PRODUCT_VIEW,
            update=update,
        )

        assert result is False
        fallback.assert_awaited_once_with(update, ctx)

    @pytest.mark.asyncio
    async def test_navigate_to_no_handler_returns_false(self) -> Any:
        ctx = make_context()

        result = await Navigation.navigate_to(
            context=ctx,
            screen_type=ScreenType.SEARCH,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_navigate_to_handler_failure_without_fallback(self) -> Any:
        ctx = make_context()
        handler = AsyncMock(side_effect=RuntimeError("fail"))
        registry = Navigation._get_registry(ctx)
        registry.register(ScreenType.CART)(handler)
        update = MagicMock()

        result = await Navigation.navigate_to(
            context=ctx,
            screen_type=ScreenType.CART,
            update=update,
        )

        assert result is False

    def test_can_go_back_returns_false_when_no_screens(self) -> Any:
        ctx = make_context()

        assert Navigation.can_go_back(ctx) is False

    def test_can_go_back_returns_true_with_screens(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))

        assert Navigation.can_go_back(ctx) is True

    def test_reset_clears_state(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))
        assert BackStack.can_go_back(ctx) is True

        Navigation.reset(ctx)

        assert Navigation.can_go_back(ctx) is False
        state = BackStack.get_state(ctx)
        assert state.current_screen is None
        assert len(state.back_stack) == 0

    @pytest.mark.asyncio
    async def test_go_back_handler_call_path(self) -> Any:
        ctx = make_context()
        back_handler = AsyncMock(return_value=None)
        registry = Navigation._get_registry(ctx)
        registry.register(ScreenType.MAIN_MENU)(back_handler)
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))
        update = MagicMock()

        result = await Navigation.go_back(context=ctx, update=update)

        assert result is True
        back_handler.assert_awaited_once_with(update, ctx)

    @pytest.mark.asyncio
    async def test_go_back_returns_false_when_no_back_stack(self) -> Any:
        ctx = make_context()

        result = await Navigation.go_back(context=ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_go_back_handler_failure_logged(self) -> Any:
        ctx = make_context()
        handler = AsyncMock(side_effect=ValueError("back fail"))
        registry = Navigation._get_registry(ctx)
        registry.register(ScreenType.MAIN_MENU)(handler)
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))
        update = MagicMock()

        result = await Navigation.go_back(context=ctx, update=update)

        assert result is False


class TestGetPreviousScreen:
    def test_with_backstack(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU, {"k": "v1"}))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES, {"k": "v2"}))

        prev = get_previous_screen(ctx)

        assert prev is not None
        assert prev.screen_type == ScreenType.MAIN_MENU
        assert prev.data == {"k": "v1"}

    def test_without_backstack(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))

        prev = get_previous_screen(ctx)

        assert prev is None


class TestGetOrCreateBackTarget:
    def test_with_backstack_returns_message_id(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU, {"message_id": "42"}))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES, {"message_id": "99"}))

        result = get_or_create_back_target(ctx, "fallback_key")

        assert result == "42"

    def test_without_backstack_falls_back(self) -> Any:
        ctx = make_context()
        ctx.user_data["fallback_key"] = "fallback_val"
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))

        result = get_or_create_back_target(ctx, "fallback_key")

        assert result == "fallback_val"

    def test_no_backstack_no_fallback_returns_none(self) -> Any:
        ctx = make_context()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))

        result = get_or_create_back_target(ctx, "nonexistent_key")

        assert result is None


class TestScreenFromDictMissingCallback:
    def test_from_dict_missing_callback_data(self) -> Any:
        data = {"screen_type": "main_menu", "data": {"k": "v"}}
        screen = Screen.from_dict(data)

        assert screen.screen_type == ScreenType.MAIN_MENU
        assert screen.data == {"k": "v"}
        assert screen.callback_data is None


class TestBackStackGetStateByUserId:
    def test_get_state_by_user_id_mismatch_updates(self) -> Any:
        ctx = make_context(user_id=100)
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))

        state = BackStack.get_state_by_user_id(ctx, user_id=999)

        assert state.user_id == 999
        assert state.current_screen.screen_type == ScreenType.MAIN_MENU

    def test_get_state_by_user_id_match_preserves(self) -> Any:
        ctx = make_context(user_id=100)
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))

        state = BackStack.get_state_by_user_id(ctx, user_id=100)

        assert state.user_id == 100


class TestNavigateToDecorator:
    @pytest.mark.asyncio
    async def test_navigate_to_does_not_raise_type_error(self):
        from tg_bot.navigation import ScreenType, navigate_to

        handler = AsyncMock()
        decorated = navigate_to(ScreenType.CATEGORIES)(handler)
        ctx = MockContext()
        await decorated(MagicMock(), ctx)

        handler.assert_not_awaited()  # navigate_to calls Navigation.navigate_to, not the handler


class TestNavigateBackDecorator:
    @pytest.mark.asyncio
    async def test_navigate_back_no_backstack_calls_handler(self):
        from tg_bot.navigation import navigate_back

        handler = AsyncMock()
        decorated = navigate_back()(handler)
        ctx = MockContext()
        await decorated(MagicMock(), ctx)

        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_navigate_back_with_backstack_does_not_raise(self):
        from tg_bot.navigation import BackStack, Screen, ScreenType, navigate_back

        handler = AsyncMock()
        decorated = navigate_back()(handler)
        ctx = MockContext()
        BackStack.push(ctx, Screen(ScreenType.MAIN_MENU))
        BackStack.push(ctx, Screen(ScreenType.CATEGORIES))

        await decorated(MagicMock(), ctx)

        handler.assert_not_awaited()
