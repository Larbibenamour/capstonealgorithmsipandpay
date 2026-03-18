"""Ablation studies for the waiter performance scoring algorithm.

Tests the necessity of each pipeline component by disabling one at a time
and measuring the impact on rankings vs the full method. This corresponds to
thesis Section 8.3 (Ablation Studies).

Ablations implemented:
  A) No complexity adjustment — treat all orders as complexity=1 (eff_raw = cycle_time)
  B) No workload adjustment  — bypass staffing intensity factor (eff_raw_adjusted = eff_raw)
  C) No shrinkage            — set shrinkage_strength=0.0 (alpha = 0)
  D) Single-component        — efficiency only (w_eff=1.0, w_thr=0.0, w_cons=0.0)

Usage:
    python -m src.evaluation.ablations
    # or
    PYTHONPATH=. python src/evaluation/ablations.py
"""

import sys
from pathlib import Path
from typing import Dict

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.mock_data import generate_mock_data
from src.evaluation.comparisons import (
    analyze_rank_inversions,
    compare_rankings,
    compute_adjusted_rankings,
    compute_naive_rankings,
)
from src.scoring.score_shift import compute_scores

# ---------------------------------------------------------------------------
# Default (full-pipeline) config — must match the standard evaluation config
# so ablation comparisons are meaningful.
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG = {
    "weights": {"efficiency": 0.50, "throughput": 0.30, "consistency": 0.20},
    "item_weights": {},
    "workload_adjustment": "multiplicative",
    "shrinkage_strength": 0.3,
    "winsorize_quantile": 0.05,
}


