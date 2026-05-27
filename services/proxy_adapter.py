# Services/proxy_adapter.py
# Адаптер для інтеграції proxypool с ботами

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

import httpx

from services.proxy_pool import ProxyServer, get_proxy_pool
from tg_bot.infrastructure.metrics import kojo_proxy_failover_count

logger = logging.getLogger(__name__)


class ProxyAdapter:
    """
    Адаптер для ботов - прозрачно переключает прокси при отказах.

    Использование:
    1. Получить httpx.Proxy: proxy = adapter.get_proxy_for_httpx()
    2. Создать client: httpx.AsyncClient(proxy=proxy)
    3. После успешного запроса: adapter.mark_success()
    4. После неудачного запроса: await adapter.handle_failure()
    """

    def __init__(self, bot_id: str = "default") -> None:
        self.bot_id = bot_id
        self.pool = get_proxy_pool(bot_id)
        self.current_proxy: Optional[ProxyServer] = None
        self._max_retries = 3
        self._retries = 0

    def get_proxy_for_httpx(self) -> Optional[httpx.Proxy]:
        """Возвращает httpx.Proxy без мутации os.environ."""
        if not self.current_proxy:
            return None
        return httpx.Proxy(url=self.current_proxy.url)

    async def async_set_proxy(self) -> Optional[ProxyServer]:
        """Асинхронно выбирает рабочий прокси из пула (с health-check)."""
        proxy = None
        try:
            proxy = await self.pool.get_working_proxy()
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"[ProxyAdapter/{self.bot_id}] async_set_proxy error: {e}")

        if proxy:
            self.current_proxy = proxy
            logger.info(f"🌐 [ProxyAdapter/{self.bot_id}] Выбран прокси: {proxy.full_name}")
        else:
            self.current_proxy = None
            logger.info(f"🌐 [ProxyAdapter/{self.bot_id}] Работаем напрямую.")
        return proxy

    async def mark_success(self) -> None:
        if self.current_proxy:
            await self.pool.mark_success(self.current_proxy)
            self._retries = 0

    async def mark_failure(self) -> None:
        if self.current_proxy:
            await self.pool.mark_failed(self.current_proxy)

    async def handle_failure(self) -> bool:
        await self.mark_failure()
        self._retries += 1

        if self._retries > self._max_retries:
            logger.warning(f"❌ [ProxyAdapter/{self.bot_id}] Превышен лимит попыток ({self._max_retries})")
            return False

        next_proxy = await self.pool.get_next_proxy(self.current_proxy)
        if next_proxy:
            self.current_proxy = next_proxy
            logger.info(
                f"🔄 [ProxyAdapter/{self.bot_id}] "
                f"Переключились на: {next_proxy.full_name} "
                f"(попытка {self._retries})"
            )
            # Increment Failover Metric
            kojo_proxy_failover_count.labels(bot_id=self.bot_id).inc()
            return True

        logger.warning(f"❌ [ProxyAdapter/{self.bot_id}] Нет доступных прокси")
        return False

    def get_status(self) -> dict[str, str | int | None]:
        return {
            "bot_id": self.bot_id,
            "current_proxy": self.current_proxy.full_name if self.current_proxy else None,
            "retries": self._retries,
            "failed_count": self.pool.get_failed_count(),
            "total_proxies": len(self.pool.proxies)
        }


class RequestMiddleware:
    """
    HTTP Request Middleware, которое инжектит прокси на уровне клиента.
    Инкапсулирует создание httpx.AsyncClient с актуальным прокси из ProxyAdapter.
    Автоматически обрабатывает HTTP-ошибки с переключением прокси.
    """

    def __init__(self, adapter: ProxyAdapter, timeout: float = 20.0) -> None:
        self.adapter = adapter
        self.timeout = timeout

    @asynccontextmanager
    async def client(self, timeout: Optional[float] = None, url: Optional[str] = None) -> AsyncIterator[httpx.AsyncClient]:
        proxy = None
        if url and ("localhost" in url or "127.0.0.1" in url):
            proxy = None
        else:
            proxy = self.adapter.get_proxy_for_httpx()
        effective_timeout = timeout if timeout is not None else self.timeout
        async with httpx.AsyncClient(timeout=effective_timeout, proxy=proxy) as client:  # type: ignore[call-arg]
            yield client

    async def post(
        self,
        url: str,
        payload: dict[str, object],
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_on: tuple[int, ...] = (500, 502, 503, 504)
    ) -> httpx.Response:
        """Выполняет POST с автоматическим переключением прокси при HTTP-ошибках."""
        effective_timeout = timeout if timeout is not None else self.timeout
        attempt = 0
        while True:
            attempt += 1
            await self.adapter.async_set_proxy()
            self.adapter._retries = 0

            async with self.client(timeout=effective_timeout, url=url) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code in retry_on and attempt < self.adapter._max_retries:
                    logger.warning(f"[RequestMiddleware] HTTP {response.status_code}, переключаю прокси (попытка {attempt})")  # noqa: E501
                    await self.adapter.handle_failure()
                    continue

                response.raise_for_status()
                await self.adapter.mark_success()
                return response

    async def get(
        self,
        url: str,
        params: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_on: tuple[int, ...] = (500, 502, 503, 504)
    ) -> httpx.Response:
        """Выполняет GET с автоматическим переключением прокси."""
        effective_timeout = timeout if timeout is not None else self.timeout
        attempt = 0
        while True:
            attempt += 1
            await self.adapter.async_set_proxy()
            self.adapter._retries = 0

            async with self.client(timeout=effective_timeout, url=url) as client:
                response = await client.get(url, params=params)

                if response.status_code in retry_on and attempt < self.adapter._max_retries:
                    logger.warning(f"[RequestMiddleware] HTTP {response.status_code}, переключаю прокси (попытка {attempt})")  # noqa: E501
                    await self.adapter.handle_failure()
                    continue

                response.raise_for_status()
                await self.adapter.mark_success()
                return response


_proxy_adapters: dict[str, ProxyAdapter] = {}
_middleware_cache: dict[str, RequestMiddleware] = {}


def get_proxy_adapter(bot_id: str = "default") -> ProxyAdapter:
    """Получить адаптер прокси для бота."""
    if bot_id not in _proxy_adapters:
        _proxy_adapters[bot_id] = ProxyAdapter(bot_id)
    return _proxy_adapters[bot_id]


def get_request_middleware(bot_id: str = "default", timeout: float = 20.0) -> RequestMiddleware:
    """Получить RequestMiddleware для бота (синглтон по bot_id + timeout)."""
    key = f"{bot_id}:{timeout}"
    if key not in _middleware_cache:
        _middleware_cache[key] = RequestMiddleware(get_proxy_adapter(bot_id), timeout)
    return _middleware_cache[key]


def clear_cache() -> None:
    """Очистить глобальные кэши. Использовать в тестах для изоляции."""
    _proxy_adapters.clear()
    _middleware_cache.clear()
