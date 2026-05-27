# Utils/image_cache.py
import io
import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image
from telegram import Message

logger = logging.getLogger(__name__)
PHOTO_CACHE_TTL_SECONDS = 24 * 60 * 60
PHOTO_CACHE_MAX_ITEMS = 800


def _prune_photo_cache(photo_cache: dict[str, Any]) -> None:
    """Удаляет просроченные/битые записи и ограничивает размер кэша."""
    now = time.time()

    stale_keys = []
    for key, entry in photo_cache.items():
        if isinstance(entry, dict):
            file_id = entry.get('file_id')
            ts = entry.get('ts')
            if not file_id or not isinstance(ts, (int, float)) or (now - float(ts)) > PHOTO_CACHE_TTL_SECONDS:
                stale_keys.append(key)

    for key in stale_keys:
        photo_cache.pop(key, None)

    overflow = len(photo_cache) - PHOTO_CACHE_MAX_ITEMS
    if overflow > 0:
        # Сбрасываем самые старые записи; legacy-строки считаем "свежими", чтобы не ломать обратную совместимость.
        def sort_key(item: tuple[str, Any]) -> float:
            entry = item[1]
            if isinstance(entry, dict) and isinstance(entry.get('ts'), (int, float)):
                return float(entry['ts'])
            return now

        for key, _ in sorted(photo_cache.items(), key=sort_key)[:overflow]:
            photo_cache.pop(key, None)

def get_optimized_image(photo_path: Path) -> io.BufferedIOBase:
    """Сжимает картинку в памяти перед отправкой в Telegram."""
    try:
        with Image.open(photo_path) as img:
            # Конвертация прозрачного фона в белый (чтобы не было черных квадратов)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Уменьшаем разрешение (telegram всё равно ужимает до 1280px)
            img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)

            # Сохраняем в буфер памяти как легкий jpeg
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
            img_byte_arr.seek(0)

            # Обязательное имя файла, иначе telegram не примет байты
            img_byte_arr.name = 'photo.jpg'

            return img_byte_arr

    except (OSError, PermissionError) as e:
        logger.error(f"⚠️ Ошибка сжатия (использую оригинал): {e}")
        return open(photo_path, 'rb')


def get_media_payload(photo_path: Path, bot_data: dict[str, Any]) -> tuple[Any, Any]:
    """
    Возвращает (payload, file_to_close).
    payload - строка (file_id) или BytesIO.
    file_to_close - объект, который нужно закрыть в finally (или None).
    """
    photo_cache = bot_data.setdefault('photo_cache', {})
    _prune_photo_cache(photo_cache)
    path_str = str(photo_path)
    payload: Any = None
    entry = photo_cache.get(path_str)

    if isinstance(entry, dict):
        payload = entry.get('file_id')
        ts = entry.get('ts')
        if not payload or not isinstance(ts, (int, float)) or (time.time() - float(ts)) > PHOTO_CACHE_TTL_SECONDS:
            photo_cache.pop(path_str, None)
            payload = None
    elif isinstance(entry, str):
        # Обратная совместимость со старым форматом кэша.
        payload = entry
        photo_cache[path_str] = {'file_id': entry, 'ts': time.time()}

    if payload:
        print(f"[DEBUG] ImageCache: Взят file_id из кэша для {photo_path.name}")
        return payload, None

    print(f"[DEBUG] ImageCache: Сжатие и загрузка с диска для {photo_path.name}")
    file_obj = get_optimized_image(photo_path)
    return file_obj, file_obj


def update_cache_from_message(bot_data: dict[str, Any], photo_path: Path, message: Message) -> None:
    """Сохраняет file_id из отправленного сообщения в кэш."""
    if message and message.photo:
        photo_cache = bot_data.setdefault('photo_cache', {})
        photo_cache[str(photo_path)] = {'file_id': message.photo[-1].file_id, 'ts': time.time()}
        _prune_photo_cache(photo_cache)
        logger.info(f"📸 Фото закэшировано: {photo_path.name}")
