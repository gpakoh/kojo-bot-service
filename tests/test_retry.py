"""Tests for utils/retry.py."""
from unittest.mock import AsyncMock, patch

import pytest

from utils.retry import async_retry


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        decorated = async_retry(max_attempts=3)(mock_func)
        result = await decorated()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError(f"fail {call_count}")
            return "success"

        with patch('asyncio.sleep', new_callable=AsyncMock):
            decorated = async_retry(max_attempts=3, base_delay=0.01)(mock_func)
            result = await decorated()
            assert result == "success"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_attempts_raises(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            raise OSError("permanent failure")

        with patch('asyncio.sleep', new_callable=AsyncMock):
            decorated = async_retry(max_attempts=2, base_delay=0.01)(mock_func)
            with pytest.raises(OSError, match="permanent failure"):
                await decorated()
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_unmatched_exception(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("not in retry list")

        decorated = async_retry(max_attempts=3, base_delay=0.01, exceptions=(KeyError,))(mock_func)
        with pytest.raises(ValueError):
            await decorated()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_custom_exceptions_are_retried(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise KeyError("retry this")
            return "success"

        with patch('asyncio.sleep', new_callable=AsyncMock):
            decorated = async_retry(max_attempts=3, base_delay=0.01, exceptions=(KeyError,))(mock_func)
            result = await decorated()
            assert result == "success"

    @pytest.mark.asyncio
    async def test_max_delay_caps_exponential_backoff(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("fail")
            return "success"

        mock_sleep = AsyncMock()
        with patch('asyncio.sleep', mock_sleep):
            decorated = async_retry(max_attempts=3, base_delay=100.0, max_delay=5.0)(mock_func)
            result = await decorated()
            assert result == "success"
            # Both Retries Should Sleep At Max_delay=5.0, Not 100*2^(n-1)
            for call_args in mock_sleep.call_args_list:
                delay = call_args[0][0]
                assert delay == 5.0

    @pytest.mark.asyncio
    async def test_max_attempts_zero_returns_none(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        decorated = async_retry(max_attempts=0)(mock_func)
        result = await decorated()
        assert result is None
        assert call_count == 0

    def test_preserves_name(self) -> None:
        @async_retry()
        async def my_function() -> None:
            pass
        assert my_function.__name__ == "my_function"

    def test_preserves_wrapped(self) -> None:
        @async_retry()
        async def my_function() -> None:
            pass
        assert my_function.__wrapped__ is not None
        assert my_function.__wrapped__.__name__ == "my_function"

    @pytest.mark.asyncio
    async def test_sleep_called_with_increasing_delays(self) -> None:
        call_count = 0
        async def mock_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("fail")
            return "success"

        mock_sleep = AsyncMock()
        with patch('asyncio.sleep', mock_sleep):
            decorated = async_retry(max_attempts=3, base_delay=1.0, max_delay=30.0)(mock_func)
            await decorated()
            # Should Sleep For 1.0 Then 2.0 (exponential, Uncapped)
            assert mock_sleep.call_args_list[0][0][0] == 1.0
            assert mock_sleep.call_args_list[1][0][0] == 2.0
