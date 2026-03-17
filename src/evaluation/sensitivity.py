"""Sensitivity analysis for scoring algorithm parameters.

Tests how scores change when varying:
- Component weights (efficiency, throughput, consistency)
- Item complexity weights
- Workload adjustment method
- Shrinkage strength
"""

import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.mock_data import generate_mock_data
from src.scoring.score_shift import compute_scores


def sweep_weight_parameter(
    orders_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    staffing_df: pd.DataFrame,
    param_name: str,
    param_values: List[float],
) -> pd.DataFrame:
    """Sweep a single weight parameter and measure score changes.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame
        param_name: Parameter to vary ('efficiency', 'throughput', or 'consistency')
        param_values: List of values to test

    Returns:
        DataFrame with parameter values and resulting scores
    """
    results_records = []

    for param_value in param_values:
        # Adjust weights to maintain sum = 1.0
        if param_name == "efficiency":
            weights = {
                "efficiency": param_value,
                "throughput": (1 - param_value) * 0.6,
                "consistency": (1 - param_value) * 0.4,
            }
        elif param_name == "throughput":
            weights = {
                "efficiency": (1 - param_value) * 0.7,
                "throughput": param_value,
                "consistency": (1 - param_value) * 0.3,
            }
        else:  # consistency
            weights = {
                "efficiency": (1 - param_value) * 0.625,
                "throughput": (1 - param_value) * 0.375,
                "consistency": param_value,
            }

        config = {
            "weights": weights,
            "item_weights": {},
            "workload_adjustment": "multiplicative",
            "shrinkage_strength": 0.3,
        }

        results = compute_scores(orders_df, shifts_df, staffing_df, config)

        # Extract scores
        for shift_id, waiters in results.items():
            for waiter_id, data in waiters.items():
                results_records.append(
                    {
                        "param_value": param_value,
                        "shift_id": shift_id,
                        "waiter_id": waiter_id,
                        "score": data["score"],
                        "confidence": data["confidence"],
                    }
                )

    return pd.DataFrame(results_records)


def analyze_weight_sensitivity(sweep_df: pd.DataFrame, param_name: str) -> dict:
    """Analyze sensitivity of scores to weight parameter.

    Args:
        sweep_df: Output from sweep_weight_parameter()
        param_name: Parameter name for reporting

    Returns:
        Dictionary with sensitivity statistics
    """
    # Compute score variance across parameter values for each waiter
    waiter_variance = (
        sweep_df.groupby(["waiter_id", "shift_id"])["score"]
        .agg(["mean", "std", "min", "max"])
        .reset_index()
    )
    waiter_variance["range"] = waiter_variance["max"] - waiter_variance["min"]

    stats = {
        "param_name": param_name,
        "mean_std": waiter_variance["std"].mean(),
        "mean_range": waiter_variance["range"].mean(),
        "max_range": waiter_variance["range"].max(),
        "pct_high_sensitivity": (waiter_variance["range"] > 10).mean() * 100,
    }

    print(f"\n=== Sensitivity to {param_name.upper()} weight ===")
    print(f"Mean score std dev across weight values: {stats['mean_std']:.2f}")
    print(f"Mean score range: {stats['mean_range']:.2f}")
    print(f"Max score range: {stats['max_range']:.2f}")
    print(
        f"Pct with range > 10 points: {stats['pct_high_sensitivity']:.1f}% "
        f"(high sensitivity)"
    )

    return stats


def sweep_shrinkage_strength(
    orders_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    staffing_df: pd.DataFrame,
    shrinkage_values: List[float],
) -> pd.DataFrame:
    """Test sensitivity to shrinkage strength parameter.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame
        shrinkage_values: List of shrinkage strength values (0-1)

    Returns:
        DataFrame with results
    """
    results_records = []

    base_config = {
        "weights": {"efficiency": 0.50, "throughput": 0.30, "consistency": 0.20},
        "item_weights": {},
        "workload_adjustment": "multiplicative",
    }

    for shrinkage in shrinkage_values:
        config = {**base_config, "shrinkage_strength": shrinkage}
        results = compute_scores(orders_df, shifts_df, staffing_df, config)

        for shift_id, waiters in results.items():
            for waiter_id, data in waiters.items():
                results_records.append(
                    {
                        "shrinkage": shrinkage,
                        "shift_id": shift_id,
                        "waiter_id": waiter_id,
                        "score": data["score"],
                        "confidence": data["confidence"],
                    }
                )

    return pd.DataFrame(results_records)