def _flatten_complexity(orders_df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of orders_df where every order has complexity = 1.

    Replaces each order's items with a single item of quantity=1 so that
    complexity_units = 1.0 for all orders. This means eff_raw = cycle_time
    (no complexity normalisation), which is the 'no complexity adjustment'
    ablation condition.

    Does NOT modify the input DataFrame.
    """
    df = orders_df.copy()
    df["items"] = [[{"item_id": "item_1", "quantity": 1}]] * len(df)
    return df


def run_ablation(
    label: str,
    orders_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    staffing_df: pd.DataFrame,
    config: dict,
    full_adjusted_df: pd.DataFrame,
) -> Dict:
    """Run a single ablation and compare its rankings to the full method.

    Args:
        label: Short name for printing (e.g., 'A — No Complexity').
        orders_df: Orders DataFrame (possibly preprocessed for the ablation).
        shifts_df: Shifts DataFrame.
        staffing_df: Staffing DataFrame.
        config: Ablation config dict.
        full_adjusted_df: Adjusted rankings from the full pipeline (for comparison).

    Returns:
        Dictionary with inversion statistics between this ablation and the full method.
    """
    results = compute_scores(orders_df, shifts_df, staffing_df, config)
    ablation_df = compute_adjusted_rankings(results)

    # Rename adjusted_rank/score columns so compare_rankings works correctly
    ablation_df = ablation_df.rename(
        columns={"adjusted_rank": "naive_rank", "adjusted_score": "mean_cycle_time"}
    )
    full_df = full_adjusted_df.copy()
    full_df["shift_id"] = full_df["shift_id"].astype(str)
    ablation_df["shift_id"] = ablation_df["shift_id"].astype(str)

    comparison = ablation_df.merge(
        full_df[["shift_id", "waiter_id", "adjusted_rank"]],
        on=["shift_id", "waiter_id"],
        how="outer",
    )
    comparison["rank_change"] = comparison["adjusted_rank"] - comparison["naive_rank"]
    comparison["abs_rank_change"] = comparison["rank_change"].abs()
    comparison["rank_inverted"] = comparison["abs_rank_change"] >= 2

    stats = {
        "ablation": label,
        "total_comparisons": len(comparison),
        "n_rank_changes": int(comparison["rank_inverted"].sum()),
        "inversion_rate_pct": float(comparison["rank_inverted"].mean() * 100),
        "mean_abs_rank_change": float(comparison["abs_rank_change"].mean()),
    }
    return stats


def run_ablation_study(
    orders_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    staffing_df: pd.DataFrame,
) -> pd.DataFrame:
    """Run all four ablation studies and return a summary DataFrame.

    Each ablation disables one pipeline component and compares its output
    rankings to the full-pipeline rankings. A high rank-inversion rate
    indicates that the removed component had a meaningful impact.

    Args:
        orders_df: Orders DataFrame from generate_mock_data or real data.
        shifts_df: Shifts DataFrame.
        staffing_df: Staffing DataFrame.

    Returns:
        DataFrame with one row per ablation, showing rank change statistics.
    """
    print("=" * 60)
    print("ABLATION STUDIES — Thesis Section 8.3")
    print("=" * 60)
    print("Each ablation disables one component and compares rankings")
    print("to the FULL pipeline. Higher inversion rate = component matters more.\n")

    # -----------------------------------------------------------------------
    # Step 0: Compute full-pipeline rankings (the reference)
    # -----------------------------------------------------------------------
    full_results = compute_scores(orders_df, shifts_df, staffing_df, _DEFAULT_CONFIG)
    full_adjusted_df = compute_adjusted_rankings(full_results)

    results_list = []

    # -----------------------------------------------------------------------
    # Ablation A: No complexity adjustment
    # All orders treated as having complexity = 1, so eff_raw = cycle_time.
    # Implemented by flattening item lists to a single item of quantity=1.
    # -----------------------------------------------------------------------
    print("[A] No complexity adjustment (eff_raw = cycle_time)...")
    orders_flat = _flatten_complexity(orders_df)
    stats_a = run_ablation(
        "A — No Complexity",
        orders_flat,
        shifts_df,
        staffing_df,
        _DEFAULT_CONFIG,
        full_adjusted_df,
    )
    results_list.append(stats_a)
    print(
        f"    Rank inversions vs full: {stats_a['n_rank_changes']} "
        f"({stats_a['inversion_rate_pct']:.1f}%), "
        f"mean |rank change|: {stats_a['mean_abs_rank_change']:.2f}"
    )

    # -----------------------------------------------------------------------
    # Ablation B: No workload adjustment
    # workload_adjustment='stratified' falls into the else-branch in
    # compute_scores which uses eff_raw directly (no staffing factor applied).
    # -----------------------------------------------------------------------
    print("[B] No workload adjustment (eff_raw_adjusted = eff_raw)...")
    config_b = {**_DEFAULT_CONFIG, "workload_adjustment": "stratified"}
    stats_b = run_ablation(
        "B — No Workload Adj.",
        orders_df,
        shifts_df,
        staffing_df,
        config_b,
        full_adjusted_df,
    )
    results_list.append(stats_b)
    print(
        f"    Rank inversions vs full: {stats_b['n_rank_changes']} "
        f"({stats_b['inversion_rate_pct']:.1f}%), "
        f"mean |rank change|: {stats_b['mean_abs_rank_change']:.2f}"
    )

    # -----------------------------------------------------------------------
    # Ablation C: No shrinkage (alpha = 0)
    # shrinkage_strength=0.0 means: final_score = raw_score for all waiters.
    # -----------------------------------------------------------------------
    print("[C] No shrinkage (shrinkage_strength = 0.0)...")
    config_c = {**_DEFAULT_CONFIG, "shrinkage_strength": 0.0}
    stats_c = run_ablation(
        "C — No Shrinkage",
        orders_df,
        shifts_df,
        staffing_df,
        config_c,
        full_adjusted_df,
    )
    results_list.append(stats_c)
    print(
        f"    Rank inversions vs full: {stats_c['n_rank_changes']} "
        f"({stats_c['inversion_rate_pct']:.1f}%), "
        f"mean |rank change|: {stats_c['mean_abs_rank_change']:.2f}"
    )

    # -----------------------------------------------------------------------
    # Ablation D: Single-component scoring (efficiency only)
    # w_eff=1.0 so composite_score = efficiency_score.
    # -----------------------------------------------------------------------
    print("[D] Single-component scoring (w_eff=1.0, w_thr=0.0, w_cons=0.0)...")
    config_d = {
        **_DEFAULT_CONFIG,
        "weights": {"efficiency": 1.0, "throughput": 0.0, "consistency": 0.0},
    }
    stats_d = run_ablation(
        "D — Single Component",
        orders_df,
        shifts_df,
        staffing_df,
        config_d,
        full_adjusted_df,
    )
    results_list.append(stats_d)
    print(
        f"    Rank inversions vs full: {stats_d['n_rank_changes']} "
        f"({stats_d['inversion_rate_pct']:.1f}%), "
        f"mean |rank change|: {stats_d['mean_abs_rank_change']:.2f}"
    )

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    summary_df = pd.DataFrame(results_list)
    summary_df = summary_df.set_index("ablation")

    print("\n=== Ablation Summary ===")
    print(summary_df.to_string())
    print(
        "\nInterpretation: Higher inversion rate = the removed component changes"
        " rankings more = the component contributes more to the full method."
    )

    return summary_df


def main() -> None:
    """Run ablation studies on standard mock data."""
    print("Generating mock data (10 shifts, 8 waiters, 50 orders/shift)...")
    orders_df, shifts_df, staffing_df = generate_mock_data(
        n_shifts=10, n_waiters=8, orders_per_shift=50, seed=42
    )
    run_ablation_study(orders_df, shifts_df, staffing_df)


if __name__ == "__main__":
    main()
