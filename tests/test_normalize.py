"""Tests for normalization and scoring functions."""

import numpy as np
import pandas as pd
import pytest

from src.scoring.normalize import (
    compute_composite_score,
    normalize_efficiency_within_shift,
    percentile_rank,
    robust_scale,
    winsorize_values,
)


def test_percentile_rank():
    """Test percentile rank calculation.

    scipy kind='rank': for [1,2,3,4,5], value=3 → 3/5 * 100 = 60.0
    The minimum is 0 only when value < all values; maximum 100 when value = max.
    """
    values = np.array([1, 2, 3, 4, 5])
    assert percentile_rank(values, 3) == pytest.approx(60.0, abs=5)  # middle of 5
    assert percentile_rank(values, 1) == pytest.approx(20.0, abs=5)  # lowest rank = 1/5
    assert percentile_rank(values, 5) == pytest.approx(100.0, abs=5)  # highest


def test_percentile_rank_empty():
    """Test percentile rank with empty array."""
    values = np.array([])
    rank = percentile_rank(values, 5)
    assert rank == 50.0  # Default for empty


def test_robust_scale():
    """Test robust scaling with median and IQR."""
    data = pd.Series([10, 20, 30, 40, 50])
    scaled = robust_scale(data, center="median", scale="iqr")

    # Median should be approximately 0
    assert abs(scaled.median()) < 0.1

    # Check IQR scaling
    assert scaled.std() > 0  # Should have variance


def test_robust_scale_mean_std():
    """Test robust scaling with mean and std."""
    data = pd.Series([10, 20, 30, 40, 50])
    scaled = robust_scale(data, center="mean", scale="std")

    # Mean should be approximately 0
    assert abs(scaled.mean()) < 0.1

    # Std should be approximately 1
    assert abs(scaled.std() - 1.0) < 0.1


def test_robust_scale_constant_values():
    """Test robust scaling with constant values (edge case)."""
    data = pd.Series([5, 5, 5, 5, 5])
    scaled = robust_scale(data, center="median", scale="iqr")

    # Should handle zero IQR gracefully with epsilon
    assert not np.any(np.isnan(scaled))


def test_normalize_efficiency_within_shift():
    """Test within-shift efficiency normalization."""
    eff_stats = pd.DataFrame(
        {
            "shift_id": [1, 1, 1],
            "waiter_id": ["W1", "W2", "W3"],
            "median_eff_raw": [80, 100, 120],  # W1 is fastest (lowest)
        }
    )

    result = normalize_efficiency_within_shift(eff_stats, lower_is_better=True)

    # W1 (fastest) should have highest score
    w1_score = result.loc[result["waiter_id"] == "W1", "efficiency_score"].values[0]
    w3_score = result.loc[result["waiter_id"] == "W3", "efficiency_score"].values[0]

    assert w1_score > w3_score
    assert 0 <= w1_score <= 100
    assert 0 <= w3_score <= 100


def test_normalize_efficiency_single_waiter():
    """Test normalization with single waiter in shift."""
    eff_stats = pd.DataFrame(
        {
            "shift_id": [1],
            "waiter_id": ["W1"],
            "median_eff_raw": [100],
        }
    )

    result = normalize_efficiency_within_shift(eff_stats, lower_is_better=True)

    # Single waiter should get neutral score
    score = result.loc[0, "efficiency_score"]
    assert 0 <= score <= 100


def test_compute_composite_score():
    """Test composite score calculation."""
    weights = {"efficiency": 0.5, "throughput": 0.3, "consistency": 0.2}

    score = compute_composite_score(80, 70, 60, weights)

    expected = 0.5 * 80 + 0.3 * 70 + 0.2 * 60
    assert score == pytest.approx(expected, abs=0.01)


def test_compute_composite_score_bounds():
    """Test composite score stays within bounds."""
    weights = {"efficiency": 0.5, "throughput": 0.3, "consistency": 0.2}

    # Test upper bound
    score_high = compute_composite_score(100, 100, 100, weights)
    assert score_high == 100

    # Test lower bound
    score_low = compute_composite_score(0, 0, 0, weights)
    assert score_low == 0

    # Test clipping
    score_clip = compute_composite_score(150, 150, 150, weights)
    assert score_clip == 100


def test_winsorize_values():
    """Test winsorization of extreme values."""
    data = pd.Series([1, 2, 3, 4, 5, 100])  # 100 is outlier
    winsorized = winsorize_values(data, lower_quantile=0.1, upper_quantile=0.9)

    # Extreme value should be capped
    assert winsorized.max() < 100
    assert winsorized.min() >= 1


def test_winsorize_values_no_outliers():
    """Test winsorization with no outliers."""
    data = pd.Series([10, 20, 30, 40, 50])
    winsorized = winsorize_values(data, lower_quantile=0.1, upper_quantile=0.9)

    # Should be similar to original
    assert (data - winsorized).abs().mean() < 5


def test_normalize_efficiency_multiple_shifts():
    """Test normalization preserves shift isolation."""
    eff_stats = pd.DataFrame(
        {
            "shift_id": [1, 1, 2, 2],
            "waiter_id": ["W1", "W2", "W1", "W2"],
            "median_eff_raw": [80, 120, 90, 110],
        }
    )

    result = normalize_efficiency_within_shift(eff_stats, lower_is_better=True)

    # Check that normalization is within-shift
    shift1_scores = result[result["shift_id"] == 1]["efficiency_score"].values
    shift2_scores = result[result["shift_id"] == 2]["efficiency_score"].values

    # Within each shift, faster should score higher
    assert shift1_scores[0] > shift1_scores[1]  # W1 faster than W2 in shift 1
    assert shift2_scores[0] > shift2_scores[1]  # W1 faster than W2 in shift 2
