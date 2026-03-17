"""Order complexity calculation and credit allocation.

This module computes complexity units for orders and handles credit allocation
across waiters. Designed to support future order-splitting without refactoring.
"""

from typing import Dict, List, Tuple, Union

from src.scoring.schema import Order, OrderCredit


def compute_order_complexity(
    order: Order, item_weights: Dict[Union[str, int], float], default_weight: float = 1.0
) -> float:
    """Compute total complexity units for an order.

    Complexity is calculated as the sum of (quantity × item_weight) across all items.
    If an item has no specified weight, uses default_weight.

    Args:
        order: Order object containing items
        item_weights: Mapping of item_id to complexity weight
        default_weight: Default weight for items not in item_weights mapping

    Returns:
        Total complexity units (≥ 0)

    Examples:
        >>> order = Order(
        ...     order_id=1, shift_id=1, assigned_waiter_id=1,
        ...     accepted_ts=datetime(2026, 1, 1, 12, 0),
        ...     completed_ts=datetime(2026, 1, 1, 12, 10),
        ...     items=[
        ...         OrderItem(item_id="burger", quantity=2),
        ...         OrderItem(item_id="fries", quantity=1)
        ...     ]
        ... )
        >>> item_weights = {"burger": 2.0, "fries": 1.0}
        >>> compute_order_complexity(order, item_weights)
        5.0  # 2*2.0 + 1*1.0
    """
    complexity = 0.0
    for item in order.items:
        weight = item_weights.get(item.item_id, default_weight)
        complexity += item.quantity * weight
    return max(complexity, 0.0)  # Ensure non-negative


def get_order_credits(order: Order) -> List[OrderCredit]:
    """Allocate order credit to waiters.

    MVP v1: Single waiter receives 100% credit.
    Future v2: Support order_assignments table for split credit allocation.

    Args:
        order: Order object

    Returns:
        List of OrderCredit objects allocating credit shares

    Examples:
        >>> order = Order(order_id=1, shift_id=1, assigned_waiter_id="W1", ...)
        >>> credits = get_order_credits(order)
        >>> credits[0].waiter_id
        'W1'
        >>> credits[0].credit_share
        1.0
    """
    # MVP v1: Single waiter gets full credit
    return [OrderCredit(order_id=order.order_id, waiter_id=order.assigned_waiter_id, credit_share=1.0)]


def get_order_credits_with_splitting(
    order: Order, assignments: List[Tuple[Union[str, int], float]]
) -> List[OrderCredit]:
    """Allocate order credit with explicit waiter assignments (future extension).

    This function provides the interface for order-splitting in future versions.
    Currently not used in MVP v1 but demonstrates the extension pattern.

    Args:
        order: Order object
        assignments: List of (waiter_id, responsibility_pct) tuples, where
                     responsibility_pct is in range [0, 1]

    Returns:
        List of OrderCredit objects allocating credit shares

    Raises:
        ValueError: If responsibility percentages don't sum to ~1.0

    Examples:
        >>> order = Order(order_id=1, shift_id=1, assigned_waiter_id="W1", ...)
        >>> assignments = [("W1", 0.7), ("W2", 0.3)]
        >>> credits = get_order_credits_with_splitting(order, assignments)
        >>> len(credits)
        2
        >>> credits[0].credit_share
        0.7

    TODO (v2): Integrate with order_assignments table from database
    TODO (v2): Update compute_waiter_orders() to use fractional credits
    """
    total_pct = sum(pct for _, pct in assignments)
    if not (0.99 <= total_pct <= 1.01):
        raise ValueError(f"Responsibility percentages must sum to 1.0, got {total_pct}")

    return [
        OrderCredit(order_id=order.order_id, waiter_id=waiter_id, credit_share=pct)
        for waiter_id, pct in assignments
    ]


def compute_complexity_adjusted_cycle_time(
    cycle_time_seconds: float, complexity_units: float, epsilon: float = 1e-6
) -> float:
    """Compute efficiency raw metric: cycle time per complexity unit.

    This is the core efficiency metric used for within-shift comparisons.
    Lower values indicate faster completion relative to order complexity.

    Args:
        cycle_time_seconds: Order cycle time in seconds
        complexity_units: Total complexity units for the order
        epsilon: Small constant to prevent division by zero

    Returns:
        Efficiency raw value (seconds per complexity unit)

    Examples:
        >>> compute_complexity_adjusted_cycle_time(600, 5.0)
        120.0  # 600 seconds / 5 complexity units
        >>> compute_complexity_adjusted_cycle_time(600, 0.0)  # Edge case
        600000000.0  # Protected by epsilon
    """
    return cycle_time_seconds / max(complexity_units, epsilon)


def aggregate_complexity_by_waiter(
    orders: List[Order], item_weights: Dict[Union[str, int], float], default_weight: float = 1.0
) -> Dict[Union[str, int], float]:
    """Aggregate total complexity units handled by each waiter.

    Args:
        orders: List of orders
        item_weights: Item complexity weight mapping
        default_weight: Default weight for unmapped items

    Returns:
        Dictionary mapping waiter_id to total complexity units

    Examples:
        >>> orders = [
        ...     Order(order_id=1, assigned_waiter_id="W1", items=[OrderItem(item_id="A", quantity=2)], ...),
        ...     Order(order_id=2, assigned_waiter_id="W1", items=[OrderItem(item_id="B", quantity=1)], ...),
        ...     Order(order_id=3, assigned_waiter_id="W2", items=[OrderItem(item_id="A", quantity=3)], ...),
        ... ]
        >>> item_weights = {"A": 2.0, "B": 1.0}
        >>> result = aggregate_complexity_by_waiter(orders, item_weights)
        >>> result["W1"]
        5.0  # 2*2.0 + 1*1.0
        >>> result["W2"]
        6.0  # 3*2.0
    """
    waiter_complexity: Dict[Union[str, int], float] = {}

    for order in orders:
        complexity = compute_order_complexity(order, item_weights, default_weight)
        # In v1, use assigned_waiter_id directly
        waiter_id = order.assigned_waiter_id

        if waiter_id not in waiter_complexity:
            waiter_complexity[waiter_id] = 0.0
        waiter_complexity[waiter_id] += complexity

    return waiter_complexity


def validate_item_weights(item_weights: Dict[Union[str, int], float]) -> None:
    """Validate item weights are non-negative.

    Args:
        item_weights: Item complexity weight mapping

    Raises:
        ValueError: If any weight is negative
    """
    for item_id, weight in item_weights.items():
        if weight < 0:
            raise ValueError(f"Item weight for {item_id} must be non-negative, got {weight}")
