# Tg_bot/bot_services/product_sync_service.py
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, List

import asyncpg
import httpx

from utils.logging_setup import logger

# Файл находится в /app/tg_bot/bot_services/product_sync_service.py
# .parents[0] -> Bot_services
# .parents[1] -> Tg_bot
TG_BOT_ROOT = Path(__file__).resolve().parents[1]
KOJO_ROOT = TG_BOT_ROOT.parent  # -> /app
CONFIG_LOCK = asyncio.Lock()
PRODUCTS_DIR = TG_BOT_ROOT / "products"
RAG_KNOWLEDGE_FILE = KOJO_ROOT / "base" / "products_knowledge.txt"

# Путь к конфигу. теперь он точно указывает на /app/config/config.json
CONFIG_FILE = KOJO_ROOT / "config" / "config.json"

# Вспомогательные функции

def get_file_hash(path: Path) -> str:
    """Вычисляет MD5 хэш файла."""
    hasher = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        return ""

def parse_product_file(file_path: Path) -> dict[str, Any]:
    """Парсит product.txt в структурированный словарь."""
    data, current_key = {}, None
    key_map = {
        'sale': 'sale',
        'name': 'name',
        'short description': 'short_description',
        'description': 'full_description',
        'chapter': 'chapters',
        'grinding': 'grinding',
        'price': 'price_block',
        'search': 'search',
    }
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.match(r'^([a-zA-Z\s]+):\s*(.*)', line)
            if match:
                key, value = match.group(1).strip().lower(), match.group(2).strip()
                if key in key_map:
                    current_key = key_map[key]
                    data[current_key] = value
                else:
                    current_key = None
            elif current_key and line.strip():
                data[current_key] += '\n' + line.strip()
    return data


async def _handle_force_recache(pool: asyncpg.Pool) -> tuple[bool, bool]:
    """
    Железобетонный механизм проверки флагов через очередь (Lock).
    Ни одна функция не войдет, пока предыдущая не отпустит замок.
    """
    db_recache = False
    search_recache = False

    # Входим в очередь. если замок занят — ждем здесь.
    async with CONFIG_LOCK:
        logger.info("🔒 [lock] захватили флаг работы с конфигом.")

        if not CONFIG_FILE.exists():
            logger.error(f"❌ [Config] Файл не найден: {CONFIG_FILE}")
            return False, False

        try:
            # Открываем файл внутри блокировки
            with open(CONFIG_FILE, 'r+', encoding='utf-8') as f:
                config_data = json.load(f)

                force_db = config_data.get("force_recache_product", False)
                force_search = config_data.get("force_recache_search_product", False)

                # Выполняем действия, только если флаги true
                if force_db is True:
                    logger.warning("🚀 [action] выполняем очистку бд...")
                    async with pool.acquire() as conn:
                        await conn.execute("TRUNCATE TABLE products, product_variants, sync_metadata RESTART IDENTITY CASCADE;")
                    db_recache = True
                    config_data["force_recache_product"] = False

                if force_search is True:
                    logger.warning("🔎 [action] выполняем сброс поиска...")
                    search_recache = True
                    config_data["force_recache_search_product"] = False

                # Если были изменения, записываем и сбрасываем буфер
                if db_recache or search_recache:
                    f.seek(0)
                    json.dump(config_data, f, ensure_ascii=False, indent=4)
                    f.truncate()
                    f.flush()
                    os.fsync(f.fileno())
                    logger.info("📝 [config] изменения записаны, флаги возвращены в false.")
                else:
                    logger.info("ℹ️ [config] флаги уже в состоянии false, пропускаем.")

        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [Config] Ошибка в критической секции: {e}", exc_info=True)

        logger.info("🔓 [lock] освободили флаг работы с конфигом.")

    return db_recache, search_recache


async def _reset_config_flags() -> Any:
    """Сбрасывает все флаги рекэша в false после завершения работы."""
    try:
        if not CONFIG_FILE.exists():
            return

        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Сбрасываем оба флага
        config_data["force_recache_product"] = False
        config_data["force_recache_search_product"] = False

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        logger.info("✅ [config] все флаги рекэша сброшены в false.")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"❌ [Config] Не удалось сбросить флаги: {e}")


