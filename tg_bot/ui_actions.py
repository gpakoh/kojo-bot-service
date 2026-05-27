# Tg_bot/ui_actions.py
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

UI_ACTIONS: dict[str, Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable]] = {}


def register_ui_action(key: str, action: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable]) -> None:
    """Регистрирует UI-функцию по строковому ключу."""
    UI_ACTIONS[key] = action


async def call_ui_action(key: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вызывает зарегистрированную UI-функцию по ключу."""
    action = UI_ACTIONS.get(key)
    if action:
        await action(update, context)
