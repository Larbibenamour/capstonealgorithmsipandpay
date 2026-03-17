"""Temporal stability analysis for waiter scores.

Analyzes:
- Week-to-week score correlations
- Consistency of rankings over time
- Identification of stable vs volatile performers
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.mock_data import generate_mock_data
from src.scoring.aggregate import aggregate_scores_by_period
from src.scoring.score_shift import compute_scores


def compute_temporal_correlation(aggregated_df: pd.DataFrame, period: str = "week") -> dict:
    """Compute correlation between consecutive periods.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        period: 'week' or 'month'

    Returns:
        Dictionary with correlation statistics
    """
    # Sort by waiter and period
    aggregated_df = aggregated_df.sort_values(["waiter_id", "period_start"])

    # Compute lagged scores
    aggregated_df["prev_score"] = aggregated_df.groupby("waiter_id")["aggregated_score"].shift(1)

    # Remove first period (no previous score)
    correlation_df = aggregated_df.dropna(subset=["prev_score"])

    if len(correlation_df) < 2:
        print(f"\n=== Temporal Stability Analysis ({period.title()}) ===")
        print("Insufficient data for temporal correlation (need 2+ periods)")
        return {"correlation": None, "n_comparisons": 0}

    # Compute correlation
    correlation = correlation_df["aggregated_score"].corr(correlation_df["prev_score"])

    stats = {
        "correlation": correlation,
        "n_comparisons": len(correlation_df),
        "mean_abs_change": (
            correlation_df["aggregated_score"] - correlation_df["prev_score"]
        ).abs().mean(),
    }

    print(f"\n=== Temporal Stability Analysis ({period.title()}) ===")
    print(f"Period-to-period correlation: {correlation:.3f}")
    print(f"Number of comparisons: {stats['n_comparisons']}")
    print(f"Mean absolute score change: {stats['mean_abs_change']:.2f} points")

    if correlation > 0.7:
        print("High stability - scores consistent across periods")
    elif correlation > 0.5:
        print("Moderate stability - scores somewhat consistent")
    else:
        print("Low stability - scores vary significantly over time")

    return stats


def identify_stable_performers(
    aggregated_df: pd.DataFrame, min_periods: int = 4
) -> pd.DataFrame:
    """Identify waiters with stable performance over time.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        min_periods: Minimum periods required for analysis

    Returns:
        DataFrame with stability metrics per waiter
    """
    stability_records = []

    for waiter_id, group in aggregated_df.groupby("waiter_id"):
        if len(group) < min_periods:
            continue

        scores = group["aggregated_score"].values

        stability_records.append(
            {
                "waiter_id": waiter_id,
                "n_periods": len(group),
                "mean_score": scores.mean(),
                "std_dev": scores.std(),
                "min_score": scores.min(),
                "max_score": scores.max(),
                "range": scores.max() - scores.min(),
                "coef_variation": scores.std() / scores.mean() if scores.mean() > 0 else 0,
            }
        )

    stability_df = pd.DataFrame(stability_records)

    if not stability_df.empty:
        # Sort by coefficient of variation (lower = more stable)
        stability_df = stability_df.sort_values("coef_variation")

    return stability_df


def analyze_rank_stability(
    aggregated_df: pd.DataFrame, min_periods: int = 3
) -> dict:
    """Analyze stability of rankings over time.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        min_periods: Minimum periods required

    Returns:
        Dictionary with rank stability statistics
    """
    # Compute ranks within each period
    aggregated_df = aggregated_df.copy()
    aggregated_df["rank"] = aggregated_df.groupby("period_start")["aggregated_score"].rank(
        ascending=False
    )

    # Track rank changes
    aggregated_df = aggregated_df.sort_values(["waiter_id", "period_start"])
    aggregated_df["prev_rank"] = aggregated_df.groupby("waiter_id")["rank"].shift(1)
    aggregated_df["rank_change"] = aggregated_df["rank"] - aggregated_df["prev_rank"]

    rank_changes = aggregated_df.dropna(subset=["rank_change"])

    if len(rank_changes) < min_periods:
        return {
            "mean_abs_rank_change": None,
            "pct_rank_stable": None,
            "max_rank_change": None,
        }

    stats = {
        "mean_abs_rank_change": rank_changes["rank_change"].abs().mean(),
        "pct_rank_stable": (rank_changes["rank_change"].abs() <= 1).mean() * 100,
        "max_rank_change": rank_changes["rank_change"].abs().max(),
    }

    print("\n=== Rank Stability Analysis ===")
    print(f"Mean absolute rank change: {stats['mean_abs_rank_change']:.2f}")
    print(
        f"Pct with ≤1 rank change: {stats['pct_rank_stable']:.1f}% (stable)"
    )
    print(f"Max rank change: {stats['max_rank_change']:.0f} positions")

    return stats


def identify_volatile_performers(
    stability_df: pd.DataFrame, volatility_threshold: float = 0.15
) -> pd.DataFrame:
    """Identify waiters with high score volatility.

    Args:
        stability_df: Output from identify_stable_performers()
        volatility_threshold: Coefficient of variation threshold

    Returns:
        DataFrame of volatile performers
    """
    volatile = stability_df[stability_df["coef_variation"] > volatility_threshold]

    print("\n=== Volatile Performers ===")
    if not volatile.empty:
        print(f"Identified {len(volatile)} volatile performers (CV > {volatility_threshold})")
        print(
            volatile[["waiter_id", "mean_score", "std_dev", "coef_variation"]].to_string(
                index=False
            )
        )
    else:
        print(f"No highly volatile performers found (CV > {volatility_threshold})")

    return volatile


def test_score_reliability(
    aggregated_df: pd.DataFrame, test_periods: int = 4, prediction_horizon: int = 1
) -> dict:
    """Test reliability of scores for predicting future performance.

    Uses first N periods to predict performance in period N+1.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        test_periods: Number of historical periods to use for prediction
        prediction_horizon: Number of periods ahead to predict

    Returns:
        Dictionary with prediction accuracy statistics
    """
    # Ensure sorted
    aggregated_df = aggregated_df.sort_values(["waiter_id", "period_start"])

    prediction_records = []

    for waiter_id, group in aggregated_df.groupby("waiter_id"):
        if len(group) < test_periods + prediction_horizon:
            continue

        for i in range(len(group) - test_periods - prediction_horizon + 1):
            # Historical scores
            historical = group.iloc[i : i + test_periods]
            historical_mean = historical["aggregated_score"].mean()

            # Future actual score
            future = group.iloc[i + test_periods + prediction_horizon - 1]
            actual_score = future["aggregated_score"]

            # Prediction error
            error = actual_score - historical_mean

            prediction_records.append(
                {
                    "waiter_id": waiter_id,
                    "predicted": historical_mean,
                    "actual": actual_score,
                    "error": error,
                    "abs_error": abs(error),
                }
            )

    if not prediction_records:
        print("\n=== Score Reliability Test ===")
        print("Insufficient data for prediction analysis")
        return {"mae": None, "rmse": None, "correlation": None}

    pred_df = pd.DataFrame(prediction_records)

    mae = pred_df["abs_error"].mean()
    rmse = np.sqrt((pred_df["error"] ** 2).mean())
    correlation = pred_df["predicted"].corr(pred_df["actual"])

    print("\n=== Score Reliability Test ===")
    print(f"Predicting {prediction_horizon} period(s) ahead using {test_periods} historical periods")
    print(f"Mean Absolute Error: {mae:.2f} points")
    print(f"RMSE: {rmse:.2f} points")
    print(f"Predicted-Actual correlation: {correlation:.3f}")

    if mae < 5:
        print("High reliability - scores predict future well")
    elif mae < 10:
        print("Moderate reliability - scores somewhat predictive")
    else:
        print("Low reliability - high prediction error")

    return {"mae": mae, "rmse": rmse, "correlation": correlation, "n_predictions": len(pred_df)}


def run_stability_analysis(
    orders_df: pd.DataFrame, shifts_df: pd.DataFrame, staffing_df: pd.DataFrame
) -> None:
    """Run complete temporal stability analysis.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame
    """
    print("=" * 60)
    print("TEMPORAL STABILITY ANALYSIS")
    print("=" * 60)

    # Compute scores
    print("\nComputing shift-level scores...")
    config = {
        "weights": {"efficiency": 0.50, "throughput": 0.30, "consistency": 0.20},
        "item_weights": {},
        "workload_adjustment": "multiplicative",
        "shrinkage_strength": 0.3,
    }
    results = compute_scores(orders_df, shifts_df, staffing_df, config)

    # Aggregate to weekly periods
    print("Aggregating to weekly periods...")
    aggregated_df = aggregate_scores_by_period(
        results, shifts_df, period="week", min_confidence=0.3
    )

    if aggregated_df.empty:
        print("No data available for temporal analysis")
        return

    # Temporal correlation
    compute_temporal_correlation(aggregated_df, period="week")

    # Identify stable performers
    print("\n[1/4] Identifying stable performers...")
    stability_df = identify_stable_performers(aggregated_df, min_periods=3)
    if not stability_df.empty:
        print("\nTop 5 Most Stable Performers:")
        print(
            stability_df.head(5)[
                ["waiter_id", "n_periods", "mean_score", "std_dev", "coef_variation"]
            ].to_string(index=False)
        )

    # Rank stability
    print("\n[2/4] Analyzing rank stability...")
    analyze_rank_stability(aggregated_df, min_periods=3)

    # Volatile performers
    print("\n[3/4] Identifying volatile performers...")
    identify_volatile_performers(stability_df, volatility_threshold=0.12)

    # Prediction reliability
    print("\n[4/4] Testing score reliability...")
    test_score_reliability(aggregated_df, test_periods=3, prediction_horizon=1)

    print("\n" + "=" * 60)
    print("TEMPORAL STABILITY ANALYSIS COMPLETE")
    print("=" * 60)


def main() -> None:
    """Run stability analysis on mock data."""
    print("Generating mock data (4 weeks)...")
    orders_df, shifts_df, staffing_df = generate_mock_data(
        n_shifts=28, n_waiters=8, orders_per_shift=50  # 4 weeks, daily shifts
    )

    run_stability_analysis(orders_df, shifts_df, staffing_df)


if __name__ == "__main__":
    main()
