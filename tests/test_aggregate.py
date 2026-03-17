"""Tests for temporal aggregation functions."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.scoring.aggregate import (
    aggregate_scores_by_period,
    compute_period_over_period_change,
    compute_rolling_average,
    compute_trend,
    identify_consistent_performers,
)


@pytest.fixture
def sample_results():
    """Create sample results dict for testing."""
    return {
        "shift_1": {
            "W1": {
                "score": 80.0,
                "confidence": 0.8,
                "metrics": {"total_complexity": 50.0},
            },
            "W2": {
                "score": 70.0,
                "confidence": 0.7,
                "metrics": {"total_complexity": 40.0},
            },
        },
        "shift_2": {
            "W1": {
                "score": 85.0,
                "confidence": 0.85,
                "metrics": {"total_complexity": 55.0},
            },
            "W2": {
                "score": 65.0,
                "confidence": 0.6,
                "metrics": {"total_complexity": 35.0},
            },
        },
    }


@pytest.fixture
def sample_shifts_df():
    """Create sample shifts DataFrame."""
    return pd.DataFrame(
        {
            "shift_id": ["shift_1", "shift_2"],
            "start_ts": [
                datetime(2026, 1, 1, 18, 0),
                datetime(2026, 1, 8, 18, 0),
            ],
            "end_ts": [
                datetime(2026, 1, 2, 2, 0),
                datetime(2026, 1, 9, 2, 0),
            ],
        }
    )


def test_aggregate_scores_by_period(sample_results, sample_shifts_df):
    """Test aggregation to weekly periods."""
    aggregated = aggregate_scores_by_period(
        sample_results, sample_shifts_df, period="week", min_confidence=0.3
    )

    assert not aggregated.empty
    assert "waiter_id" in aggregated.columns
    assert "aggregated_score" in aggregated.columns
    assert "period_start" in aggregated.columns


def test_aggregate_scores_filters_low_confidence(sample_results, sample_shifts_df):
    """Test that low-confidence scores are filtered."""
    # Set high confidence threshold
    aggregated = aggregate_scores_by_period(
        sample_results, sample_shifts_df, period="week", min_confidence=0.9
    )

    # Should filter out most scores
    assert len(aggregated) < len(sample_results) * 2


def test_aggregate_scores_winsorization(sample_results, sample_shifts_df):
    """Test that winsorization caps extreme scores."""
    # Add extreme score
    sample_results["shift_1"]["W1"]["score"] = 150.0  # Artificially high

    aggregated = aggregate_scores_by_period(
        sample_results, sample_shifts_df, period="week", winsorize_quantile=0.1
    )

    # Aggregated score should be reasonable (not 150)
    if not aggregated.empty:
        max_score = aggregated["aggregated_score"].max()
        assert max_score <= 100  # Should be capped


def test_compute_rolling_average():
    """Test rolling average computation."""
    agg_df = pd.DataFrame(
        {
            "waiter_id": ["W1", "W1", "W1", "W1"],
            "period_start": pd.date_range("2026-01-01", periods=4, freq="W"),
            "aggregated_score": [70, 75, 80, 85],
        }
    )

    result = compute_rolling_average(agg_df, window_size=2, min_periods=2)

    # Check rolling average exists
    assert "rolling_avg_score" in result.columns

    # Last rolling avg should be mean of last 2 scores
    expected_last = (80 + 85) / 2
    actual_last = result.iloc[-1]["rolling_avg_score"]
    assert actual_last == pytest.approx(expected_last, abs=0.1)


def test_compute_trend_positive():
    """Test trend computation with improving scores."""
    agg_df = pd.DataFrame(
        {
            "waiter_id": ["W1", "W1", "W1"],
            "period_start": pd.date_range("2026-01-01", periods=3, freq="W"),
            "aggregated_score": [70, 75, 80],  # Improving
        }
    )

    trends = compute_trend(agg_df)

    assert len(trends) == 1
    assert trends.loc[0, "trend_slope"] > 0  # Positive trend
    assert "trend_pvalue" in trends.columns


def test_compute_trend_negative():
    """Test trend computation with declining scores."""
    agg_df = pd.DataFrame(
        {
            "waiter_id": ["W1", "W1", "W1"],
            "period_start": pd.date_range("2026-01-01", periods=3, freq="W"),
            "aggregated_score": [80, 75, 70],  # Declining
        }
    )

    trends = compute_trend(agg_df)

    assert trends.loc[0, "trend_slope"] < 0  # Negative trend


def test_compute_trend_insufficient_data():
    """Test trend with insufficient data."""
    agg_df = pd.DataFrame(
        {
            "waiter_id": ["W1"],
            "period_start": [datetime(2026, 1, 1)],
            "aggregated_score": [75],
        }
    )

    trends = compute_trend(agg_df)

    # Should still return result with neutral values
    assert len(trends) == 1
    assert trends.loc[0, "trend_slope"] == 0.0


def test_identify_consistent_performers():
    """Test identification of consistent high performers."""
    agg_df = pd.DataFrame(
        {
            "waiter_id": ["W1", "W1", "W1", "W1", "W2", "W2", "W2", "W2"],
            "aggregated_score": [80, 82, 81, 79, 60, 90, 55, 95],  # W1 consistent, W2 variable
        }
    )

    consistent = identify_consistent_performers(
        agg_df, min_periods=4, max_variance=10.0, min_mean_score=70.0
    )

    # W1 should be identified as consistent (low variance, high mean)
    assert "W1" in consistent["waiter_id"].values
    # W2 should not (high variance)
    assert "W2" not in consistent["waiter_id"].values


def test_compute_period_over_period_change():
    """Test period-over-period change calculation."""
    agg_df = pd.DataFrame(
        {
            "waiter_id": ["W1", "W1", "W1"],
            "period_start": pd.date_range("2026-01-01", periods=3, freq="W"),
            "aggregated_score": [70, 80, 85],
        }
    )

    result = compute_period_over_period_change(agg_df)

    assert "score_change" in result.columns
    assert "pct_change" in result.columns

    # Second period change should be +10
    assert result.loc[1, "score_change"] == pytest.approx(10.0, abs=0.1)

    # Third period change should be +5
    assert result.loc[2, "score_change"] == pytest.approx(5.0, abs=0.1)


def test_aggregate_complexity_weighted():
    """Test that aggregation weights by complexity."""
    results = {
        "shift_1": {
            "W1": {
                "score": 100.0,
                "confidence": 0.9,
                "metrics": {"total_complexity": 10.0},  # Low complexity
            }
        },
        "shift_2": {
            "W1": {
                "score": 50.0,
                "confidence": 0.9,
                "metrics": {"total_complexity": 90.0},  # High complexity
            }
        },
    }

    shifts_df = pd.DataFrame(
        {
            "shift_id": ["shift_1", "shift_2"],
            "start_ts": [datetime(2026, 1, 1), datetime(2026, 1, 2)],
        }
    )

    aggregated = aggregate_scores_by_period(results, shifts_df, period="week")

    # Aggregated score should be closer to 50 (weighted by complexity)
    w1_score = aggregated.loc[aggregated["waiter_id"] == "W1", "aggregated_score"].values[0]

    # Expected: (100*10 + 50*90) / (10 + 90) = 5500 / 100 = 55
    assert w1_score == pytest.approx(55.0, abs=1.0)