def analyze_shrinkage_impact(sweep_df: pd.DataFrame) -> dict:
    """Analyze impact of shrinkage on low vs high confidence scores.

    Args:
        sweep_df: Output from sweep_shrinkage_strength()

    Returns:
        Dictionary with impact statistics
    """
    # Compare impact on low vs high confidence scores
    low_conf = sweep_df[sweep_df["confidence"] < 0.5]
    high_conf = sweep_df[sweep_df["confidence"] >= 0.7]

    low_conf_variance = (
        low_conf.groupby(["waiter_id", "shift_id"])["score"].std().mean()
        if not low_conf.empty
        else 0
    )
    high_conf_variance = (
        high_conf.groupby(["waiter_id", "shift_id"])["score"].std().mean()
        if not high_conf.empty
        else 0
    )

    stats = {
        "low_conf_score_std": low_conf_variance,
        "high_conf_score_std": high_conf_variance,
        "ratio": low_conf_variance / high_conf_variance if high_conf_variance > 0 else 0,
    }

    print("\n=== Shrinkage Strength Impact ===")
    print(
        f"Score std for low-confidence (<0.5): {stats['low_conf_score_std']:.2f}"
    )
    print(
        f"Score std for high-confidence (>=0.7): {stats['high_conf_score_std']:.2f}"
    )
    print(
        f"Ratio: {stats['ratio']:.2f}x (shrinkage affects low-confidence more)"
    )

    return stats


def test_workload_adjustment_methods(
    orders_df: pd.DataFrame, shifts_df: pd.DataFrame, staffing_df: pd.DataFrame
) -> dict:
    """Compare multiplicative vs stratified workload adjustment.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame

    Returns:
        Dictionary with comparison results
    """
    base_config = {
        "weights": {"efficiency": 0.50, "throughput": 0.30, "consistency": 0.20},
        "item_weights": {},
        "shrinkage_strength": 0.3,
    }

    # Multiplicative method
    config_mult = {**base_config, "workload_adjustment": "multiplicative"}
    results_mult = compute_scores(orders_df, shifts_df, staffing_df, config_mult)

    # Stratified method (uses unadjusted in current MVP)
    config_strat = {**base_config, "workload_adjustment": "stratified"}
    results_strat = compute_scores(orders_df, shifts_df, staffing_df, config_strat)

    # Extract scores and compare
    scores_mult = []
    scores_strat = []

    for shift_id in results_mult.keys():
        for waiter_id in results_mult[shift_id].keys():
            scores_mult.append(results_mult[shift_id][waiter_id]["score"])
            scores_strat.append(results_strat[shift_id][waiter_id]["score"])

    scores_mult = np.array(scores_mult)
    scores_strat = np.array(scores_strat)

    stats = {
        "mean_diff": (scores_mult - scores_strat).mean(),
        "mean_abs_diff": np.abs(scores_mult - scores_strat).mean(),
        "correlation": np.corrcoef(scores_mult, scores_strat)[0, 1],
        "pct_diff_over_5": (np.abs(scores_mult - scores_strat) > 5).mean() * 100,
    }

    print("\n=== Workload Adjustment Method Comparison ===")
    print(f"Mean difference (mult - strat): {stats['mean_diff']:.2f}")
    print(f"Mean absolute difference: {stats['mean_abs_diff']:.2f}")
    print(f"Correlation: {stats['correlation']:.3f}")
    print(
        f"Pct with >5 point difference: {stats['pct_diff_over_5']:.1f}%"
    )

    return stats


def run_sensitivity_analysis(
    orders_df: pd.DataFrame, shifts_df: pd.DataFrame, staffing_df: pd.DataFrame
) -> None:
    """Run complete sensitivity analysis.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame
    """
    print("=" * 60)
    print("SENSITIVITY ANALYSIS")
    print("=" * 60)

    # Test efficiency weight
    print("\n[1/5] Testing efficiency weight sensitivity...")
    eff_sweep = sweep_weight_parameter(
        orders_df, shifts_df, staffing_df, "efficiency", [0.3, 0.4, 0.5, 0.6, 0.7]
    )
    analyze_weight_sensitivity(eff_sweep, "efficiency")

    # Test throughput weight
    print("\n[2/5] Testing throughput weight sensitivity...")
    thr_sweep = sweep_weight_parameter(
        orders_df, shifts_df, staffing_df, "throughput", [0.1, 0.2, 0.3, 0.4, 0.5]
    )
    analyze_weight_sensitivity(thr_sweep, "throughput")

    # Test consistency weight
    print("\n[3/5] Testing consistency weight sensitivity...")
    cons_sweep = sweep_weight_parameter(
        orders_df, shifts_df, staffing_df, "consistency", [0.1, 0.15, 0.2, 0.25, 0.3]
    )
    analyze_weight_sensitivity(cons_sweep, "consistency")

    # Test shrinkage strength
    print("\n[4/5] Testing shrinkage strength sensitivity...")
    shrink_sweep = sweep_shrinkage_strength(
        orders_df, shifts_df, staffing_df, [0.0, 0.2, 0.4, 0.6, 0.8]
    )
    analyze_shrinkage_impact(shrink_sweep)

    # Test workload adjustment
    print("\n[5/5] Testing workload adjustment methods...")
    test_workload_adjustment_methods(orders_df, shifts_df, staffing_df)

    print("\n" + "=" * 60)
    print("SENSITIVITY ANALYSIS COMPLETE")
    print("=" * 60)


def main() -> None:
    """Run sensitivity analysis on mock data."""
    print("Generating mock data...")
    orders_df, shifts_df, staffing_df = generate_mock_data(
        n_shifts=10, n_waiters=8, orders_per_shift=50
    )

    run_sensitivity_analysis(orders_df, shifts_df, staffing_df)


if __name__ == "__main__":
    main()
