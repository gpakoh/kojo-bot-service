# Tg_bot/bot_services/base_integration.py
import logging
from typing import Any, cast

import httpx

from services.proxy_adapter import get_proxy_adapter
from utils.config_pusher import push_config_to_integration

logger = logging.getLogger(__name__)

class BaseIntegrationService:
    """
    Базовый класс для взаимодействия с Integration Service.
    Реализует логику автоматического восстановления конфига (Retry pattern).
    Поддерживает автоматическое переключение прокси при отказах.
    """
    def __init__(self, quart_url: str, bot_id: str) -> None:
        self.base_url = quart_url.rstrip('/')
        self.bot_id = bot_id
        self.proxy_adapter = get_proxy_adapter(bot_id)
        self._max_retries = 3

    async def _post_request(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        """Выполняет POST запрос с автоматическим failover прокси."""
        url = f"{self.base_url}{endpoint}"

        if "bot_id" not in payload:
            payload["bot_id"] = self.bot_id

        await self.proxy_adapter.async_set_proxy()
        self.proxy_adapter._retries = 0

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(url, json=payload)

                    if response.status_code == 412:
                        logger.warning(f"Integration Service не знает конфиг для '{self.bot_id}'. Восстановление...")
                        await push_config_to_integration()
                        logger.info("Повторяем запрос к integration service...")
                        response = await client.post(url, json=payload)

                    await self.proxy_adapter.mark_success()
                    return response

            except httpx.RequestError as e:
                logger.error(f"Ошибка сети при запросе к {url} (попытка {attempt + 1}): {e}")

                if attempt < self._max_retries - 1:
                    if not await self.proxy_adapter.handle_failure():
                        break
                    logger.info("Повторяем с новым прокси...")
                else:
                    await self.proxy_adapter.mark_failure()
                    return httpx.Response(status_code=503, text=str(e))

        return httpx.Response(status_code=503, text="No proxies available")


    async def find_yandex_station(self) -> dict[str, Any] | None:
        """
        Запрашивает у Integration Service поиск лучшего склада.
        """
        response = await self._post_request("/api/delivery/yandex/find_station", {})

        if response.status_code == 200:
            return cast(dict[str, Any] | None, response.json())
        else:
            logger.error(f"Error finding station: {response.status_code} {response.text}")
            return None
