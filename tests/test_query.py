# Tests/test_query.py
# Tests For Sqlalchemy Core Query Builders In Query.py
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestQueryBuilders:
    @pytest.mark.asyncio
    async def test_search_similarity_threshold_logic(self) -> Any:
        from tg_bot.bot_services.query import search_similarity

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mock_engine = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect = MagicMock(return_value=mock_cm)

        await search_similarity(mock_engine, "test", "test", 0.5)

        assert mock_conn.execute.call_count == 2
        first_call = mock_conn.execute.call_args_list[0]
        executed_stmt = first_call[0][0]

        assert "set_config" in str(executed_stmt)

    @pytest.mark.asyncio
    async def test_search_similarity_short_query_uses_lower_threshold(self) -> Any:
        from tg_bot.bot_services.query import search_similarity

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect = MagicMock(return_value=mock_cm)

        await search_similarity(mock_engine, "test", "ab", 0.5)

        assert mock_conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_search_similarity_medium_query_uses_mid_threshold(self) -> Any:
        from tg_bot.bot_services.query import search_similarity

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect = MagicMock(return_value=mock_cm)

        await search_similarity(mock_engine, "test", "abcde", 0.5)

        assert mock_conn.execute.call_count == 2


class TestTables:
    def test_products_table_defined(self) -> Any:
        from tg_bot.bot_services.tables import products
        assert products is not None
        assert "id" in products.columns
        assert "name" in products.columns
        assert "is_available" in products.columns

    def test_product_variants_defined(self) -> Any:
        from tg_bot.bot_services.tables import product_variants
        assert product_variants is not None
        assert "product_id" in product_variants.columns
        assert "price" in product_variants.columns

    def test_users_table_defined(self) -> Any:
        from tg_bot.bot_services.tables import users
        assert users is not None
        assert "telegram_id" in users.columns

    def test_orders_table_defined(self) -> Any:
        from tg_bot.bot_services.tables import orders
        assert orders is not None
        assert "user_id" in orders.columns
        assert "total_amount" in orders.columns

    def test_settings_table_defined(self) -> Any:
        from tg_bot.bot_services.tables import settings
        assert settings is not None
        assert settings.columns["key"].primary_key
