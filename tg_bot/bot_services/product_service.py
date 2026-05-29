# Tg_bot/bot_services/product_service.py
import logging
import re
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict

import asyncpg

from tg_bot.models import Product, Variant
from tg_bot.tenant.config import get_current_tenant

logger = logging.getLogger(__name__)

class _ScoredProduct(TypedDict):
    product: Product
    score: float


class ProductService:
    def __init__(self, pool: asyncpg.Pool, db_manager: Any = None) -> None:
        self.pool = pool
        self.db_manager = db_manager
        self._category_tree_cache: Optional[dict[str, Any]] = None
        self._category_tree_updated: Optional[datetime] = None
        self._CACHE_TTL = 300

    async def _build_products_from_records(self, records: List[asyncpg.Record]) -> List[Product]:
        products_map = {}
        for r in records:
            product_id = r['id']
            if product_id not in products_map:
                full_desc = r.get('full_description') or ""
                products_map[product_id] = Product(
                    id=r['id'],
                    name=r['name'],
                    short_description=r['short_description'],
                    full_description=full_desc,
                    search_variants=r.get('search_variants') or "",
                    chapters=r['chapters'] or [],
                    images=r['images'] or [],
                    is_available=bool(r.get('is_available', True)),
                    variants=[]
                )
            if r['variant_id']:
                variant_name = r.get('attribute') or 'Стандартный'
                # Добавляем weight_grams и volume_ml
                variant = Variant(
                    id=r['variant_id'],
                    product_id=r['product_id'],
                    name=variant_name,
                    price=str(r['price']),
                    weight_grams=r.get('weight_grams'),
                    volume_ml=r.get('volume_ml')
                )
                products_map[product_id].variants.append(variant)
        return list(products_map.values())

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Any]:
        tenant = get_current_tenant()
        tenant_id = getattr(tenant, "bot_id", None) if tenant else None

        if self.db_manager is not None and tenant_id:
            async with self.db_manager.tenant_connection(tenant_id) as conn:
                yield conn
            return

        async with self.pool.acquire() as conn:
            yield conn

    async def get_available_products(self, light_mode: bool = False) -> List[Product]:
        logger.info(f"⏳ [DB] Запрос продуктов (light={light_mode})...") # [LOG]

        fields = "p.id, p.name, p.short_description, p.chapters, p.images, p.is_available, p.search_variants"
        if not light_mode:
            fields += ", p.full_description"

        query = f"""
            SELECT {fields},
                pv.id as variant_id, pv.product_id, pv.weight_grams,
                pv.volume_ml, pv.attribute, pv.price
            FROM products p
            LEFT JOIN product_variants pv ON p.id = pv.product_id
            WHERE p.is_available = TRUE
            ORDER BY p.name, pv.price;
        """
        try:
            # Добавил timeout 10 сек
            async with self._connection() as conn:
                records = await conn.fetch(query)

            logger.info(f"✅ [DB] Получено {len(records)} записей продуктов.") # [LOG]
            return await self._build_products_from_records(records)
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [DB] Ошибка get_available_products: {e}")
            return []

    async def get_product_by_id(self, product_id: int) -> Optional[Product]:
        logger.info(f"⏳ [DB] Запрос продукта {product_id}...") # [LOG]
        query = """
            SELECT p.id, p.name, p.short_description, p.full_description,
                p.chapters, p.images, p.is_available, p.search_variants,
                pv.id as variant_id, pv.product_id, pv.weight_grams,
                pv.volume_ml, pv.attribute, pv.price
            FROM products p
            LEFT JOIN product_variants pv ON p.id = pv.product_id
            WHERE p.id = $1 AND p.is_available = TRUE
        """
        try:
            async with self._connection() as conn:
                records = await conn.fetch(query, product_id)
            logger.info(f"✅ [DB] Продукт {product_id} загружен.")
            if not records:
                return None
            products = await self._build_products_from_records(records)
            return products[0] if products else None
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [DB] Ошибка get_product_by_id: {e}")
            return None

    async def get_category_tree(self) -> dict[str, Any]:
        if self._category_tree_cache and self._category_tree_updated:
            age = (datetime.now() - self._category_tree_updated).total_seconds()
            if age < self._CACHE_TTL:
                return self._category_tree_cache

        logger.info("⏳ [db] строим дерево категорий...")
        query = """SELECT DISTINCT chapters FROM products WHERE is_available = TRUE AND chapters IS NOT NULL"""
        try:
            async with self._connection() as conn:
                records = await conn.fetch(query)
            logger.info(f"✅ [DB] Дерево загружено ({len(records)} записей).")

            tree: dict[str, set[str]] = {}
            for r in records:
                chapters = r['chapters']
                if not chapters:
                    continue
                root = chapters[0].strip()
                if root not in tree:
                    tree[root] = set()
                if len(chapters) > 1:
                    sub = chapters[1].strip()
                    if sub:
                        tree[root].add(sub)

            result_tree = {k: sorted(list(v)) for k, v in tree.items()}
            self._category_tree_cache = result_tree
            self._category_tree_updated = datetime.now()
            return result_tree
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [DB] Ошибка get_category_tree: {e}")
            return {}


    def _normalize_search_text(self, text: str) -> str:
        """Нормализация пользовательского текста для устойчивого поиска."""
        if not text:
            return ""
        normalized = text.lower().replace("ё", "е")
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _tokenize_query(self, text: str) -> List[str]:
        return [token for token in text.split() if len(token) >= 2]

    def _generate_search_variants(self, text: str) -> List[str]:
        """Генерирует варианты запроса: раскладка + фонетическая транслитерация."""
        base_text = self._normalize_search_text(text)
        if not base_text:
            return []

        variants = [base_text]

        # 1. опечатки раскладки клавиатуры (йцукен <-> qwerty)
        ru_layout = "йцукенгшщзхъфывапролджэячсмитьбю"
        en_layout = "qwertyuiop[]asdfghjkl;'zxcvbnm,."

        if re.search('[а-я]', base_text):
            tr = str.maketrans(ru_layout, en_layout)
            variants.append(base_text.translate(tr))
        elif re.search('[a-z]', base_text):
            tr = str.maketrans(en_layout, ru_layout)
            variants.append(base_text.translate(tr))

        # 2. простая транслитерация ru -> en (нарино -> narino)
        translit_ru_en = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        }
        if re.search('[а-я]', base_text):
            ru_en_text = "".join(translit_ru_en.get(c, c) for c in base_text)
            if ru_en_text != base_text:
                variants.append(ru_en_text)

        # 3. простая транслитерация en -> ru (drip -> дрип)
        if re.search('[a-z]', base_text):
            en_ru_text = base_text
            digraphs = {'sch': 'щ', 'sh': 'ш', 'ch': 'ч', 'zh': 'ж', 'ts': 'ц', 'ya': 'я', 'yu': 'ю'}
            for eng, ru in sorted(digraphs.items(), key=lambda kv:
                len(kv[0]), reverse=True):
                en_ru_text = en_ru_text.replace(eng, ru)

            translit_en_ru = {
                'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'z': 'з',
                'i': 'и', 'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
                'p': 'п', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'f': 'ф', 'h': 'х',
                'c': 'к', 'j': 'дж', 'w': 'в', 'x': 'кс', 'q': 'кв'
            }
            en_ru_text = "".join(translit_en_ru.get(c, c) for c in en_ru_text)
            if en_ru_text != base_text:
                variants.append(en_ru_text)

        # Возвращаем только уникальные нормализованные варианты
        unique = []
        for variant in variants:
            variant_clean = self._normalize_search_text(variant)
            if variant_clean and variant_clean not in unique and len(variant_clean) >= 2:
                unique.append(variant_clean)
        return unique

    async def search_products(self, query_text: str) -> List[Product]:
        """
        Умный поиск: раскладка/транслит + триграммы + стабильное ранжирование.
        """
        clean_query = self._normalize_search_text(query_text)
        if len(clean_query) < 2:
            return []

        # Генерируем массив возможных написаний
        variants = self._generate_search_variants(clean_query)
        query_tokens = self._tokenize_query(clean_query)
        logger.info(f"⏳ [DB Search v3] Поиск по умным вариантам: {variants}")

        sql = """
            SELECT p.id, p.name, p.short_description, p.full_description,
                   p.chapters, p.images, p.is_available, p.search_variants,
                   pv.id as variant_id, pv.product_id, pv.weight_grams,
                   pv.volume_ml, pv.attribute, pv.price,
                   (
                       CASE
                           WHEN lower(p.name) = $1 THEN 220
                           WHEN lower(p.name) LIKE $2 THEN 140
                           WHEN lower(COALESCE(p.search_variants, '')) LIKE $2 THEN 120
                           WHEN lower(COALESCE(p.short_description, '')) LIKE $2 THEN 35
                           WHEN lower(COALESCE(p.full_description, '')) LIKE $2 THEN 15
                           ELSE 0
                       END
                       +
                       GREATEST(
                           similarity(lower(p.name), $1) * 95,
                           similarity(lower(COALESCE(p.search_variants, '')), $1) * 85,
                           similarity(lower(COALESCE(p.short_description, '')), $1) * 30,
                           similarity(lower(COALESCE(p.full_description, '')), $1) * 12
                       )
                   ) AS rank_score
            FROM products p
            LEFT JOIN product_variants pv ON p.id = pv.product_id
            WHERE p.is_available = TRUE
              AND (
                  lower(p.name) % $1
                  OR lower(COALESCE(p.search_variants, '')) % $1
                  OR lower(p.name) LIKE $2
                  OR lower(COALESCE(p.search_variants, '')) LIKE $2
                  OR lower(COALESCE(p.full_description, '')) LIKE $2
                  OR lower(COALESCE(p.short_description, '')) LIKE $2
              )
            ORDER BY
                rank_score DESC,
                p.name, pv.price;
        """

        all_found_products: dict[int, _ScoredProduct] = {}

        try:
            async with self._connection() as conn:
                for variant in variants:
                    # Коротким запросам нужен более строгий порог сходства, иначе шумит выдача.
                    if len(variant) <= 3:
                        similarity_threshold = 0.45
                    elif len(variant) <= 5:
                        similarity_threshold = 0.30
                    else:
                        similarity_threshold = 0.20
                    await conn.execute(f"SET pg_trgm.similarity_threshold = {similarity_threshold};")

                    substring_query = f"%{variant}%"
                    records = await conn.fetch(sql, variant, substring_query)
                    if not records:
                        continue

                    variant_scores: Dict[int, float] = {}
                    for record in records:
                        product_id = record['id']
                        base_score = float(record.get('rank_score') or 0.0)

                        # Доп. бонус за покрытие токенов исходного запроса.
                        if query_tokens:
                            search_blob = self._normalize_search_text(
                                " ".join([
                                    str(record.get('name') or ""),
                                    str(record.get('search_variants') or ""),
                                    str(record.get('short_description') or ""),
                                ])
                            )
                            matched = sum(1 for token in query_tokens if token in search_blob)
                            coverage = matched / len(query_tokens)
                            base_score += coverage * 40
                            if len(query_tokens) >= 2 and coverage == 0:
                                base_score -= 35

                        variant_scores[product_id] = max(
                            variant_scores.get(product_id, float("-inf")),
                            base_score,
                        )

                    products = await self._build_products_from_records(records)
                    for product in products:
                        score = variant_scores.get(product.id, 0.0)
                        current = all_found_products.get(product.id)
                        if (current is None) or (score > current["score"]):
                            all_found_products[product.id] = {"product": product, "score": score}

            ranked = sorted(
                all_found_products.values(),
                key=lambda item: item["score"],
                reverse=True
            )
            result_list = [item["product"] for item in ranked]
            logger.info(f"✅[DB Fuzzy Search v3] Найдено уникальных позиций: {len(result_list)}")
            return result_list

        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [DB Search] Ошибка Fuzzy-поиска: {e}")
            return await self._search_products_fallback(clean_query)

    async def _search_products_fallback(self, query_text: str) -> List[Product]:
        """Запасной метод: поиск по пересечению слов для всех вариантов написания."""
        variants = self._generate_search_variants(query_text)
        all_found_products = {}

        async with self._connection() as conn:
            for variant in variants:
                words = [w for w in variant.split() if len(w) > 2]
                if not words:
                    words = [variant]

                conditions = []
                params =[]
                for i, w in enumerate(words):
                    p_idx = i + 1
                    params.append(f"%{w}%")
                    conditions.append(f"""
                        (p.name ILIKE ${p_idx}
                         OR p.search_variants ILIKE ${p_idx}
                         OR p.full_description ILIKE ${p_idx}
                         OR p.short_description ILIKE ${p_idx})
                    """)

                sql = f"""
                    SELECT p.*, pv.id as variant_id, pv.product_id, pv.weight_grams,
                        pv.volume_ml, pv.attribute, pv.price
                    FROM products p
                    LEFT JOIN product_variants pv ON p.id = pv.product_id
                    WHERE p.is_available = TRUE AND ({" AND ".join(conditions)})
                    ORDER BY p.name;
                """
                records = await conn.fetch(sql, *params)
                products = await self._build_products_from_records(records)

                for p in products:
                    if p.id not in all_found_products:
                        all_found_products[p.id] = p

        return list(all_found_products.values())
