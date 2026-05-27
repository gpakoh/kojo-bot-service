# Tg_bot/utils/config_pusher.py
import logging
from typing import Any, Optional
from urllib.parse import urlparse

import asyncpg

logger = logging.getLogger(__name__)


async def push_config_to_integration(
    pool: Optional[asyncpg.Pool] = None,
    app_config: Any = None
) -> None:
    """
    Отправляет настройки бота в Integration Service.
    Приоритет: app_config (Redis/БД) > Переменные окружения (.env).
    """
    integration_url: Optional[str] = None
    if app_config:
        integration_url = await app_config.get("INTEGRATION_SERVER_URL")
    if not integration_url:
        import os
        integration_url = os.getenv("INTEGRATION_SERVER_URL")

    if not integration_url:
        logger.warning("Integration_server_url не задан. синхронизация пропущена.")
        return

    webhook_public: Optional[str] = None
    if app_config:
        webhook_public = await app_config.get("WEBHOOK_PUBLIC_URL")
    if not webhook_public:
        import os
        webhook_public = os.getenv("WEBHOOK_PUBLIC_URL", "")

    bot_domain = ""
    if webhook_public:
        try:
            parsed = urlparse(webhook_public)
            bot_domain = f"{parsed.scheme}://{parsed.netloc}"
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"[databases/kojo/utils/config_pusher.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")

    async def get_config(key: str, default: str = "") -> str:
        if app_config:
            val: Any = await app_config.get(key)
            if val is not None:
                return str(val)
        import os
        return os.getenv(key, default)

    config_data: dict[str, object] = {
        "bot_id": await get_config("BOT_ID_FOR_QUART"),
        "cdek_client_id": await get_config("CDEK_CLIENT_ID"),
        "cdek_client_secret": await get_config("CDEK_CLIENT_SECRET"),
        "yandex_maps_api_key": await get_config("YANDEX_MAPS_API_KEY"),
        "paykeeper_base_url": await get_config("PAYKEEPER_BASE_URL"),
        "paykeeper_secret_seed": await get_config("PAYKEEPER_SECRET_SEED"),
        "bot_internal_webhook_url": await get_config("MY_INTERNAL_URL"),
        "webhook_secret_token": await get_config("WEBHOOK_SECRET_TOKEN"),
        "bot_domain": bot_domain,
        "yandex_token": await get_config("YANDEX_CLIENT_SECRET"),
        "shop_lat": await get_config("SHOP_LATITUDE"),
        "shop_lon": await get_config("SHOP_LONGITUDE"),
        "shop_address": await get_config("SHOP_ADDRESS"),
        "shop_phone": await get_config("SHOP_PHONE"),
        "shop_name": await get_config("SHOP_NAME", "Магазин"),
        "platform_station_id": await get_config("YANDEX_STATION_ID"),
    }

    if pool:
        try:
            db_station_id = await pool.fetchval("SELECT value FROM bot_settings WHERE key = 'yandex_station_id'")
            if db_station_id:
                logger.info(f"⚙️ Используем Station ID из базы данных: {db_station_id}")
                config_data["platform_station_id"] = db_station_id
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Ошибка чтения настроек из БД: {e}")

    target_url = f"{integration_url}/api/internal/config"

    try:
        from tg_bot.http_client import get_http_client
        client = get_http_client()
        resp = await client.post(target_url, config_data)
        if resp.status_code == 200:
            logger.info("✅ конфигурация успешно принята integration service.")
        else:
            logger.error(f"❌ Ошибка отправки конфига: {resp.status_code} {resp.text}")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"❌ Не удалось отправить конфиг: {e}")
