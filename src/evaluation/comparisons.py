"""Compare naive vs complexity-adjusted rankings.

Analyzes how much complexity adjustment changes waiter rankings
and identifies cases of rank inversion (where adjustment meaningfully
changes relative performance assessment).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.mock_data import generate_mock_data
from src.scoring.score_shift import compute_scores


def compute_naive_rankings(orders_df: pd.DataFrame) -> pd.DataFrame:
    """Compute naive rankings based solely on mean cycle time.

    Args:
        orders_df: Orders DataFrame

    Returns:
        DataFrame with waiter_id, shift_id, naive_rank, mean_cycle_time
    """
    orders_df = orders_df.copy()
    orders_df["cycle_time"] = (
        pd.to_datetime(orders_df["completed_ts"]) - pd.to_datetime(orders_df["accepted_ts"])
    ).dt.total_seconds()

    # Compute mean cycle time per waiter per waiter_shift_id
    naive_stats = (
        orders_df.groupby(["waiter_shift_id", "assigned_waiter_id"])["cycle_time"]
        .mean()
        .reset_index()
    )
    naive_stats.rename(
        columns={"assigned_waiter_id": "waiter_id", "cycle_time": "mean_cycle_time",
                 "waiter_shift_id": "shift_id"}, inplace=True
    )

    # Rank within each shift (lower cycle time = better rank)
    naive_stats["naive_rank"] = naive_stats.groupby("shift_id")["mean_cycle_time"].rank(
        ascending=True
    )

    return naive_stats


def compute_adjusted_rankings(results: dict) -> pd.DataFrame:
    """Extract rankings from scoring results.

    Args:
        results: Output from compute_scores()

    Returns:
        DataFrame with waiter_id, shift_id, adjusted_rank, adjusted_score
    """
    records = []
    for shift_id, waiters in results.items():
        for waiter_id, data in waiters.items():
            records.append(
                {"shift_id": shift_id, "waiter_id": waiter_id, "adjusted_score": data["score"]}
            )

    adjusted_df = pd.DataFrame(records)

    # Rank within each shift (higher score = better rank)
    adjusted_df["adjusted_rank"] = adjusted_df.groupby("shift_id")["adjusted_score"].rank(
        ascending=False
    )

    return adjusted_df


def compare_rankings(
    naive_df: pd.DataFrame, adjusted_df: pd.DataFrame, rank_threshold: int = 2
) -> pd.DataFrame:
    """Compare naive and adjusted rankings.

    Args:
        naive_df: Naive rankings DataFrame
        adjusted_df: Adjusted rankings DataFrame
        rank_threshold: Minimum rank change to consider significant

    Returns:
        DataFrame with rank comparisons and inversions
    """
    naive_df = naive_df.copy()
    adjusted_df = adjusted_df.copy()
    naive_df["shift_id"] = naive_df["shift_id"].astype(str)
    adjusted_df["shift_id"] = adjusted_df["shift_id"].astype(str)
    comparison = naive_df.merge(adjusted_df, on=["shift_id", "waiter_id"], how="outer")

    comparison["rank_change"] = comparison["adjusted_rank"] - comparison["naive_rank"]
    comparison["abs_rank_change"] = comparison["rank_change"].abs()
    comparison["rank_inverted"] = comparison["abs_rank_change"] >= rank_threshold

    return comparison


def analyze_rank_inversions(comparison_df: pd.DataFrame) -> dict:
    """Analyze rank inversion statistics.

    Args:
        comparison_df: Output from compare_rankings()

    Returns:
        Dictionary with inversion statistics
    """
    stats = {
        "total_comparisons": len(comparison_df),
        "n_inversions": comparison_df["rank_inverted"].sum(),
        "inversion_rate": comparison_df["rank_inverted"].mean() * 100,
        "mean_rank_change": comparison_df["rank_change"].mean(),
        "mean_abs_rank_change": comparison_df["abs_rank_change"].mean(),
        "max_rank_improvement": comparison_df["rank_change"].min(),  # Negative = improvement
        "max_rank_decline": comparison_df["rank_change"].max(),
    }

    print("\n=== Rank Inversion Analysis ===")
    print(f"Total waiter-shift comparisons: {stats['total_comparisons']}")
    print(f"Significant rank changes: {stats['n_inversions']} ({stats['inversion_rate']:.1f}%)")
    print(f"Mean absolute rank change: {stats['mean_abs_rank_change']:.2f}")
    print(f"Largest improvement: {-stats['max_rank_improvement']:.0f} positions")
    print(f"Largest decline: {stats['max_rank_decline']:.0f} positions")

    return stats


def identify_affected_waiters(comparison_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Identify waiters most affected by complexity adjustment.

    Args:
        comparison_df: Output from compare_rankings()
        top_n: Number of top affected waiters to return

    Returns:
        DataFrame of most affected waiters
    """
    # Aggregate by waiter across all shifts
    waiter_impact = (
        comparison_df.groupby("waiter_id")
        .agg(
            n_shifts=("shift_id", "count"),
            mean_rank_change=("rank_change", "mean"),
            mean_abs_rank_change=("abs_rank_change", "mean"),
            n_inversions=("rank_inverted", "sum"),
        )
        .reset_index()
    )

    # Sort by absolute impact
    waiter_impact = waiter_impact.sort_values("mean_abs_rank_change", ascending=False)

    print("\n=== Top Affected Waiters ===")
    print(waiter_impact.head(top_n).to_string(index=False))

    return waiter_impact.head(top_n)


