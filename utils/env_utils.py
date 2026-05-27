# Tg_bot/utils/env_utils.py
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

def update_env_variable(key: str, value: str, env_path: str = ".env") -> Any:
    """
    Обновляет переменную в файле .env и в текущем окружении os.environ.
    Если ключа нет — добавляет его. Если есть — перезаписывает.
    """
    # 1. обновляем память процесса (чтобы изменения применились мгновенно для текущего кода)
    os.environ[key] = value

    lines = []
    try:
        # Пытаемся прочитать существующий файл
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"Не удалось прочитать {env_path}, будет создан новый: {e}")

    new_lines = []
    found = False

    # Ищем строку и заменяем
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    # Если ключ не найден, добавляем в конец
    if not found:
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        new_lines.append(f"{key}={value}\n")

    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        logger.info(f"✅ Переменная {key} успешно сохранена в {env_path}")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"❌ Ошибка записи в {env_path}: {e}")
