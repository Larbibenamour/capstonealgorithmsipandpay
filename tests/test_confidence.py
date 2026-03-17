"""Tests for confidence scoring and shrinkage."""

import pandas as pd
import pytest

from src.scoring.confidence import (
    apply_shrinkage,
    compute_complexity_confidence,
    compute_confidence_weighted_average,
    compute_overall_confidence,
    compute_sample_size_confidence,
    compute_stability_confidence,
)


def test_compute_sample_size_confidence():
    """Test confidence increases with sample size."""
    conf_small = compute_sample_size_confidence(2, min_orders=5)
    conf_medium = compute_sample_size_confidence(10, min_orders=5)
    conf_large = compute_sample_size_confidence(50, min_orders=5)

    # Confidence should increase with more orders
    assert conf_small < conf_medium < conf_large

    # Check specific thresholds
    assert compute_sample_size_confidence(5, min_orders=5) == pytest.approx(0.5, abs=0.1)
    assert compute_sample_size_confidence(0, min_orders=5) == 0.0


def test_compute_complexity_confidence():
    """Test confidence increases with complexity handled."""
    conf_small = compute_complexity_confidence(5.0, min_complexity=10.0)
    conf_medium = compute_complexity_confidence(30.0, min_complexity=10.0)
    conf_large = compute_complexity_confidence(100.0, min_complexity=10.0)

    assert conf_small < conf_medium < conf_large

    # Check specific thresholds
    assert compute_complexity_confidence(10.0, min_complexity=10.0) == pytest.approx(0.5, abs=0.1)


def test_compute_stability_confidence():
    """Test confidence decreases with higher dispersion."""
    conf_stable = compute_stability_confidence(0.0, max_acceptable_dispersion=0.5)
    conf_moderate = compute_stability_confidence(0.3, max_acceptable_dispersion=0.5)
    conf_unstable = compute_stability_confidence(1.0, max_acceptable_dispersion=0.5)

    assert conf_stable > conf_moderate > conf_unstable

    # Perfect stability should give high confidence
    assert conf_stable > 0.9


def test_compute_overall_confidence():
    """Test overall confidence combines components."""
    config = {"min_orders_for_confidence": 5}

    # High confidence case
    conf_high = compute_overall_confidence(
        n_orders=20, total_complexity=50.0, normalized_dispersion=0.1, config=config
    )

    # Low confidence case
    conf_low = compute_overall_confidence(
        n_orders=2, total_complexity=5.0, normalized_dispersion=0.8, config=config
    )

    assert conf_high > conf_low
    assert 0 <= conf_high <= 1
    assert 0 <= conf_low <= 1


def test_compute_overall_confidence_custom_weights():
    """Test overall confidence with custom component weights."""
    config = {"min_orders_for_confidence": 5}
    weights = {"sample_size": 0.5, "complexity": 0.3, "stability": 0.2}

    conf = compute_overall_confidence(
        n_orders=10, total_complexity=30.0, normalized_dispersion=0.2, config=config, weights=weights
    )

    assert 0 <= conf <= 1


def test_compute_overall_confidence_invalid_weights():
    """Test that invalid weight sums raise error."""
    config = {"min_orders_for_confidence": 5}
    weights = {"sample_size": 0.5, "complexity": 0.3, "stability": 0.1}  # Sum = 0.9

    with pytest.raises(ValueError, match="must sum to 1.0"):
        compute_overall_confidence(
            n_orders=10, total_complexity=30.0, normalized_dispersion=0.2, config=config, weights=weights
        )


def test_apply_shrinkage_high_confidence():
    """Test shrinkage has minimal effect with high confidence."""
    raw_score = 90.0
    shift_baseline = 50.0
    confidence = 1.0

    shrunk_score = apply_shrinkage(raw_score, shift_baseline, confidence, shrinkage_strength=0.3)

    # High confidence should preserve raw score
    assert shrunk_score == pytest.approx(raw_score, abs=1)


def test_apply_shrinkage_low_confidence():
    """Test shrinkage pulls toward baseline with low confidence."""
    raw_score = 90.0
    shift_baseline = 50.0
    confidence = 0.0

    shrunk_score = apply_shrinkage(raw_score, shift_baseline, confidence, shrinkage_strength=0.3)

    # Low confidence should pull toward baseline
    assert shift_baseline < shrunk_score < raw_score


def test_apply_shrinkage_medium_confidence():
    """Test shrinkage with medium confidence."""
    raw_score = 80.0
    shift_baseline = 50.0
    confidence = 0.5

    shrunk_score = apply_shrinkage(raw_score, shift_baseline, confidence, shrinkage_strength=0.3)

    # Should be between baseline and raw score
    assert shift_baseline < shrunk_score < raw_score


def test_apply_shrinkage_bounds():
    """Test shrinkage respects score bounds."""
    # Test upper bound
    shrunk_high = apply_shrinkage(150, 50, 0.5, 0.3)
    assert shrunk_high <= 100

    # Test lower bound
    shrunk_low = apply_shrinkage(-10, 50, 0.5, 0.3)
    assert shrunk_low >= 0


def test_compute_confidence_weighted_average():
    """Test confidence-weighted averaging."""
    scores = pd.Series([100, 50, 80])
    confidences = pd.Series([0.9, 0.1, 0.7])  # Middle score has low confidence

    avg = compute_confidence_weighted_average(scores, confidences, min_confidence=0.2)

    # Should be dominated by high-confidence scores (100 and 80)
    assert 80 < avg < 100


def test_compute_confidence_weighted_average_all_low():
    """Test averaging when all confidences are low."""
    scores = pd.Series([70, 80, 90])
    confidences = pd.Series([0.1, 0.1, 0.1])

    avg = compute_confidence_weighted_average(scores, confidences, min_confidence=0.5)

    # All filtered out, should return neutral 50
    assert avg == 50.0


def test_confidence_monotonicity():
    """Test that confidence increases monotonically with better conditions."""
    config = {"min_orders_for_confidence": 5}

    # Vary sample size (holding others constant)
    conf_samples = [
        compute_overall_confidence(n, 30.0, 0.2, config) for n in [2, 5, 10, 20, 50]
    ]
    assert all(conf_samples[i] <= conf_samples[i + 1] for i in range(len(conf_samples) - 1))

    # Vary complexity (holding others constant)
    conf_complexity = [
        compute_overall_confidence(10, c, 0.2, config) for c in [5.0, 10.0, 30.0, 60.0, 100.0]
    ]
    assert all(conf_complexity[i] <= conf_complexity[i + 1] for i in range(len(conf_complexity) - 1))

    # Vary stability (lower dispersion = higher confidence)
    conf_stability = [
        compute_overall_confidence(10, 30.0, d, config) for d in [1.0, 0.5, 0.3, 0.1, 0.0]
    ]
    assert all(conf_stability[i] <= conf_stability[i + 1] for i in range(len(conf_stability) - 1))