def analyze_direction_of_adjustment(comparison_df: pd.DataFrame) -> dict:
    """Analyze whether adjustments favor certain waiter types.

    Args:
        comparison_df: Output from compare_rankings()

    Returns:
        Dictionary with directional analysis
    """
    # Positive rank_change = rank got worse (higher number)
    # Negative rank_change = rank improved (lower number)

    improved = comparison_df[comparison_df["rank_change"] < -1]
    declined = comparison_df[comparison_df["rank_change"] > 1]

    stats = {
        "n_improved": len(improved),
        "n_declined": len(declined),
        "n_unchanged": len(comparison_df) - len(improved) - len(declined),
        "mean_improvement": improved["rank_change"].mean() if len(improved) > 0 else 0,
        "mean_decline": declined["rank_change"].mean() if len(declined) > 0 else 0,
    }

    print("\n=== Direction of Adjustment ===")
    print(f"Improved ranking: {stats['n_improved']} waiters")
    print(f"Declined ranking: {stats['n_declined']} waiters")
    print(f"Roughly unchanged: {stats['n_unchanged']} waiters")

    return stats


def run_comparison_analysis(
    orders_df: pd.DataFrame, shifts_df: pd.DataFrame, staffing_df: pd.DataFrame
) -> None:
    """Run full comparison analysis.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame
    """
    print("=" * 60)
    print("NAIVE VS ADJUSTED RANKING COMPARISON")
    print("=" * 60)

    # Compute naive rankings
    print("\nComputing naive rankings (mean cycle time only)...")
    naive_df = compute_naive_rankings(orders_df)

    # Compute adjusted rankings
    print("Computing complexity-adjusted rankings...")
    config = {
        "weights": {"efficiency": 0.50, "throughput": 0.30, "consistency": 0.20},
        "item_weights": {},
        "workload_adjustment": "multiplicative",
        "shrinkage_strength": 0.3,
        "winsorize_quantile": 0.05,
    }
    results = compute_scores(orders_df, shifts_df, staffing_df, config)
    adjusted_df = compute_adjusted_rankings(results)

    # Compare rankings
    print("Comparing rankings...")
    comparison_df = compare_rankings(naive_df, adjusted_df, rank_threshold=2)

    # Analyze inversions
    analyze_rank_inversions(comparison_df)

    # Identify affected waiters
    identify_affected_waiters(comparison_df, top_n=5)

    # Analyze direction
    analyze_direction_of_adjustment(comparison_df)

    # Show examples of large inversions
    print("\n=== Example Large Inversions ===")
    large_inversions = comparison_df[comparison_df["abs_rank_change"] >= 3].head(5)
    if not large_inversions.empty:
        print(
            large_inversions[
                ["shift_id", "waiter_id", "naive_rank", "adjusted_rank", "rank_change"]
            ].to_string(index=False)
        )
    else:
        print("No large inversions found (threshold: 3 positions)")


def main() -> None:
    """Run comparison analysis on mock data."""
    print("Generating mock data...")
    orders_df, shifts_df, staffing_df = generate_mock_data(
        n_shifts=10, n_waiters=8, orders_per_shift=50
    )

    run_comparison_analysis(orders_df, shifts_df, staffing_df)


if __name__ == "__main__":
    main()
