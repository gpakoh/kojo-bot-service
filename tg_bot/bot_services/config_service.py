# Tg_bot/services/config_service.py
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from utils.logging_setup import logger


class BotConfigService:
    def __init__(self, base_path: str = "databases") -> None:
        self.base_path = Path(base_path)
        self._configs: dict[str, dict[str, str | None]] = {}
        logger.info("Инициализация сервиса конфигураций ботов.")

    def load_all_bot_configs(self) -> Any:
        """Сканирует директории и загружает все .env файлы ботов."""
        logger.info(f"Сканирование {self.base_path} для поиска конфигураций ботов...")
        for bot_dir in self.base_path.iterdir():
            if bot_dir.is_dir():
                env_path = bot_dir / "tg_bot" / ".env"
                if env_path.exists():
                    bot_id = bot_dir.name
                    self._configs[bot_id] = dotenv_values(env_path)
                    logger.info(f"✅ Конфигурация для бота '{bot_id}' успешно загружена.")
        logger.info(f"Загрузка конфигураций завершена. Найдено ботов: {len(self._configs)}")

    def get_bot_config(self, bot_id: str) -> dict[str, Any] | None:
        """Возвращает конфигурацию для конкретного бота."""
        return self._configs.get(bot_id)
