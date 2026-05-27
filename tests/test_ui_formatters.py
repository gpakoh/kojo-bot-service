from typing import Any

from tg_bot.models import Product, Variant
from utils.ui_formatters import format_product_card_html


def make_product(
    name: str = "Test Coffee",
    short_description: str = "A tasty brew",
    full_description: str = "Характеристики: арабика. Оценка SCA (Q): 84. Способ обработки: мытый.",
    variants: list | None = None,
) -> Product:
    if variants is None:
        variants = [Variant(id=1, product_id=1, name="200g", price="1500")]
    return Product(
        id=1,
        name=name,
        short_description=short_description,
        full_description=full_description,
        variants=variants,
    )


class TestFormatProductCardHtml:
    def test_normal_card_with_all_fields(self) -> Any:
        product = make_product()
        result = format_product_card_html(product)

        assert "<b>☕️ TEST COFFEE</b>" in result
        assert "<i>A tasty brew</i>" in result
        assert "<b>Характеристики:</b>" in result
        assert "<b>Оценка SCA (Q):</b>" in result
        assert "<b>Способ обработки:</b>" in result
        assert "<b>💳 Доступные варианты:</b>" in result
        assert "200g" in result
        assert "1500₽" in result

    def test_missing_short_description(self) -> Any:
        product = make_product(short_description=None)
        result = format_product_card_html(product)

        assert "<b>☕️ TEST COFFEE</b>" in result
        assert "<i>" not in result
        assert "<b>💳 Доступные варианты:</b>" in result

    def test_missing_variants(self) -> Any:
        product = make_product(variants=[])
        result = format_product_card_html(product)

        assert "<b>☕️ TEST COFFEE</b>" in result
        assert "<i>A tasty brew</i>" in result
        assert "<b>💳 Доступные варианты:</b>" not in result

    def test_keys_to_bold_rendering(self) -> Any:
        product = make_product(
            full_description=(
                "Характеристики: арабика.\n"
                "Оценка SCA (Q): 84.\n"
                "Способ обработки: мытый.\n"
                "Разновидность: катурра.\n"
                "Регион: Антиокия.\n"
                "Высота: 1800м.\n"
                "Дескрипторы: шоколад, цитрус."
            )
        )
        result = format_product_card_html(product)

        assert "<b>Характеристики:</b>" in result
        assert "<b>Оценка SCA (Q):</b>" in result
        assert "<b>Способ обработки:</b>" in result
        assert "<b>Разновидность:</b>" in result
        assert "<b>Регион:</b>" in result
        assert "<b>Высота:</b>" in result
        assert "<b>Дескрипторы:</b>" in result

    def test_block_headers_formatting(self) -> Any:
        product = make_product(
            full_description=(
                "Some intro text.\nОписание: This is the description.\n"
                "Дополнительные особенности: Extra features."
            )
        )
        result = format_product_card_html(product)

        assert "\n<b>Описание:</b>" in result
        assert "\n<b>Дополнительные особенности:</b>" in result

    def test_case_insensitive_key_bolding(self) -> Any:
        product = make_product(
            full_description="характеристики: арабика."
        )
        result = format_product_card_html(product)

        assert "<b>Характеристики:</b>" in result

    def test_empty_full_description(self) -> Any:
        product = make_product(full_description=None)
        result = format_product_card_html(product)

        assert "<b>☕️ TEST COFFEE</b>" in result
        assert "<i>A tasty brew</i>" in result
        assert "<b>💳 Доступные варианты:</b>" in result

    def test_short_description_stripped(self) -> Any:
        product = make_product(short_description="  spaced text  ")
        result = format_product_card_html(product)

        assert "<i>spaced text</i>" in result
        assert "  spaced text  " not in result