async def _parse_and_insert_variants(conn: asyncpg.Connection, product_id: int, price_block: str, product_name: str) -> Any:
    """
    Интеллектуально парсит блок с ценами и вставляет варианты в БД.
    Обрабатывает простые, одиночные и множественные варианты.
    """
    variants_to_insert = []
    lines = [line.strip() for line in price_block.split('\n') if line.strip()]

    if not lines:
        logger.warning(f"Для товара '{product_name}' (ID: {product_id}) не найден блок с ценой. Варианты не будут созданы.")
        return

    for line in lines:
        # Сценарий 1: "100 гр 449 руб" или "50 мл 1200"
        match_complex = re.match(r"(\d+)\s*(гр|мл)\s*(\d+)", line, re.IGNORECASE)
        if match_complex:
            value, unit, price = match_complex.groups()
            variant = {'product_id': product_id, 'price': int(price), 'weight_grams': None, 'volume_ml': None, 'attribute': f"{value} {unit.lower()}"}
            if unit.lower() == 'гр':
                variant['weight_grams'] = int(value)
            elif unit.lower() == 'мл':
                variant['volume_ml'] = int(value)
            variants_to_insert.append(variant)
            logger.info(f"Найден сложный вариант для '{product_name}': {variant['attribute']} - {variant['price']} руб.")
            continue

        # Сценарий 2: "9599 руб" (просто цена)
        match_simple = re.match(r"(\d+)\s*руб", line, re.IGNORECASE)
        if match_simple:
            price = int(match_simple.group(1))
            variants_to_insert.append({
                'product_id': product_id,
                'price': price,
                'weight_grams': None,
                'volume_ml': None,
                'attribute': None # Нет атрибута, т.к. вариант один
            })
            logger.info(f"Найден простой вариант для '{product_name}': {price} руб.")

    if not variants_to_insert:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось распарсить цену для '{product_name}' из блока: '{price_block}'. Товар будет без цены!")
        return

    if variants_to_insert:
        records = [(v['product_id'], v['weight_grams'], v['volume_ml'], v['attribute'], v['price']) for v in variants_to_insert]
        await conn.copy_records_to_table('product_variants', records=records, columns=('product_id', 'weight_grams', 'volume_ml', 'attribute', 'price'))
        logger.info(f"Для товара '{product_name}' успешно вставлено {len(variants_to_insert)} вариантов цены.")

def _is_cyrillic(text: str) -> bool:
    """Проверяет, содержит ли текст кириллицу."""
    return bool(re.search('[а-яА-ЯёЁ]', text))

async def _get_variant_from_llm(name: str, task_type: str) -> str:
    """Запрашивает вариант у LLM с жесткими примерами и очисткой мусора."""
    quart_url = os.getenv("QUART_SERVER_URL")
    bot_id = os.getenv("BOT_ID_FOR_QUART")

    # Сверхжесткие промпты с примерами (few-shot)
    prompts = {
        "to_en": f"Task: Translate product name to English.\nInput: 'Габа улун'\nOutput: Gaba Oolong\nInput: 'Шоппер'\nOutput: Shopper\nInput: '{name}'\nOutput:",
        "to_ru": f"Task: Translate product name to Russian.\nInput: 'Drip Peru'\nOutput: Дрип Перу\nInput: '{name}'\nOutput:",
        "to_lat": f"Task: Transliterate Russian name using English letters (phonetic).\nInput: 'Габа улун'\nOutput: gaba ulun\nInput: 'Мангалам'\nOutput: mangalam\nInput: '{name}'\nOutput:",
        "to_cyr": f"Task: Transliterate English name using Russian letters (phonetic).\nInput: 'Drip Peru'\nOutput: Дрип Перу Ла Коипа\nInput: '{name}'\nOutput:"
    }

    prompt = prompts.get(task_type, name)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(3):
            try:
                assert quart_url is not None
                resp = await client.post(quart_url, json={
                    "bot_id": bot_id,
                    "user_id": "system_sync",
                    "topic": prompt,
                    "is_direct": True
                })

                if resp.status_code == 200:
                    raw_val = resp.json().get("answer", "").strip()

                    # Блок очистки (ножницы)
                    # 1. убираем кавычки
                    val = raw_val.replace('"', '').replace("'", "")
                    # 2. если модель выдала предложение "x translates to y", берем последнее слово
                    if " translates to " in val.lower():
                        val = val.lower().split(" translates to ")[-1]
                    # 3. убираем префиксы, которые любит llm
                    val = re.sub(r'^(output|result|translation|name):\s*', '', val, flags=re.IGNORECASE)
                    # 4. берем только первую строку (на случай если модель начала объяснять)
                    val = val.split('\n')[0].strip()
                    # 5. убираем точку в конце
                    val = val.rstrip('.')

                    return val  # type: ignore[no-any-return]

                if resp.status_code == 429:
                    await asyncio.sleep((attempt + 1) * 3)
                    continue
                break

            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"❌ Ошибка LLM: {e}")
                await asyncio.sleep(1)

    return ""

