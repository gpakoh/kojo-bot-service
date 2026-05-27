# Utils/ui_formatters.py
import logging
import re
from typing import Any

logger = logging.getLogger("ui_formatters")


def format_product_card_html(product: Any) -> str:
    """
    Превращает данные объекта Product в красиво оформленный HTML для Telegram.
    Реализует правила: Жирный шрифт для ключей, Курсив для Short Desc,
    Отступы перед блоками.
    """
    logger.info(f"Formatting product card for: {product.name}")

    # 1. заголовок (в верхнем регистре для солидности)
    text = f"<b>☕️ {product.name.upper()}</b>\n\n"

    # 2. краткое описание (short description) -> всегда курсивом
    if product.short_description:
        short_desc = product.short_description.strip()
        text += f"<i>{short_desc}</i>\n\n"

    # 3. обработка основного тела описания
    full_desc = product.full_description or ""

    # Правило: жирные ключи характеристик
    keys_to_bold = [
        "Характеристики:", r"Оценка SCA \(Q\):", "Способ обработки:",
        "Разновидность:", "Регион:", "Высота:", "Дескрипторы:"
    ]

    for key in keys_to_bold:
        # Исправление syntaxerror: выносим замену за пределы f-строки
        clean_label = key.replace('\\', '')
        pattern = f"(?i){key}"
        replacement = f"<b>{clean_label}</b>"
        full_desc = re.sub(pattern, replacement, full_desc)

    # Правило: пустая строка перед крупными блоками
    block_headers = ["Описание:", "Дополнительные особенности:"]
    for header in block_headers:
        # Делаем заголовок жирным и добавляем пустую строку сверху
        pattern = f"(?i){header}"
        replacement = f"\n<b>{header}</b>"
        full_desc = re.sub(pattern, replacement, full_desc)

    text += full_desc.strip()

    # 4. блок цен (если есть варианты)
    if product.variants:
        text += "\n\n<b>💳 Доступные варианты:</b>\n"
        for v in product.variants:
            text += f"• {v.name}: <b>{v.price}₽</b>\n"

    print(f"[DEBUG] UI Formatter: Text generated, length={len(text)}")
    return text
