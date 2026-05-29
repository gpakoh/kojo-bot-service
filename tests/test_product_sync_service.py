# Tests For Product_sync_service.py
from pathlib import Path
from typing import Any

from tg_bot.bot_services.product_sync_service import (
    get_file_hash,
    parse_product_file,
)


class TestGetFileHash:
    def test_get_file_hash_exists(self, tmp_path) -> Any:
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        result = get_file_hash(test_file)
        assert result != ""
        assert len(result) == 32

    def test_get_file_hash_not_found(self) -> Any:
        result = get_file_hash(Path("/nonexistent/path.txt"))
        assert result == ""

    def test_get_file_hash_uses_tmp_path(self, tmp_path) -> Any:
        test_file = tmp_path / "hash_test.txt"
        test_file.write_text("content for hash")
        result = get_file_hash(test_file)
        assert result != ""
        assert isinstance(result, str)


class TestParseProductFile:
    def test_parse_product_file(self, tmp_path) -> Any:
        content = """name: Тестовый кофе
short description: Короткое описание
description: Полное описание товара
chapter: Кофе
price: 100 гр 449 руб
search: кофе, тест
sale: true"""
        test_file = tmp_path / "product.txt"
        test_file.write_text(content)

        result = parse_product_file(test_file)
        assert result['name'] == 'Тестовый кофе'
        assert result['short_description'] == 'Короткое описание'
        assert result['sale'] == 'true'

    def test_parse_complex_prices(self, tmp_path) -> Any:
        test_cases = [
            ("100 гр 449 руб", "100 гр 449 руб"),
            ("250 гр 599 руб", "250 гр 599 руб"),
            ("1 кг 1890 руб", "1 кг 1890 руб"),
            ("50 гр 299 ₽", "50 гр 299 ₽"),
            ("200г 399руб", "200г 399руб"),
            ("450 руб", "450 руб"),
            ("999", "999"),
        ]
        for price_str, expected_price_block in test_cases:
            content = f"""name: Тест
price: {price_str}"""
            test_file = tmp_path / f"product_{expected_price_block.replace(' ', '_')}.txt"
            test_file.write_text(content)
            result = parse_product_file(test_file)
            assert result.get('price_block') == expected_price_block, f"Failed for price: {price_str}"

    def test_parse_product_file_uses_tmp_path(self, tmp_path) -> Any:
        content = """name: Временный товар
price: 100"""
        test_file = tmp_path / "temp_product.txt"
        test_file.write_text(content)
        result = parse_product_file(test_file)
        assert result['name'] == 'Временный товар'


def test_product_sync_service_documents_raw_pool_bypass():
    source = Path("tg_bot/bot_services/product_sync_service.py").read_text(encoding="utf-8")

    assert "system-level catalog operation" in source
    assert "raw pool instead of tenant-scoped connections" in source
    assert "db_manager.tenant_connection" not in source