async def _process_single_product_directory(conn: asyncpg.Connection, product_dir: Path, search_recache: bool = False) -> str:
    """Обрабатывает папку товара: парсит, обогащает поиск, пишет в БД."""
    file_path = product_dir / "product.txt"
    parsed_data = parse_product_file(file_path)
    product_name = parsed_data.get('name', product_dir.name)

    # Логика обогащения поиска
    search_line = parsed_data.get('search', '').strip()

    # Если включен форсированный рекэш поиска, обнуляем старую строку
    if search_recache:
        logger.info(f"♻️ [Force Search] Сброс старых данных поиска для: {product_name}")
        search_line = ""

    # Если поля search нет или оно пустое (или было сброшено выше)
    if not search_line or len(search_line.split(',')) < 2:
        logger.info(f"🔎 [Sync] Запуск обогащения поиска для: {product_name}")

        variants = [product_name]

        # Генерируем варианты строго один за другом
        if _is_cyrillic(product_name):
            logger.info("(ru) запрос en...")
            en_variant = await _get_variant_from_llm(product_name, "to_en")

            logger.info("(ru) запрос lat...")
            lat_variant = await _get_variant_from_llm(product_name, "to_lat")

            if en_variant:
                variants.append(en_variant)
            if lat_variant:
                variants.append(lat_variant)
        else:
            logger.info("(en) запрос ru...")
            ru_variant = await _get_variant_from_llm(product_name, "to_ru")

            logger.info("(en) запрос cyr...")
            cyr_variant = await _get_variant_from_llm(product_name, "to_cyr")

            if ru_variant:
                variants.append(ru_variant)
            if cyr_variant:
                variants.append(cyr_variant)

        # Очистка: убираем дубликаты, пустые строки и слишком длинные фразы (мусор)
        unique_variants = []
        # Добавляем оригинал
        unique_variants.append(product_name.lower())

        for v in variants:
            if not v:
                continue
            v_clean = v.lower().strip()
            # Если вариант совпадает с оригиналом или уже есть в списке — пропускаем
            if v_clean in unique_variants:
                continue
            # Если в варианте больше 5 слов — скорее всего это "поток сознания" llm, пропускаем
            if len(v_clean.split()) > 5:
                continue
            unique_variants.append(v_clean)

        # Собираем строку (оригинал всегда первый)
        search_line = ", ".join(unique_variants)

        # Обновляем файл product.txt
        content = file_path.read_text(encoding='utf-8')
        if "search:" in content:
            content = re.sub(r"search:.*", f"search: {search_line}", content)
        else:
            content = content.rstrip() + f"\n\nsearch: {search_line}\n"

        file_path.write_text(content, encoding='utf-8')
        # Права файлов управляются deployment (dockerfile copy --chmod), не runtime-кодом
        logger.info(f"✅ [Sync] Файл обновлен. Варианты: {search_line}")

    # Сохранение в бд
    images = [str(p.relative_to(KOJO_ROOT)) for p in product_dir.glob("*") if p.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']]

    # Используем search_variants колонку (нужно добавить в бд: alter table products add column search_variants text)
    product_id = await conn.fetchval(
        """
        INSERT INTO products (name, short_description, full_description, chapters, images, is_available, search_variants)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (name) DO UPDATE SET
        short_description = $2, full_description = $3, chapters = $4, images = $5, is_available = $6, search_variants = $7
        RETURNING id;
        """,
        product_name, parsed_data.get('short_description', ''), parsed_data.get('full_description', ''),
        [c.strip() for c in parsed_data.get('chapters', '').split(',')] if parsed_data.get('chapters') else [],
        images, parsed_data.get('sale', 'False').lower() == 'true',
        search_line
    )

    # Валидация наличия product_id перед выполнением зависимых sql-запросов
    if not product_id:
        logger.error(f"❌ [Sync] Критическая ошибка: product_id = None для товара '{product_name}'. Пропускаем обновление вариантов.")
        logger.debug("Sync: Skipped variants for '%s' due to missing product_id.", product_name)
        return ""

    await conn.execute("DELETE FROM product_variants WHERE product_id = $1", product_id)
    await _parse_and_insert_variants(conn, product_id, parsed_data.get('price_block', ''), product_name)

    logger.debug("Sync: Product %s synced with search variants.", product_name)
    return f"### Товар: {product_name} ###\nПоиск: {search_line}\n"


def _write_rag_file(rag_content_parts: List[str]) -> Any:
    """Записывает собранные части в файл для RAG."""
    try:
        RAG_KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RAG_KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            f.write("\n\n---\n\n".join(rag_content_parts))
        logger.info(f"📝 Файл базы знаний для RAG '{RAG_KNOWLEDGE_FILE}' успешно обновлён.")
    except IOError as e:
        logger.error(f"❌ Не удалось записать файл для RAG: {e}")


# NOTE:
# Product sync is a system-level catalog operation.
# It intentionally uses the raw pool instead of tenant-scoped connections because
# it refreshes global product tables during startup/admin sync and may run outside
# Telegram tenant middleware. Do not wrap this path in tenant_connection() unless
# product sync is redesigned to be tenant-explicit.
async def sync_products(pool: asyncpg.Pool) -> Any:
    """Главная функция-оркестратор синхронизации."""
    logger.info("--- запуск синхронизации каталога продуктов ---")

    # Флаги сбрасываются прямо внутри этой функции
    db_recache, search_recache = await _handle_force_recache(pool)

    if not PRODUCTS_DIR.is_dir():
        logger.warning(f"Директория продуктов '{PRODUCTS_DIR}' не найдена.")
        return

    # Загружаем хеши (если бд не чистилась)
    sync_hashes = {}
    if not db_recache:
        try:
            rows = await pool.fetch("SELECT product_folder, file_hash FROM sync_metadata")
            sync_hashes = {row['product_folder']: row['file_hash'] for row in rows}
        except (RuntimeError, ConnectionError, TimeoutError, OSError):
            logger.error("Не удалось загрузить метаданные синхронизации.")

    rag_content_parts: List[str] = []

    for product_dir in PRODUCTS_DIR.iterdir():
        if not product_dir.is_dir():
            continue
        product_file = product_dir / "product.txt"
        if not product_file.exists():
            continue

        current_hash = get_file_hash(product_file)

        # Условие пропуска: не форс-поиск и хеш совпал
        if not search_recache and sync_hashes.get(product_dir.name) == current_hash:
            continue

        logger.info(f"🔄 '{product_dir.name}': начало обработки (ForceSearch={search_recache})")
        try:
            async with pool.acquire() as conn:
                rag_part = await _process_single_product_directory(conn, product_dir, search_recache)
                rag_content_parts.append(rag_part)

                await conn.execute(
                    """
                    INSERT INTO sync_metadata (product_folder, file_hash) VALUES ($1, $2)
                    ON CONFLICT (product_folder) DO UPDATE SET file_hash = $2, last_synced_at = NOW();
                    """,
                    product_dir.name, current_hash
                )
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ ОШИБКА при обработке '{product_dir.name}': {e}")

    if rag_content_parts:
        _write_rag_file(rag_content_parts)

    logger.info("--- синхронизация каталога продуктов завершена ---")
