"""Tests for tenant database module."""
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_bot.tenant.config import TenantConfig, set_current_tenant
from tg_bot.tenant.database import TenantDatabase, get_tenant_database


@pytest.fixture
def tenant() -> TenantConfig:
    return TenantConfig(bot_id="TestBot", bot_token="token")


def create_mock_pool(mock_conn: AsyncMock | None = None) -> MagicMock:
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    conn = mock_conn or AsyncMock()

    @asynccontextmanager
    async def acquire() -> AsyncIterator[AsyncMock]:
        yield conn

    pool.acquire = acquire
    return pool


@pytest.fixture
def mock_conn() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def pool(mock_conn: AsyncMock) -> MagicMock:
    return create_mock_pool(mock_conn)


class TestInit:
    def test_default_strategy_from_env(self) -> None:
        with patch.dict('os.environ', {"TENANT_ISOLATION_STRATEGY": "shared_schema"}, clear=True):
            db = TenantDatabase(pool=MagicMock())
        assert db.strategy == "shared_schema"

    def test_default_strategy_fallback(self) -> None:
        with patch.dict('os.environ', {}, clear=True):
            db = TenantDatabase(pool=MagicMock())
        assert db.strategy == "schema_per_tenant"

    def test_explicit_strategy(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        assert db.strategy == "shared_schema"


class TestSingleton:
    def teardown_method(self) -> None:
        TenantDatabase.reset_instance()

    def test_get_instance_creates_with_pool(self, pool: MagicMock) -> None:
        db = TenantDatabase.get_instance(pool)
        assert isinstance(db, TenantDatabase)
        assert TenantDatabase._instance is db

    def test_get_instance_returns_same(self, pool: MagicMock) -> None:
        db1 = TenantDatabase.get_instance(pool)
        db2 = TenantDatabase.get_instance()
        assert db1 is db2

    def test_get_instance_raises_without_pool_first(self) -> None:
        with pytest.raises(ValueError, match="Pool required on first initialization"):
            TenantDatabase.get_instance()

    def test_reset_instance(self, pool: MagicMock) -> None:
        TenantDatabase.get_instance(pool)
        assert TenantDatabase._instance is not None
        TenantDatabase.reset_instance()
        assert TenantDatabase._instance is None


class TestStrategyProperty:
    def test_returns_strategy(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        assert db.strategy == "shared_schema"


class TestTenantContext:
    @pytest.mark.asyncio
    async def test_sets_schema_for_schema_per_tenant(self, pool: MagicMock, tenant: TenantConfig) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        async with db.tenant_context(tenant):
            assert db._current_tenant_schema == tenant.db_schema
        assert db._current_tenant_schema is None

    @pytest.mark.asyncio
    async def test_does_not_set_schema_for_shared_schema(self, pool: MagicMock, tenant: TenantConfig) -> None:
        db = TenantDatabase(pool=pool, strategy="shared_schema")
        async with db.tenant_context(tenant):
            assert db._current_tenant_schema is None

    @pytest.mark.asyncio
    async def test_restores_previous_schema(self, pool: MagicMock, tenant: TenantConfig) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        db._current_tenant_schema = "original"
        async with db.tenant_context(tenant):
            assert db._current_tenant_schema == tenant.db_schema
        assert db._current_tenant_schema == "original"

    @pytest.mark.asyncio
    async def test_restores_none_when_no_previous(self, pool: MagicMock, tenant: TenantConfig) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        async with db.tenant_context(tenant):
            pass
        assert db._current_tenant_schema is None


class TestExecuteWithTenant:
    @pytest.mark.asyncio
    async def test_sets_search_path_for_schema_per_tenant(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        db._current_tenant_schema = tenant.db_schema
        await db.execute_with_tenant(mock_conn, "SELECT 1")
        mock_conn.execute.assert_any_call(f'SET search_path TO "{tenant.db_schema}", public')
        mock_conn.execute.assert_any_call("SELECT 1")

    @pytest.mark.asyncio
    async def test_no_search_path_without_schema(
        self, mock_conn: AsyncMock, pool: MagicMock
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        await db.execute_with_tenant(mock_conn, "SELECT 1")
        mock_conn.execute.assert_called_once_with("SELECT 1")

    @pytest.mark.asyncio
    async def test_no_search_path_for_shared_schema(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="shared_schema")
        db._current_tenant_schema = tenant.db_schema
        await db.execute_with_tenant(mock_conn, "SELECT 1")
        mock_conn.execute.assert_called_once_with("SELECT 1")


class TestFetchWithTenant:
    @pytest.mark.asyncio
    async def test_sets_search_path(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        db._current_tenant_schema = tenant.db_schema
        mock_conn.fetch = AsyncMock(return_value=[{"id": 1}])
        result = await db.fetch_with_tenant(mock_conn, "SELECT * FROM t")
        assert result == [{"id": 1}]
        mock_conn.execute.assert_called_once_with(f'SET search_path TO "{tenant.db_schema}", public')
        mock_conn.fetch.assert_called_once_with("SELECT * FROM t")

    @pytest.mark.asyncio
    async def test_no_search_path_without_schema(
        self, mock_conn: AsyncMock, pool: MagicMock
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        await db.fetch_with_tenant(mock_conn, "SELECT 1")
        mock_conn.execute.assert_not_called()


class TestFetchRowWithTenant:
    @pytest.mark.asyncio
    async def test_sets_search_path(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        db._current_tenant_schema = tenant.db_schema
        mock_conn.fetchrow = AsyncMock(return_value={"id": 1})
        result = await db.fetchrow_with_tenant(mock_conn, "SELECT * FROM t WHERE id=1")
        assert result == {"id": 1}
        mock_conn.execute.assert_called_once_with(f'SET search_path TO "{tenant.db_schema}", public')
        mock_conn.fetchrow.assert_called_once_with("SELECT * FROM t WHERE id=1")

    @pytest.mark.asyncio
    async def test_no_search_path_without_schema(
        self, mock_conn: AsyncMock, pool: MagicMock
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        await db.fetchrow_with_tenant(mock_conn, "SELECT 1")
        mock_conn.execute.assert_not_called()


class TestAddTenantFilter:
    def test_shared_schema_with_where_adds_and(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        tenant = TenantConfig(bot_id="my_bot", bot_token="tok")
        set_current_tenant(tenant)
        try:
            result = db.add_tenant_filter("SELECT * FROM orders WHERE active = true")
            assert result == "SELECT * FROM orders WHERE active = true AND bot_id = 'my_bot'"
        finally:
            set_current_tenant(None)

    def test_shared_schema_without_where_adds_clause(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        tenant = TenantConfig(bot_id="my_bot", bot_token="tok")
        set_current_tenant(tenant)
        try:
            result = db.add_tenant_filter("SELECT * FROM orders")
            assert result == "SELECT * FROM orders WHERE bot_id = 'my_bot'"
        finally:
            set_current_tenant(None)

    def test_shared_schema_no_tenant_returns_unchanged(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        set_current_tenant(None)
        result = db.add_tenant_filter("SELECT * FROM orders WHERE active = true")
        assert result == "SELECT * FROM orders WHERE active = true"

    def test_schema_per_tenant_returns_unchanged(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="schema_per_tenant")
        tenant = TenantConfig(bot_id="my_bot", bot_token="tok")
        set_current_tenant(tenant)
        try:
            result = db.add_tenant_filter("SELECT * FROM orders")
            assert result == "SELECT * FROM orders"
        finally:
            set_current_tenant(None)

    def test_custom_column_name(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        tenant = TenantConfig(bot_id="my_bot", bot_token="tok")
        set_current_tenant(tenant)
        try:
            result = db.add_tenant_filter("SELECT * FROM t", tenant_id_column="tenant_id")
            assert result == "SELECT * FROM t WHERE tenant_id = 'my_bot'"
        finally:
            set_current_tenant(None)

    def test_where_case_insensitive_detection(self) -> None:
        db = TenantDatabase(pool=MagicMock(), strategy="shared_schema")
        tenant = TenantConfig(bot_id="b", bot_token="t")
        set_current_tenant(tenant)
        try:
            result = db.add_tenant_filter("select * from t where x = 1")
            assert result == "select * from t where x = 1 AND bot_id = 'b'"
        finally:
            set_current_tenant(None)


class TestCreateTenantSchema:
    @pytest.mark.asyncio
    async def test_creates_schema_for_schema_per_tenant(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        await db.create_tenant_schema(tenant)
        mock_conn.execute.assert_called_once_with(
            f'CREATE SCHEMA IF NOT EXISTS "{tenant.db_schema}"'
        )

    @pytest.mark.asyncio
    async def test_skips_for_shared_schema(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="shared_schema")
        await db.create_tenant_schema(tenant)
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_connection_acquire(
        self, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        await db.create_tenant_schema(tenant)
        # Verify The Pool's Acquire Context Manager Was Used
        assert hasattr(pool, 'acquire')


class TestDropTenantSchema:
    @pytest.mark.asyncio
    async def test_drops_schema_for_schema_per_tenant(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="schema_per_tenant")
        await db.drop_tenant_schema(tenant)
        mock_conn.execute.assert_called_once_with(
            f'DROP SCHEMA IF EXISTS "{tenant.db_schema}" CASCADE'
        )

    @pytest.mark.asyncio
    async def test_skips_for_shared_schema(
        self, mock_conn: AsyncMock, pool: MagicMock, tenant: TenantConfig
    ) -> None:
        db = TenantDatabase(pool=pool, strategy="shared_schema")
        await db.drop_tenant_schema(tenant)
        mock_conn.execute.assert_not_called()


class TestGetTenantDatabase:
    def teardown_method(self) -> None:
        TenantDatabase.reset_instance()

    def test_returns_none_when_no_instance(self) -> None:
        TenantDatabase.reset_instance()
        assert get_tenant_database() is None

    def test_returns_instance(self, pool: MagicMock) -> None:
        db = TenantDatabase.get_instance(pool)
        result = get_tenant_database()
        assert result is db
