# Tg_bot/bot_services/payment_service.py
import logging
from typing import Any, Optional, cast

# Импорт базового класса
from tg_bot.bot_services.base_integration import BaseIntegrationService

logger = logging.getLogger(__name__)

# Наследуемся от baseintegrationservice
class PaymentService(BaseIntegrationService):

    # Конструктор можно не писать, если он совпадает с базовым,
    # Но у нас в main.py передаются именованные аргументы, так что лучше оставить.
    def __init__(self, quart_url: str, bot_id: str, idempotency_store: Optional[Any] = None) -> None:
        super().__init__(quart_url, bot_id)
        self._idempotency = idempotency_store
        # Остальные поля (paykeeper_url) теперь не нужны здесь,
        # Так как они живут в integration service и пушатся туда отдельно.


    async def create_payment_url(self, order_id: int, total_amount: float, cart: dict[str, Any], products: dict[str, Any], user_fio: str, idempotency_key: str = "") -> str:
        """
        Формирует данные заказа и запрашивает платежную ссылку у Integration Service.
        """
        products_payload = {}
        for p_id, item in cart.items():
            product = products.get(str(p_id))
            if product:
                products_payload[str(p_id)] = {
                    "name": product.name,
                    "price": float(item['price']),
                    "quantity": int(item['quantity'])
                }

        # Idempotency Check
        if idempotency_key and self._idempotency:
            cached = await self._idempotency.check("payment:create", idempotency_key)
            if cached:
                if cached.get("status") == "completed":
                    logger.info("Idempotency hit for payment: %s", idempotency_key)
                    return cast(str, cached.get("payment_url", "#idempotent"))
                raise ValueError("Duplicate payment request in progress")
            await self._idempotency.start("payment:create", idempotency_key)

        payload = {
            "order_id": order_id,
            "total_amount": total_amount,
            "user_id": str(order_id), # Технический ID (можно оставить ID заказа)
            "client_fio": user_fio,   # ФИО пользователя для отображения в банке
            "products": products_payload,
            "idempotency_key": idempotency_key,
        }

        try:
            # Используем метод базового класса для отправки в integration service
            response = await self._post_request("/api/create-payment-form", payload)

            if response.status_code == 200:
                data = response.json()
                payment_url = data.get("payment_url") or "#error_no_link"
                # Idempotency Completion
                if idempotency_key and self._idempotency:
                    await self._idempotency.complete(
                        "payment:create", idempotency_key,
                        {"status": "completed", "payment_url": payment_url, "order_id": order_id}
                    )
                return payment_url
            else:
                logger.error(f"Pay error: {response.text}")
                return "#error_http"
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Pay exception: {e}")
            return "#error_exception"
