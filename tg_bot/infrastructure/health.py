import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HealthCheck:
    """Проверка критических зависимостей бота."""

    def __init__(self) -> None:
        self._checks: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, check: Callable[..., Any]) -> None:
        self._checks[name] = check

    async def run(self) -> dict[str, Any]:
        results: dict[str, str] = {}
        all_ok = True
        for name, check in self._checks.items():
            try:
                if asyncio.iscoroutinefunction(check):
                    await check()
                else:
                    check()
                results[name] = "ok"
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                results[name] = f"fail: {e}"
                all_ok = False
                logger.warning(f"Health check '{name}' failed: {e}")
        return {"status": "ok" if all_ok else "degraded", "checks": results}


# Процесс-локальный — допустимо
_health = HealthCheck()


def get_health_check() -> HealthCheck:
    return _health
