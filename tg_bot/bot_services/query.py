# Tg_bot/bot_services/query.py
# Sqlalchemy Core Query Builders
from typing import Any, cast

from sqlalchemy import select, text

from .tables import products


async def search_similarity(engine: Any, vector_column: str, query_text: str, threshold: float = 0.5) -> list[Any]:
    """
    Search for products using vector similarity.
    Sets the similarity threshold and performs a search.
    """
    async with engine.connect() as conn:
        # Set The Similarity Threshold
        await conn.execute(text(f"SELECT set_config('pg_trm.similarity_threshold', '{threshold}', true)"))

        # Perform The Search
        stmt = select(products).where(
            products.c.name.op('%')(query_text)
        )
        result = await conn.execute(stmt)
        return cast(list[Any], result.fetchall())
