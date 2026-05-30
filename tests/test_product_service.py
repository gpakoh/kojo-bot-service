from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.bot_services.product_service import ProductService
from tg_bot.tenant.config import set_current_tenant


@pytest.mark.asyncio
async def test_uses_tenant_connection_when_tenant_is_set():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])

    pool = MagicMock()
    pool.acquire = MagicMock()

    class DummyDbManager:
        def __init__(self):
            self.called = False
            self.seen_tenant_id = None

        @asynccontextmanager
        async def tenant_connection(self, tenant_id):
            self.called = True
            self.seen_tenant_id = tenant_id
            yield conn

    db_manager = DummyDbManager()
    service = ProductService(pool, db_manager=db_manager)

    set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
    try:
        result = await service.get_product_by_id(123)
    finally:
        set_current_tenant(None)

    assert result is None
    assert db_manager.called is True
    assert db_manager.seen_tenant_id == "kojo-test"
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_pool_when_no_tenant():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire())

    db_manager = MagicMock()
    db_manager.tenant_connection = MagicMock()

    service = ProductService(pool, db_manager=db_manager)

    set_current_tenant(None)

    result = await service.get_product_by_id(123)

    assert result is None
    pool.acquire.assert_called_once()
    db_manager.tenant_connection.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_pool_when_db_manager_missing():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire())

    service = ProductService(pool, db_manager=None)

    set_current_tenant(SimpleNamespace(bot_id="kojo-test"))
    try:
        result = await service.get_product_by_id(123)
    finally:
        set_current_tenant(None)

    assert result is None
    pool.acquire.assert_called_once()
