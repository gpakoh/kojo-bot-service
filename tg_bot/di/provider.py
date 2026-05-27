# Tg_bot/di/provider.py
# Dependency Injection Container - Follows DIP (dependency Inversion Principle)
# Uses Context Injection Pattern (appropriate For Telegram Bot API)

import logging
from typing import Any, Callable, Dict, Optional, Set, Type, TypeVar, cast

import asyncpg
from telegram.ext import ContextTypes

from tg_bot.di.unit_of_work import UnitOfWorkFactory, create_uow_factory

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceRegistry:
    """
    Explicit service registry - tracks all registered services.
    Provides introspection for debugging and testing.
    """

    def __init__(self) -> None:
        self._singletons: Dict[Type[Any], Any] = {}
        self._factories: Dict[Type[Any], Callable[..., Any]] = {}
        self._registered_types: Set[Type[Any]] = set()

    def register_singleton(self, cls: Type[T], instance: T) -> None:
        """Register a singleton instance."""
        self._singletons[cls] = instance
        self._registered_types.add(cls)
        logger.debug(f"Registered singleton: {cls.__name__}")

    def register_factory(self, cls: Type[T], factory: Callable[[], T]) -> None:
        """Register a factory function."""
        self._factories[cls] = factory
        self._registered_types.add(cls)
        logger.debug(f"Registered factory: {cls.__name__}")

    def get(self, cls: Type[T]) -> T:
        """Get instance of a class."""
        if cls in self._singletons:
            return cast(T, self._singletons[cls])

        if cls in self._factories:
            return cast(T, self._factories[cls]())

        raise KeyError(f"No registration found for {cls.__name__}")

    def has(self, cls: Type[T]) -> bool:
        """Check if class is registered."""
        return cls in self._registered_types

    def get_registered_types(self) -> Set[Type[Any]]:
        """Get all registered service types."""
        return self._registered_types.copy()


class Container:
    """
    DI Container following DIP (Dependency Inversion Principle).

    High-level modules should not depend on low-level modules.
    Both should depend on abstractions.

    This container provides:
    - Explicit service registration
    - Context-based injection (appropriate for Telegram handlers)
    - Unit of Work support for transactions

    Usage:
        # Registration (in Main.py Post_init)
        container = Container()
        container.register_singleton(UserService, UserService(pool))

        # Injection (in Handlers)
        user_service = container.get_from_context(context, UserService)
    """

    def __init__(self) -> None:
        self._registry = ServiceRegistry()
        self._pool: Optional[asyncpg.Pool] = None
        self._uow_factory: Optional[UnitOfWorkFactory] = None
        self._initialized = False

    def register_singleton(self, cls: Type[T], instance: T) -> 'Container':
        """Register a singleton instance. Returns self for chaining."""
        self._registry.register_singleton(cls, instance)
        return self

    def register_factory(self, cls: Type[T], factory: Callable[[], T]) -> 'Container':
        """Register a factory function. Returns self for chaining."""
        self._registry.register_factory(cls, factory)
        return self

    def register_pool(self, pool: asyncpg.Pool) -> 'Container':
        """Register database pool and create UnitOfWork factory."""
        self._pool = pool
        self._uow_factory = create_uow_factory(pool)
        self._initialized = True
        logger.info("Container Initialized With Database Pool")
        return self

    def get(self, cls: Type[T]) -> T:
        """Get instance of a class from container."""
        return self._registry.get(cls)

    def has(self, cls: Type[T]) -> bool:
        """Check if class is registered."""
        return self._registry.has(cls)

    @property
    def pool(self) -> asyncpg.Pool:
        """Get database pool."""
        if self._pool is None:
            raise RuntimeError("Database pool not registered")
        return self._pool

    @property
    def uow(self) -> UnitOfWorkFactory:
        """Get UnitOfWork factory for transaction management."""
        if self._uow_factory is None:
            raise RuntimeError("UnitOfWorkFactory not initialized. Register pool first.")
        return self._uow_factory

    def get_from_context(self, context: ContextTypes.DEFAULT_TYPE, cls: Type[T]) -> T:
        """
        Get service from context.di (context injection).

        This is the primary way to get services in handlers.
        The DI middleware injects the container into context.di during initialization.

        Args:
            context: Telegram context
            cls: Service class to retrieve

        Returns:
            Service instance

        Raises:
            RuntimeError: If DI middleware not initialized
            KeyError: If service not registered
        """
        container = getattr(context, 'di', None)
        if container is None:
            raise RuntimeError(
                "DI middleware not initialized. "
                "Ensure register_di_middleware() is called in main.py"
            )
        return cast(T, container.get(cls))

    def get_registered_services(self) -> Set[Type[Any]]:
        """Get all registered service types."""
        return self._registry.get_registered_types()

    def __repr__(self) -> str:
        services = [t.__name__ for t in self.get_registered_services()]
        return f"Container(initialized={self._initialized}, services={services})"


# Global Container Instance
_container: Optional[Container] = None


def get_container() -> Container:
    """Get the global container instance."""
    global _container
    if _container is None:
        _container = Container()
    return _container


def init_container(pool: asyncpg.Pool) -> Container:
    """Initialize container with database pool and services."""
    global _container
    _container = Container()
    _container.register_pool(pool)
    return _container


def get_from_context(context: ContextTypes.DEFAULT_TYPE, cls: Type[T]) -> T:
    """
    Get service from context.di (convenience helper for handlers).

    This is the primary API for handlers to get services.
    The DI middleware injects the container into context.di.

    Example:
        user_service = get_from_context(context, UserService)
        user = await user_service.get_user(user_id)
    """
    container = getattr(context, 'di', None)
    if container is None:
        raise RuntimeError(
            "DI middleware not initialized. "
            "Ensure register_di_middleware() is called in main.py "
            "and application is built properly."
        )
    return cast(T, container.get(cls))


# Backwards Compatibility Aliases
Provider = Container
get_provider = get_container
init_provider = init_container


__all__ = [
    'Container',
    'ServiceRegistry',
    'Provider',
    'get_container',
    'init_container',
    'get_provider',
    'init_provider',
    'get_from_context',
]
