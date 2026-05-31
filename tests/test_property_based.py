"""Property-based tests for Domain layer using Hypothesis."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tg_bot.domain.order import Money, Order, OrderItem, OrderStatus


class TestMoneyProperties:
    """Property-based tests for Money value object."""

    @given(
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
    )
    def test_addition_commutative(self, a: float, b: float) -> None:
        """Money addition should be commutative."""
        m1 = Money(a) + Money(b)
        m2 = Money(b) + Money(a)
        assert m1.amount == pytest.approx(m2.amount, abs=0.01)

    @given(
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.integers(min_value=0, max_value=10000)
    )
    def test_multiplication_by_zero(self, amount: float, n: int) -> None:
        """Multiplying any Money by 0 should give 0."""
        m = Money(amount) * 0
        assert m.amount == 0.0

    @given(
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
    )
    def test_addition_associative(self, a: float, b: float, c: float) -> None:
        """Money addition should be associative: (a+b)+c == a+(b+c)."""
        m1 = (Money(a) + Money(b)) + Money(c)
        m2 = Money(a) + (Money(b) + Money(c))
        assert m1.amount == pytest.approx(m2.amount, abs=0.01)

    @given(
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
    )
    def test_money_zero_allowed(self, amount: float) -> None:
        """Money can be created with any non-negative amount."""
        m = Money(amount)
        assert m.amount == pytest.approx(amount, abs=0.01)


class TestOrderItemProperties:
    """Property-based tests for OrderItem."""

    @given(
        st.integers(min_value=1, max_value=100000),
        st.integers(min_value=1, max_value=1000),
        st.floats(min_value=0.01, max_value=1000, allow_nan=False, allow_infinity=False)
    )
    def test_subtotal_basic(self, pid: int, qty: int, price: float) -> None:
        """OrderItem subtotal should be calculable."""
        from decimal import Decimal
        item = OrderItem(product_id=pid, quantity=qty, price=Money(float(price)), name='Test')
        # Check It's Non-negative
        assert item.subtotal.amount >= 0
        # Money Rounds Price To 2 Decimal Places, Then Multiplies By Qty
        # So Calculate Expected The Same Way: Round Price First, Then Multiply
        price_money = Money(float(price))
        expected = float(Decimal(str(price_money.amount)) * qty)
        assert item.subtotal.amount == pytest.approx(expected, rel=1e-6)


class TestOrderProperties:
    """Property-based tests for Order aggregate."""

    @given(
        st.integers(min_value=1, max_value=100000),
        st.lists(
            st.fixed_dictionaries({
                'product_id': st.integers(min_value=1, max_value=100000),
                'quantity': st.integers(min_value=1, max_value=100),
                'price': st.floats(min_value=0.01, max_value=1000, allow_nan=False, allow_infinity=False),
                'name': st.text(min_size=1, max_size=50)
            }),
            min_size=1, max_size=10
        )
    )
    def test_order_creation(self, user_id: int, items_data: list[dict]) -> None:
        """Order should be created with correct user_id and items."""
        order = Order.create(user_id=user_id, items_data=items_data)
        assert order.user_id == user_id
        assert len(order.items) == len(items_data)
        assert order.status == OrderStatus.ACCEPTED

    @given(
        st.integers(min_value=1, max_value=100000)
    )
    def test_new_order_is_not_finalized(self, user_id: int) -> None:
        """A newly created order should not be finalized."""
        order = Order.create(user_id=user_id, items_data=[
            {'product_id': 1, 'quantity': 1, 'price': 10.0, 'name': 'Test'}
        ])
        assert not order.is_finalized
        assert order.status == OrderStatus.ACCEPTED

    @given(
        st.integers(min_value=1, max_value=100000)
    )
    def test_new_order_can_cancel(self, user_id: int) -> None:
        """A newly created order should be cancellable."""
        order = Order.create(user_id=user_id, items_data=[
            {'product_id': 1, 'quantity': 1, 'price': 10.0, 'name': 'Test'}
        ])
        assert order.can_cancel  # Should be True for ACCEPTED status


class TestOrderStatusTransitions:
    """Property-based tests for status transitions."""

    def test_valid_transition_accepted_to_awaiting_payment(self) -> None:
        """ACCEPTED -> AWAITING_PAYMENT is valid."""
        order = Order.create(user_id=1, items_data=[
            {'product_id': 1, 'quantity': 1, 'price': 10.0, 'name': 'Test'}
        ])
        order.transition_to(OrderStatus.AWAITING_PAYMENT)  # Should not raise
        assert order.status == OrderStatus.AWAITING_PAYMENT

    def test_valid_transition_awaiting_payment_to_paid(self) -> None:
        """AWAITING_PAYMENT -> PAID is valid."""
        order = Order.create(user_id=1, items_data=[
            {'product_id': 1, 'quantity': 1, 'price': 10.0, 'name': 'Test'}
        ])
        order.transition_to(OrderStatus.AWAITING_PAYMENT)
        order.transition_to(OrderStatus.PAID)
        assert order.status == OrderStatus.PAID

    def test_invalid_transition_accepted_to_paid_raises(self) -> None:
        """ACCEPTED -> PAID directly should raise."""
        order = Order.create(user_id=1, items_data=[
            {'product_id': 1, 'quantity': 1, 'price': 10.0, 'name': 'Test'}
        ])
        from tg_bot.domain.order import InvalidStateTransition
        with pytest.raises(InvalidStateTransition):
            order.transition_to(OrderStatus.PAID)


import tempfile
from pathlib import Path

from tg_bot.bot_services.ai_communication_service import sanitize_for_llm_prompt
from tg_bot.bot_services.product_sync_service import parse_product_file


class TestProductSyncProperties:
    """Property-based tests for product file parser (manifest §5.4)."""

    @given(st.text(min_size=0, max_size=1000))
    def test_parse_never_crashes_on_text(self, content: str) -> None:
        """Parser must not raise on any text input."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)
        try:
            result = parse_product_file(path)
            assert isinstance(result, dict)
        finally:
            path.unlink()

    @given(
        st.from_regex(
            r"^(name: [\w ]+\nprice: \d+ гр \d+ руб|name: [\w ]+\nprice: \d+)$",
            fullmatch=True,
        )
    )
    def test_parse_extracts_price_block(self, content: str) -> None:
        """Valid price lines must be captured without crash."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)
        try:
            result = parse_product_file(path)
            assert 'name' in result
            # Price_block Or Price Key Must Exist
            assert 'price_block' in result or 'price' in result
        finally:
            path.unlink()


class TestSanitizeProperties:
    """Property-based tests for LLM input sanitizer (manifest §5.4)."""

    @given(st.text(min_size=0, max_size=3000))
    def test_output_never_exceeds_max_length(self, text: str) -> None:
        result = sanitize_for_llm_prompt(text, max_length=2000)
        assert len(result) <= 2000

    @given(st.text(min_size=1))
    def test_script_tag_always_removed(self, payload: str) -> None:
        dirty = f"<script>{payload}</script>"
        result = sanitize_for_llm_prompt(dirty)
        assert "<script" not in result.lower()
