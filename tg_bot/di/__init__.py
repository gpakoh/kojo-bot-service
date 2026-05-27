# Tg_bot/di/__init__.py
from typing import Any, Optional

from tg_bot.di.middleware import inject_di, register_di_middleware
from tg_bot.di.provider import Provider, get_from_context, get_provider, init_provider
from tg_bot.di.unit_of_work import UnitOfWork, UnitOfWorkFactory, create_uow_factory

__all__ = [
    'Provider',
    'get_provider',
    'init_provider',
    'get_from_context',
    'inject_di',
    'register_di_middleware',
    'UnitOfWork',
    'UnitOfWorkFactory',
    'create_uow_factory',
]
