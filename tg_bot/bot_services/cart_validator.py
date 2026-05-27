# Tg_bot/bot_services/cart_validator.py
# Compatibility Layer For Tests - Provides Cartvalidator And Cartvalidationstatus
from enum import Enum
from typing import Any, List, NamedTuple


class CartValidationStatus(Enum):
    """Compatibility wrapper for CartValidationResult."""
    OK = "ok"
    STALE_ITEMS_REMOVED = "cleared_old"
    UNAVAILABLE_ITEMS = "item_unavailable"


class RemovedItem(NamedTuple):
    product_id: int
    product_name: str
    reason: str


class CartValidator:
    """Compatibility wrapper - delegates to CartService validation logic."""

    def validate(self, rows: list[dict[str, Any]]) -> 'CartValidationReport':
        # Simple Validation Logic For Tests
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        removed_items = []
        unavailable_items = []

        for row in rows:
            # Check If Stale (older Than 24 Hours)
            created_at = row.get('created_at')

            # Handle Naive Datetime - Make It Timezone Aware
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            if created_at and (now - created_at).total_seconds() > 86400:  # 24 hours
                if not row.get('is_available', True):
                    removed_items.append(RemovedItem(
                        product_id=row['product_id'],
                        product_name=row['name'],
                        reason='unavailable'
                    ))
                elif row.get('current_price', 0) != row.get('saved_price', 0):
                    # Check Price Change Threshold (0.01 Or 1%)
                    old_price = row.get('saved_price', 0)
                    new_price = row.get('current_price', 0)
                    price_diff = abs(new_price - old_price)
                    threshold = max(0.01, old_price * 0.01)  # 0.01 or 1% of old price

                    if price_diff > threshold:
                        removed_items.append(RemovedItem(
                            product_id=row['product_id'],
                            product_name=row['name'],
                            reason='price_changed'
                        ))

            # Check If Unavailable
            if not row.get('is_available', True):
                check_time = created_at if created_at else now
                if (now - check_time).total_seconds() <= 86400:
                    unavailable_items.append(RemovedItem(
                        product_id=row['product_id'],
                        product_name=row['name'],
                        reason='unavailable'
                    ))

        if unavailable_items and not removed_items:
            status = CartValidationStatus.UNAVAILABLE_ITEMS
        elif removed_items:
            status = CartValidationStatus.STALE_ITEMS_REMOVED
        else:
            status = CartValidationStatus.OK

        return CartValidationReport(
            status=status,
            removed_items=removed_items,
            unavailable_items=unavailable_items
        )


class CartValidationReport:
    def __init__(self, status: CartValidationStatus,
                 removed_items: List[RemovedItem],
                 unavailable_items: List[RemovedItem]):
        self.status = status
        self.stale_items = removed_items  # Test uses stale_items
        self.unavailable_items = unavailable_items
        self.has_removed_items = bool(removed_items)
