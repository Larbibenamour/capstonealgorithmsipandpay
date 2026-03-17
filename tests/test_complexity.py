"""Tests for complexity calculation and credit allocation."""

from datetime import datetime

import pytest

from src.scoring.complexity import (
    aggregate_complexity_by_waiter,
    compute_complexity_adjusted_cycle_time,
    compute_order_complexity,
    get_order_credits,
    get_order_credits_with_splitting,
    validate_item_weights,
)
from src.scoring.schema import Order, OrderItem


@pytest.fixture
def sample_order():
    """Create a sample order for testing."""
    return Order(
        order_id=1,
        waiter_shift_id="W1_shift_1",
        assigned_waiter_id="W1",
        accepted_ts=datetime(2026, 1, 1, 12, 0),
        completed_ts=datetime(2026, 1, 1, 12, 10),
        items=[
            OrderItem(item_id="burger", quantity=2),
            OrderItem(item_id="fries", quantity=1),
        ],
    )


def test_compute_order_complexity_uniform_weights(sample_order):
    """Test complexity calculation with uniform weights."""
    item_weights = {}
    complexity = compute_order_complexity(sample_order, item_weights, default_weight=1.0)
    assert complexity == 3.0  # 2 + 1


def test_compute_order_complexity_custom_weights(sample_order):
    """Test complexity calculation with custom item weights."""
    item_weights = {"burger": 2.0, "fries": 1.0}
    complexity = compute_order_complexity(sample_order, item_weights, default_weight=1.0)
    assert complexity == 5.0  # 2*2.0 + 1*1.0


def test_compute_order_complexity_mixed_weights(sample_order):
    """Test complexity with some items having custom weights."""
    item_weights = {"burger": 2.5}  # fries uses default
    complexity = compute_order_complexity(sample_order, item_weights, default_weight=1.0)
    assert complexity == 6.0  # 2*2.5 + 1*1.0


def test_compute_order_complexity_empty_order():
    """Test that an order with no items is rejected at construction (schema validation)."""
    with pytest.raises(Exception):
        Order(
            order_id=1,
            waiter_shift_id="W1_shift_1",
            assigned_waiter_id="W1",
            accepted_ts=datetime(2026, 1, 1, 12, 0),
            completed_ts=datetime(2026, 1, 1, 12, 10),
            items=[],
        )


def test_get_order_credits_single_waiter(sample_order):
    """Test credit allocation for single waiter (MVP v1)."""
    credits = get_order_credits(sample_order)
    assert len(credits) == 1
    assert credits[0].waiter_id == "W1"
    assert credits[0].credit_share == 1.0


def test_get_order_credits_with_splitting_valid(sample_order):
    """Test credit allocation with splitting (future v2)."""
    assignments = [("W1", 0.7), ("W2", 0.3)]
    credits = get_order_credits_with_splitting(sample_order, assignments)
    assert len(credits) == 2
    assert credits[0].credit_share == 0.7
    assert credits[1].credit_share == 0.3


def test_get_order_credits_with_splitting_invalid_sum(sample_order):
    """Test that invalid responsibility percentages raise error."""
    assignments = [("W1", 0.6), ("W2", 0.3)]  # Sum = 0.9, not 1.0
    with pytest.raises(ValueError, match="must sum to 1.0"):
        get_order_credits_with_splitting(sample_order, assignments)


def test_compute_complexity_adjusted_cycle_time():
    """Test efficiency raw calculation."""
    eff_raw = compute_complexity_adjusted_cycle_time(600, 5.0)
    assert eff_raw == 120.0  # 600 / 5


def test_compute_complexity_adjusted_cycle_time_zero_complexity():
    """Test efficiency raw with zero complexity (protected by epsilon)."""
    eff_raw = compute_complexity_adjusted_cycle_time(600, 0.0, epsilon=1e-6)
    assert eff_raw > 0  # Should not divide by zero


def test_aggregate_complexity_by_waiter():
    """Test complexity aggregation across multiple orders."""
    orders = [
        Order(
            order_id=1,
            waiter_shift_id="W1_shift_1",
            assigned_waiter_id="W1",
            accepted_ts=datetime(2026, 1, 1, 12, 0),
            completed_ts=datetime(2026, 1, 1, 12, 10),
            items=[OrderItem(item_id="A", quantity=2)],
        ),
        Order(
            order_id=2,
            waiter_shift_id="W1_shift_1",
            assigned_waiter_id="W1",
            accepted_ts=datetime(2026, 1, 1, 12, 15),
            completed_ts=datetime(2026, 1, 1, 12, 25),
            items=[OrderItem(item_id="B", quantity=3)],
        ),
        Order(
            order_id=3,
            waiter_shift_id="W2_shift_1",
            assigned_waiter_id="W2",
            accepted_ts=datetime(2026, 1, 1, 12, 20),
            completed_ts=datetime(2026, 1, 1, 12, 30),
            items=[OrderItem(item_id="A", quantity=1)],
        ),
    ]

    item_weights = {"A": 2.0, "B": 1.0}
    result = aggregate_complexity_by_waiter(orders, item_weights)

    assert result["W1"] == 7.0  # 2*2.0 + 3*1.0
    assert result["W2"] == 2.0  # 1*2.0


def test_validate_item_weights_valid():
    """Test validation of valid item weights."""
    item_weights = {"A": 1.0, "B": 2.0, "C": 0.5}
    validate_item_weights(item_weights)  # Should not raise


def test_validate_item_weights_negative():
    """Test validation rejects negative weights."""
    item_weights = {"A": 1.0, "B": -1.0}
    with pytest.raises(ValueError, match="must be non-negative"):
        validate_item_weights(item_weights)
