# Tg_bot/bot_services/delivery_service.py
import logging
import os
from typing import Any, Optional, cast

import httpx

from tg_bot.bot_services.base_integration import BaseIntegrationService

logger = logging.getLogger(__name__)

class DeliveryService(BaseIntegrationService):
    def __init__(self, quart_url: str, bot_id: str) -> None:
        super().__init__(quart_url, bot_id)
        self.map_url = os.getenv("WEBAPP_MAP_URL")
        self.yandex_key = os.getenv("YANDEX_MAPS_API_KEY", "")
        # Читаем дефолты из env
        self.default_weight = int(os.getenv("DEFAULT_WEIGHT_GRAMS", 500))
        # Считываем дни на сборку
        self.assembly_days = int(os.getenv("ORDER_ASSEMBLY_DAYS", 2))

    async def init_cdek_session_raw(self, user_id: int) -> Optional[str]:
        payload = {"user_id": user_id}
        try:
            response = await self._post_request("/api/delivery/session/init", payload)
            if response.status_code == 200:
                data = response.json()
                return cast(str | None, data.get("session_token"))
            logger.error(f"CDEK Init Error: {response.text}")
            return None
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"CDEK Init Error: {e}")
            return None

    async def get_user_choice(self, token: str) -> Optional[dict[str, Any]]:
        try:
            url = f"{self.base_url}/delivery/get-choice/{token}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return cast(dict[str, Any] | None, response.json())
            return None
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Get Choice Error: {e}")
            return None

    def calculate_cart_weight(self, cart: dict[str, Any], products_cache: dict[str, Any]) -> int:
        """
        Считает общий вес корзины в граммах.
        Если у товара нет варианта веса, берет дефолт из .env
        """
        total_weight = 0
        for p_id_str, item in cart.items():
            product = products_cache.get(p_id_str)
            qty = int(item['quantity'])

            weight = self.default_weight

            # Пробуем достать вес из варианта
            if product and product.variants:
                # Берем первый вариант (обычно он актуален для карточки)
                v_weight = product.variants[0].weight_grams
                if v_weight and v_weight > 0:
                    weight = v_weight

            total_weight += weight * qty

        logger.info(f"⚖️ Calculated cart weight: {total_weight}g")
        return total_weight


    async def calc_yandex_price_server_side(self, point_id: str, weight_grams: int) -> float:
        """
        Запрашивает расчет цены доставки у Integration Service для конкретной точки.
        """
        payload = {
            "point_id": point_id,
            "weight": weight_grams
        }
        try:
            # Используем существующий роут калькулятора
            response = await self._post_request("/api/delivery/yandex/calc", payload)
            if response.status_code == 200:
                data = response.json()
                return float(data.get("price", 0.0))
            else:
                logger.error(f"Yandex Server Calc Error: {response.text}")
                return 0.0
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Yandex Server Calc Exception: {e}")
            return 0.0
