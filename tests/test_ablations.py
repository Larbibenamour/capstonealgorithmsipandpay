"""Tests for ablation study configurations and their behavioural guarantees.

Each test validates one key premise of a thesis Section 8.3 ablation:
  - Ablation A: flat complexity → eff_raw equals cycle_time
  - Ablation C: shrinkage_strength=0.0 → raw score is fully preserved
  - Ablation D: single-component weights → composite score equals efficiency score
"""

import pytest

from src.scoring.confidence import apply_shrinkage
from src.scoring.normalize import compute_composite_score


# ---------------------------------------------------------------------------
# Ablation A: No complexity adjustment
# Premise: when every order has a single item with quantity=1,
# complexity_units = 1.0, so eff_raw = cycle_time / 1.0 = cycle_time.
# ---------------------------------------------------------------------------
def test_flat_complexity_gives_eff_raw_equal_to_cycle_time():
    """Ablation A: eff_raw equals cycle_time when complexity_units = 1.0."""
    from datetime import datetime

    from src.scoring.complexity import compute_order_complexity
    from src.scoring.schema import Order, OrderItem

    # Construct an Order with a single item of quantity=1
    flat_order = Order(
        order_id=1,
        waiter_shift_id="ws_1",
        assigned_waiter_id="W1",
        accepted_ts=datetime(2026, 1, 1, 22, 0, 0),
        completed_ts=datetime(2026, 1, 1, 22, 5, 0),  # 300 seconds later
        items=[OrderItem(item_id="item_1", quantity=1)],
    )
    complexity = compute_order_complexity(flat_order, item_weights={})
    assert complexity == pytest.approx(1.0)

    # With complexity=1, eff_raw = cycle_time / complexity = cycle_time
    cycle_time_seconds = flat_order.cycle_time_seconds  # 300.0
    eff_raw = cycle_time_seconds / max(complexity, 1e-6)
    assert eff_raw == pytest.approx(cycle_time_seconds)


# ---------------------------------------------------------------------------
# Ablation C: No shrinkage (shrinkage_strength = 0.0)
# Premise: with strength=0.0, effective_confidence is raised to 1.0 so the
# raw score is fully preserved regardless of the waiter's confidence level.
# ---------------------------------------------------------------------------
def test_no_shrinkage_preserves_raw_score_at_any_confidence():
    """Ablation C: shrinkage_strength=0.0 keeps the raw score unchanged."""
    raw_score = 82.0
    baseline = 50.0

    for confidence in [0.0, 0.1, 0.3, 0.5, 0.8, 1.0]:
        result = apply_shrinkage(raw_score, baseline, confidence, shrinkage_strength=0.0)
        assert result == pytest.approx(raw_score, abs=0.01), (
            f"With shrinkage_strength=0, confidence={confidence}: "
            f"expected {raw_score}, got {result}"
        )


# ---------------------------------------------------------------------------
# Ablation D: Single-component scoring (efficiency only)
# Premise: when weights = {efficiency:1.0, throughput:0.0, consistency:0.0},
# compute_composite_score returns exactly the efficiency score.
# ---------------------------------------------------------------------------
def test_single_component_composite_equals_efficiency_score():
    """Ablation D: composite equals efficiency when w_eff=1, w_thr=0, w_cons=0."""
    single_component_weights = {
        "efficiency": 1.0,
        "throughput": 0.0,
        "consistency": 0.0,
    }

    for eff_score in [20.0, 50.0, 75.0, 95.0]:
        composite = compute_composite_score(
            efficiency_score=eff_score,
            throughput_score=30.0,  # irrelevant given w_thr=0
            consistency_score=80.0,  # irrelevant given w_cons=0
            weights=single_component_weights,
        )
        assert composite == pytest.approx(eff_score, abs=0.01), (
            f"Expected composite={eff_score} (efficiency-only), got {composite}"
        )
