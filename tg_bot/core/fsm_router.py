import logging
from dataclasses import dataclass
from typing import Any, Callable

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from tg_bot.core.state_manager import BotState, StateMachine, StateManager, TransitionError

logger = logging.getLogger(__name__)


@dataclass
class MediatorCommand:
    """Command sent from handler to mediator."""
    user_id: int
    target_state: BotState
    data: dict[str, Any] | None = None
    force: bool = False


class ViewRenderer:
    """Interface for view layer implementations."""

    async def render(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: BotState, data: dict[str, Any]) -> None:
        """Render the view for the given state."""
        raise NotImplementedError


class FSMRouter:
    """
    Mediator pattern: Handles state transitions and triggers view rendering.
    Handlers send commands here, router decides what to do.
    """

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager
        self._views: dict[BotState, ViewRenderer] = {}
        self._transition_handlers: dict[tuple[BotState, BotState], Callable[..., Any]] = {}

    def register_view(self, state: BotState, renderer: ViewRenderer) -> None:
        """Register a view renderer for a state."""
        self._views[state] = renderer
        logger.debug(f"Registered view: {state.value}")

    def register_transition(self, from_state: BotState, to_state: BotState, handler: Callable[..., Any]) -> None:
        """Register a handler to be called on transition."""
        key = (from_state, to_state)
        self._transition_handlers[key] = handler

    async def dispatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE, command: MediatorCommand) -> BotState:
        """
        Main entry point: process command, transition state, render view.
        Returns the new state.
        """
        user_id = command.user_id
        target_state = command.target_state
        current_state = await self.state_manager.get_state(user_id)

        if not command.force:
            try:
                StateMachine.validate(current_state, target_state)
            except TransitionError:
                logger.warning(f"Invalid transition for user {user_id}: {current_state.value} -> {target_state.value}")
                if update.callback_query:
                    try:
                        await update.callback_query.answer()
                    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                        logger.warning(f"callback_query.answer failed: {e}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Ваша сессия устарела. Пожалуйста, вернитесь в главное меню: /menu"
                )
                return current_state

        if command.data:
            await self.state_manager.set_data_batch(user_id, command.data)

        transition_key = (current_state, target_state)
        handler = self._transition_handlers.get(transition_key)
        if handler:
            try:
                await handler(update, context, current_state, target_state)
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Transition handler failed: {e}")
                await self._notify_error(context, user_id)

        await self.state_manager.set_state(user_id, target_state)

        renderer = self._views.get(target_state)
        if renderer:
            ctx_data = await self.state_manager.get_data(user_id)
            try:
                await renderer.render(update, context, target_state, ctx_data)
            except TelegramError as e:
                logger.warning(f"View render TelegramError for {target_state.value}: {e}")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"View render failed for {target_state.value}: {e}")
                await self._notify_error(context, user_id)
                await self._notify_error(context, user_id)

        logger.info(f"FSM: user={user_id} {current_state.value} -> {target_state.value}")
        return target_state

    async def navigate_to(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_state: BotState, data: dict[str, Any] | None = None, force: bool = False) -> BotState:
        """Helper: navigate to a state."""
        user_id = update.effective_user.id if update.effective_user else 0
        command = MediatorCommand(
            user_id=user_id,
            target_state=target_state,
            data=data,
            force=force,
        )
        return await self.dispatch(update, context, command)

    async def get_current_state(self, user_id: int) -> BotState:
        """Get current state for user."""
        return await self.state_manager.get_state(user_id)

    async def _notify_error(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
        """Send error notification to user."""
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ Произошла ошибка. Попробуйте /menu для возврата в главное меню."
            )
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"[databases/kojo/tg_bot/core/fsm_router.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")
