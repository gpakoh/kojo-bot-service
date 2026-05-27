# Tests/test_cart_validator.py
import datetime
from typing import Any

from tg_bot.bot_services.cart_validator import (
    CartValidationStatus,
    CartValidator,
)


class TestCartValidator:
    def test_empty_cart_returns_ok(self) -> Any:
        validator = CartValidator()
        report = validator.validate([])
        assert report.status == CartValidationStatus.OK
        assert not report.has_removed_items

    def test_fresh_items_returns_ok(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        rows = [{
            'product_id': 1, 'saved_price': 100.0, 'created_at': now,
            'name': 'Кофе', 'is_available': True, 'current_price': 100.0,
        }]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.OK
        assert report.stale_items == []
        assert report.unavailable_items == []

    def test_stale_item_with_price_change_is_removed(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = now - datetime.timedelta(hours=25)
        rows = [{
            'product_id': 1, 'saved_price': 100.0, 'created_at': stale,
            'name': 'Кофе', 'is_available': True, 'current_price': 120.0,
        }]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.STALE_ITEMS_REMOVED
        assert len(report.stale_items) == 1
        assert report.stale_items[0].product_name == 'Кофе'
        assert report.stale_items[0].reason == 'price_changed'

    def test_stale_unavailable_item_is_removed(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = now - datetime.timedelta(hours=30)
        rows = [{
            'product_id': 1, 'saved_price': 100.0, 'created_at': stale,
            'name': 'Кофе', 'is_available': False, 'current_price': 100.0,
        }]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.STALE_ITEMS_REMOVED
        assert report.stale_items[0].reason == 'unavailable'

    def test_fresh_unavailable_item_blocks_purchase(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        rows = [{
            'product_id': 1, 'saved_price': 100.0, 'created_at': now,
            'name': 'Кофе', 'is_available': False, 'current_price': 100.0,
        }]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.UNAVAILABLE_ITEMS
        assert report.unavailable_items[0].product_name == 'Кофе'
        assert report.stale_items == []

    def test_mixed_fresh_and_stale_fresh_survives(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = now - datetime.timedelta(hours=25)
        rows = [
            {
                'product_id': 1, 'saved_price': 100.0, 'created_at': stale,
                'name': 'Кофе', 'is_available': True, 'current_price': 120.0,
            },
            {
                'product_id': 2, 'saved_price': 50.0, 'created_at': now,
                'name': 'Чай', 'is_available': True, 'current_price': 50.0,
            },
        ]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.STALE_ITEMS_REMOVED
        assert len(report.stale_items) == 1
        assert report.stale_items[0].product_name == 'Кофе'

    def test_multiple_stale_items_all_removed(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = now - datetime.timedelta(hours=25)
        rows = [
            {
                'product_id': 1, 'saved_price': 100.0, 'created_at': stale,
                'name': 'Кофе', 'is_available': True, 'current_price': 120.0,
            },
            {
                'product_id': 2, 'saved_price': 80.0, 'created_at': stale,
                'name': 'Чай', 'is_available': True, 'current_price': 90.0,
            },
        ]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.STALE_ITEMS_REMOVED
        assert len(report.stale_items) == 2
        names = {item.product_name for item in report.stale_items}
        assert names == {'Кофе', 'Чай'}

    def test_price_change_threshold(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = now - datetime.timedelta(hours=25)
        rows = [{
            'product_id': 1, 'saved_price': 100.0, 'created_at': stale,
            'name': 'Кофе', 'is_available': True, 'current_price': 100.005,
        }]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.OK

    def test_naive_datetime_handled(self) -> Any:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = now - datetime.timedelta(hours=25)
        naive_stale = stale.replace(tzinfo=None)
        rows = [{
            'product_id': 1, 'saved_price': 100.0, 'created_at': naive_stale,
            'name': 'Кофе', 'is_available': True, 'current_price': 120.0,
        }]
        report = CartValidator().validate(rows)
        assert report.status == CartValidationStatus.STALE_ITEMS_REMOVED
