"""Tests for tg_bot/application/queries/base.py — coverage gaps."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.application.queries.base import PaginatedResult, PaginationParams, ReadRepository


class TestPaginationParams:
    def test_offset_page_1(self) -> None:
        p = PaginationParams(page=1, page_size=20)
        assert p.offset == 0

    def test_offset_page_3(self) -> None:
        p = PaginationParams(page=3, page_size=10)
        assert p.offset == 20


class TestPaginatedResult:
    def test_total_pages_exact(self) -> None:
        r = PaginatedResult(items=[], total=40, page=1, page_size=20)
        assert r.total_pages == 2

    def test_total_pages_partial(self) -> None:
        r = PaginatedResult(items=[], total=41, page=1, page_size=20)
        assert r.total_pages == 3

    def test_has_next_true(self) -> None:
        r = PaginatedResult(items=[], total=50, page=1, page_size=20)
        assert r.has_next is True
        assert r.has_prev is False

    def test_has_prev_true(self) -> None:
        r = PaginatedResult(items=[], total=50, page=2, page_size=20)
        assert r.has_prev is True
        assert r.has_next is True

    def test_has_next_false_last_page(self) -> None:
        r = PaginatedResult(items=[], total=15, page=2, page_size=10)
        assert r.has_next is False
        assert r.has_prev is True

    def test_both_false_empty(self) -> None:
        r = PaginatedResult(items=[], total=0, page=1, page_size=10)
        assert r.has_next is False
        assert r.has_prev is False


class TestReadRepository:
    @pytest.mark.asyncio
    async def test_fetch_all(self) -> None:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        repo = ReadRepository(mock_pool)
        result = await repo.fetch_all("SELECT 1")
        assert len(result) == 2
        assert result[0] == {"id": 1}

    @pytest.mark.asyncio
    async def test_fetch_one_found(self) -> None:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": 1})
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        repo = ReadRepository(mock_pool)
        result = await repo.fetch_one("SELECT 1")
        assert result == {"id": 1}

    @pytest.mark.asyncio
    async def test_fetch_one_none(self) -> None:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        repo = ReadRepository(mock_pool)
        result = await repo.fetch_one("SELECT 1")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_val(self) -> None:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=42)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        repo = ReadRepository(mock_pool)
        result = await repo.fetch_val("SELECT 1")
        assert result == 42
