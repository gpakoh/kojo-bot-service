# Services/proxy_pool.py
# Система автоматического переключения прокси при отказах

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, cast
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ProxyServer:
    host: str
    port: int
    name: str = ""
    scheme: str | None = None
    avg_response_time: float = 0.0
    success_count: int = 0
    failure_count: int = 0

    @property
    def url(self) -> str:
        # If Scheme Explicitly Provided, Use It. Otherwise Infer By Port.
        scheme = self.scheme
        if not scheme:
            # Ports 20170 And 20190 Are Socks5 By Convention; Others Are Http
            if self.port in (20170, 20190):
                scheme = "socks5"
            else:
                scheme = "http"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def full_name(self) -> str:
        return self.name or f"{self.host}:{self.port}"

    @property
    def failure_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.failure_count / total if total > 0 else 0.0


class ProxyPool:
    """
    Пул прокси серверов с автоматическим failover.
    Конфигурация через HierarchicalConfig.
    """

    def __init__(self, bot_id: str = "default", config: dict[str, object] | None = None) -> None:
        self.bot_id = bot_id
        self.config = config or {}
        self.proxies: list[ProxyServer] = []
        self.failed_proxies: dict[str, datetime] = {}
        self.current_index: int = 0
        self._cooldown_seconds = cast(int, self.config.get("proxy_cooldown_seconds", 300))
        self._health_check_interval = cast(int, self.config.get("proxy_health_check_interval", 60))
        self._last_health_check = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = asyncio.Lock()

        # Metrics
        self._total_failovers: int = 0
        self._total_requests: int = 0

        self._load_proxies()

    def _load_proxies(self) -> None:
        """Загружает прокси из конфигурации."""
        primary_pool = cast(str, self.config.get("proxy_pool", ""))
        secondary_pool = cast(str, self.config.get("proxy_pool_2", ""))
        tertiary_pool = cast(str, self.config.get("proxy_pool_3", ""))

        all_pools = []
        if primary_pool:
            all_pools.extend(primary_pool.split(","))
        if secondary_pool:
            all_pools.extend(secondary_pool.split(","))
        if tertiary_pool:
            all_pools.extend(tertiary_pool.split(","))

        for proxy_str in all_pools:
            proxy_str = proxy_str.strip()
            if not proxy_str:
                continue

            host = None
            port = None
            scheme = None

            # If Scheme Is Present, Use Urlparse To Extract Host/port
            if "//" in proxy_str or "://" in proxy_str:
                p = urlparse(proxy_str)
                scheme = p.scheme or None
                host = p.hostname
                port = p.port
            elif ":" in proxy_str:
                host, port_str = proxy_str.rsplit(":", 1)
                try:
                    port = int(port_str)
                except ValueError:
                    port = None

            if not host or not port:
                logger.warning(f"⚠️ [ProxyPool/{self.bot_id}] Пропущен (неверный формат): {proxy_str}")
                continue

            # If Scheme Not Provided, Infer From Port (socks5 For Specific Ports)
            if not scheme:
                if port in (20170, 20190):
                    scheme = "socks5"
                else:
                    scheme = "http"

            self.proxies.append(ProxyServer(host=host, port=port, name=f"pool-{len(self.proxies)+1}", scheme=scheme))
            logger.info(f"✅ [ProxyPool/{self.bot_id}] Добавлен прокси: {self.proxies[-1].full_name}")

        if not self.proxies:
            logger.warning(f"⚠️ [ProxyPool/{self.bot_id}] Нет рабочих прокси в конфиге")
        else:
            logger.info(f"📦 [ProxyPool/{self.bot_id}] Загружено {len(self.proxies)} прокси")

    async def get_working_proxy(self) -> Optional[ProxyServer]:
        """Получить первый доступный прокси (с ротацией)."""
        async with self._lock:
            if not self.proxies:
                return None

            now = datetime.now(timezone.utc)

            # Периодическая проверка здоровья прокси
            if (now - self._last_health_check).total_seconds() > self._health_check_interval:
                await self._check_proxies_health()
                self._last_health_check = now

            # Перебираем все прокси начиная с текущего
            attempts = len(self.proxies)
            for i in range(attempts):
                idx = (self.current_index + i) % len(self.proxies)
                proxy = self.proxies[idx]

                # Проверяем кулдаун
                if proxy.url in self.failed_proxies:
                    failed_time = self.failed_proxies[proxy.url]
                    if (now - failed_time).total_seconds() < self._cooldown_seconds:
                        continue
                    else:
                        # Кулдаун прошёл, пробуем снова
                        del self.failed_proxies[proxy.url]
                        logger.info(f"🔄 [ProxyPool/{self.bot_id}] Прокси {proxy.full_name} вышел из кулдауна")

                # Проверяем доступность
                if await self._check_proxy(proxy):
                    self.current_index = idx
                    logger.info(f"🌐 [ProxyPool/{self.bot_id}] Используем прокси: {proxy.full_name}")
                    return proxy

            logger.warning(f"⚠️ [ProxyPool/{self.bot_id}] нет доступных прокси")
            return None

    async def get_next_proxy(self, current: Optional[ProxyServer] = None) -> Optional[ProxyServer]:
        """Получить следующий рабочий прокси (для перебора при ошибке)."""
        async with self._lock:
            if not self.proxies:
                return None

            now = datetime.now(timezone.utc)
            start_idx = 0
            if current:
                try:
                    start_idx = self.proxies.index(current) + 1
                except ValueError as e:
                    logger.warning(f"[databases/kojo/services/proxy_pool.py] ValueError: {e}")

            # Перебираем все кроме текущего
            for i in range(len(self.proxies) - 1):
                idx = (start_idx + i) % len(self.proxies)
                proxy = self.proxies[idx]

                if proxy == current:
                    continue

                if proxy.url in self.failed_proxies:
                    failed_time = self.failed_proxies[proxy.url]
                    if (now - failed_time).total_seconds() < self._cooldown_seconds:
                        continue
                    else:
                        del self.failed_proxies[proxy.url]

                if await self._check_proxy(proxy):
                    self._total_failovers += 1
                    logger.info(f"🌐 [ProxyPool/{self.bot_id}] Следующий прокси: {proxy.full_name}")
                    return proxy

            return None

    async def mark_failed(self, proxy: ProxyServer) -> None:
        """Отметить прокси как недоступный."""
        async with self._lock:
            self.failed_proxies[proxy.url] = datetime.now(timezone.utc)
            proxy.failure_count += 1
            logger.warning(f"❌ [ProxyPool/{self.bot_id}] Прокси {proxy.full_name} отмечен как недоступный")

    async def mark_success(self, proxy: ProxyServer) -> None:
        """Отметить прокси как успешный."""
        async with self._lock:
            if proxy.url in self.failed_proxies:
                del self.failed_proxies[proxy.url]
            proxy.success_count += 1
            logger.info(f"✅ [ProxyPool/{self.bot_id}] Прокси {proxy.full_name} работает")

    async def record_response_time(self, proxy: ProxyServer, response_time: float) -> None:
        """Записать время отклика прокси для метрик."""
        if proxy.avg_response_time == 0:
            proxy.avg_response_time = response_time
        else:
            # Exponential Moving Average
            proxy.avg_response_time = 0.7 * proxy.avg_response_time + 0.3 * response_time

    async def _check_proxy(self, proxy: ProxyServer, timeout: float = 3.0) -> bool:
        """Проверяет доступность прокси простым TCP-подключением.

        Используем TCP проверку, т.к. SOCKS-прокси не ответят на HTTP GET.
        """
        try:
            # Try To Establish A TCP Connection To The Proxy Port
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(proxy.host, proxy.port),
                timeout=timeout
            )
            # CRITICAL: Always Close Writer To Prevent Resource Leak
            writer.close()
            try:
                await writer.wait_closed()
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"[databases/kojo/services/proxy_pool.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")
            return True
        except asyncio.TimeoutError:
            logger.debug(f"⏱️ [ProxyPool/{self.bot_id}] {proxy.full_name} timeout")
            return False
        except ConnectionRefusedError:
            logger.debug(f"🚫 [ProxyPool/{self.bot_id}] {proxy.full_name} connection refused")
            return False
        except OSError as e:
            logger.debug(f"❌ [ProxyPool/{self.bot_id}] {proxy.full_name} OS error: {e}")
            return False
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"⚠️ [ProxyPool/{self.bot_id}] {proxy.full_name} check failed: {e}")
            return False

    async def _check_proxies_health(self) -> None:
        """Проверяет здоровье всех прокси."""
        logger.info(f"🔍 [ProxyPool/{self.bot_id}] проверка здоровья прокси...")
        tasks = [self._check_proxy(p) for p in self.proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for proxy, result in zip(self.proxies, results):
            if isinstance(result, Exception) or not result:
                logger.warning(f"⚠️ [ProxyPool/{self.bot_id}] {proxy.full_name} недоступен")
            else:
                if proxy.url in self.failed_proxies:
                    logger.info(f"✅ [ProxyPool/{self.bot_id}] {proxy.full_name} восстановлен")
                    del self.failed_proxies[proxy.url]

    def get_all_proxies(self) -> list[ProxyServer]:
        """Получить все прокси."""
        return self.proxies.copy()

    def get_failed_count(self) -> int:
        """Получить количество недоступных прокси."""
        return len(self.failed_proxies)

    def get_metrics(self) -> dict[str, object]:
        """Get pool metrics."""
        return {
            "total_proxies": len(self.proxies),
            "failed_proxies": len(self.failed_proxies),
            "total_failovers": self._total_failovers,
            "total_requests": self._total_requests,
            "proxies": [
                {
                    "name": p.full_name,
                    "avg_response_time": round(p.avg_response_time, 3),
                    "success_count": p.success_count,
                    "failure_count": p.failure_count,
                    "failure_rate": round(p.failure_rate, 3),
                }
                for p in self.proxies
            ]
        }

    def record_request(self) -> None:
        """Record a request for metrics."""
        self._total_requests += 1


# Global Pool Registry With TTL Cleanup
_proxy_pools: dict[str, ProxyPool] = {}
_proxy_pool_timestamps: dict[str, datetime] = {}
_POOL_TTL_SECONDS = 3600  # 1 hour


def _cleanup_stale_pools() -> None:
    """Remove pools that haven't been accessed for >1 hour."""
    now = datetime.now(timezone.utc)
    stale = [
        bot_id for bot_id, ts in _proxy_pool_timestamps.items()
        if (now - ts).total_seconds() > _POOL_TTL_SECONDS
    ]
    for bot_id in stale:
        _proxy_pools.pop(bot_id, None)
        _proxy_pool_timestamps.pop(bot_id, None)
        logger.info(f"🧹 [ProxyPool] Cleaned up stale pool: {bot_id}")


def get_proxy_pool(bot_id: str = "default") -> ProxyPool:
    """Получить пул прокси для бота."""
    import os

    _cleanup_stale_pools()

    if bot_id not in _proxy_pools:
        # Clean Fallback To Env Vars, No Dependency On Telegram Context
        env_config: dict[str, object] = {
            "proxy_pool": os.environ.get("PROXY_POOL", ""),
            "proxy_pool_2": os.environ.get("PROXY_POOL_2", ""),
            "proxy_pool_3": os.environ.get("PROXY_POOL_3", ""),
            "proxy_cooldown_seconds": int(os.environ.get("PROXY_COOLDOWN_SECONDS", "300")),
            "proxy_health_check_interval": int(os.environ.get("PROXY_HEALTH_CHECK_INTERVAL", "60")),
        }
        _proxy_pools[bot_id] = ProxyPool(bot_id, env_config)
        logger.info(f"ProxyPool: created from env vars for {bot_id}")

    _proxy_pool_timestamps[bot_id] = datetime.now(timezone.utc)
    return _proxy_pools[bot_id]


def clear_all_pools() -> None:
    """Clear all proxy pools. Use in tests for isolation."""
    _proxy_pools.clear()
    _proxy_pool_timestamps.clear()
