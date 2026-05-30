"""Tests for DI provider — tenant-aware connection wiring."""
from unittest.mock import MagicMock

import pytest

from tg_bot.bot_services.user_service import UserService
from tg_bot.di.provider import Container, init_container
from tg_bot.infrastructure.database import DatabaseManager


def test_init_container_creates_db_manager() -> None:
    pool = MagicMock()
    container = init_container(pool)

    assert isinstance(container, Container)
    assert isinstance(container.db_manager, DatabaseManager)
    assert container.db_manager._pool is pool


def test_container_db_manager_property_after_register_pool() -> None:
    pool = MagicMock()
    container = Container()
    container.register_pool(pool)

    assert isinstance(container.db_manager, DatabaseManager)


def test_container_db_manager_raises_without_pool() -> None:
    container = Container()

    with pytest.raises(RuntimeError, match="register_pool"):
        _ = container.db_manager


def test_di_container_can_create_user_service_with_db_manager() -> None:
    pool = MagicMock()
    container = init_container(pool)

    user_service = UserService(pool, db_manager=container.db_manager)
    container.register_singleton(UserService, user_service)

    resolved = container.get(UserService)
    assert resolved.db_manager is container.db_manager
