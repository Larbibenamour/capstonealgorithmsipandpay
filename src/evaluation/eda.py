"""Exploratory Data Analysis for order and performance data.

Generates visualizations and summary statistics to understand:
- Cycle time distributions
- Order complexity patterns
- Correlations between complexity and cycle time
- Staffing patterns
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.mock_data import generate_mock_data
from src.scoring.complexity import compute_order_complexity


def analyze_cycle_times(orders_df: pd.DataFrame) -> dict:
    """Analyze cycle time distribution and statistics.

    Args:
        orders_df: Orders DataFrame

    Returns:
        Dictionary with summary statistics
    """
    # Convert to datetime if needed
    orders_df["accepted_ts"] = pd.to_datetime(orders_df["accepted_ts"])
    orders_df["completed_ts"] = pd.to_datetime(orders_df["completed_ts"])

    # Compute cycle times
    orders_df["cycle_time_seconds"] = (
        orders_df["completed_ts"] - orders_df["accepted_ts"]
    ).dt.total_seconds()

    stats = {
        "mean": orders_df["cycle_time_seconds"].mean(),
        "median": orders_df["cycle_time_seconds"].median(),
        "std": orders_df["cycle_time_seconds"].std(),
        "min": orders_df["cycle_time_seconds"].min(),
        "max": orders_df["cycle_time_seconds"].max(),
        "q25": orders_df["cycle_time_seconds"].quantile(0.25),
        "q75": orders_df["cycle_time_seconds"].quantile(0.75),
    }

    print("\n=== Cycle Time Analysis ===")
    print(f"Mean: {stats['mean']:.1f}s ({stats['mean']/60:.1f} min)")
    print(f"Median: {stats['median']:.1f}s ({stats['median']/60:.1f} min)")
    print(f"Std Dev: {stats['std']:.1f}s")
    print(f"Range: [{stats['min']:.1f}s, {stats['max']:.1f}s]")
    print(f"IQR: [{stats['q25']:.1f}s, {stats['q75']:.1f}s]")

    return stats


def analyze_complexity(orders_df: pd.DataFrame, item_weights: dict = None) -> dict:
    """Analyze order complexity distribution.

    Args:
        orders_df: Orders DataFrame
        item_weights: Item complexity weights

    Returns:
        Dictionary with complexity statistics
    """
    if item_weights is None:
        item_weights = {}

    # Parse orders and compute complexity
    from src.scoring.schema import Order, OrderItem

    complexities = []
    for _, row in orders_df.iterrows():
        items = row["items"]
        if isinstance(items, str):
            import json

            items = json.loads(items)

        order_items = [OrderItem(**item) if isinstance(item, dict) else item for item in items]

        order = Order(
            order_id=row["order_id"],
            waiter_shift_id=row["waiter_shift_id"],
            assigned_waiter_id=row["assigned_waiter_id"],
            accepted_ts=pd.to_datetime(row["accepted_ts"]),
            completed_ts=pd.to_datetime(row["completed_ts"]),
            items=order_items,
        )

        complexity = compute_order_complexity(order, item_weights, default_weight=1.0)
        complexities.append(complexity)

    complexity_series = pd.Series(complexities)

    stats = {
        "mean": complexity_series.mean(),
        "median": complexity_series.median(),
        "std": complexity_series.std(),
        "min": complexity_series.min(),
        "max": complexity_series.max(),
    }

    print("\n=== Order Complexity Analysis ===")
    print(f"Mean: {stats['mean']:.2f} units")
    print(f"Median: {stats['median']:.2f} units")
    print(f"Std Dev: {stats['std']:.2f}")
    print(f"Range: [{stats['min']:.2f}, {stats['max']:.2f}]")

    return stats


def analyze_complexity_time_correlation(orders_df: pd.DataFrame, item_weights: dict = None) -> float:
    """Analyze correlation between order complexity and cycle time.

    Args:
        orders_df: Orders DataFrame
        item_weights: Item complexity weights

    Returns:
        Pearson correlation coefficient
    """
    if item_weights is None:
        item_weights = {}

    # Compute cycle times and complexities
    from src.scoring.schema import Order, OrderItem

    records = []
    for _, row in orders_df.iterrows():
        items = row["items"]
        if isinstance(items, str):
            import json

            items = json.loads(items)

        order_items = [OrderItem(**item) if isinstance(item, dict) else item for item in items]

        order = Order(
            order_id=row["order_id"],
            waiter_shift_id=row["waiter_shift_id"],
            assigned_waiter_id=row["assigned_waiter_id"],
            accepted_ts=pd.to_datetime(row["accepted_ts"]),
            completed_ts=pd.to_datetime(row["completed_ts"]),
            items=order_items,
        )

        complexity = compute_order_complexity(order, item_weights, default_weight=1.0)
        cycle_time = order.cycle_time_seconds

        records.append({"complexity": complexity, "cycle_time": cycle_time})

    df = pd.DataFrame(records)
    correlation = df["complexity"].corr(df["cycle_time"])

    print("\n=== Complexity-Time Correlation ===")
    print(f"Pearson correlation: {correlation:.3f}")

    if correlation > 0.5:
        print("Strong positive correlation - complexity predicts cycle time well")
    elif correlation > 0.3:
        print("Moderate positive correlation - complexity partially predicts cycle time")
    else:
        print("Weak correlation - other factors dominate cycle time")

    return correlation


def analyze_waiter_performance(orders_df: pd.DataFrame) -> pd.DataFrame:
    """Analyze raw performance metrics by waiter.

    Args:
        orders_df: Orders DataFrame

    Returns:
        DataFrame with waiter-level summary statistics
    """
    # Compute cycle times
    orders_df = orders_df.copy()
    orders_df["cycle_time_seconds"] = (
        pd.to_datetime(orders_df["completed_ts"]) - pd.to_datetime(orders_df["accepted_ts"])
    ).dt.total_seconds()

    # Aggregate by waiter
    waiter_stats = (
        orders_df.groupby("assigned_waiter_id")["cycle_time_seconds"]
        .agg(
            n_orders="count",
            mean_cycle_time="mean",
            median_cycle_time="median",
            std_cycle_time="std",
        )
        .reset_index()
    )

    print("\n=== Waiter Performance Summary ===")
    print(waiter_stats.to_string(index=False))

    return waiter_stats


def run_full_eda(orders_df: pd.DataFrame, shifts_df: pd.DataFrame, staffing_df: pd.DataFrame) -> None:
    """Run complete EDA on all data.

    Args:
        orders_df: Orders DataFrame
        shifts_df: Shifts DataFrame
        staffing_df: Staffing DataFrame
    """
    print("=" * 60)
    print("EXPLORATORY DATA ANALYSIS")
    print("=" * 60)

    print(f"\nDataset sizes:")
    print(f"  Orders: {len(orders_df)}")
    print(f"  Shifts: {len(shifts_df)}")
    print(f"  Staffing buckets: {len(staffing_df)}")

    # Cycle time analysis
    analyze_cycle_times(orders_df)

    # Complexity analysis
    analyze_complexity(orders_df)

    # Correlation analysis
    analyze_complexity_time_correlation(orders_df)

    # Waiter performance
    analyze_waiter_performance(orders_df)

    # Shift analysis
    print("\n=== Shift Summary ===")
    orders_per_shift = orders_df.groupby("waiter_shift_id").size()
    print(f"Orders per shift - Mean: {orders_per_shift.mean():.1f}, "
          f"Median: {orders_per_shift.median():.1f}")

    # Staffing patterns
    print("\n=== Staffing Patterns ===")
    print(f"Mean active waiters: {staffing_df['active_waiter_count'].mean():.1f}")
    print(f"Range: [{staffing_df['active_waiter_count'].min()}, "
          f"{staffing_df['active_waiter_count'].max()}]")


def main() -> None:
    """Run EDA on mock data."""
    print("Generating mock data...")
    orders_df, shifts_df, staffing_df = generate_mock_data(
        n_shifts=10, n_waiters=8, orders_per_shift=50
    )

    run_full_eda(orders_df, shifts_df, staffing_df)


if __name__ == "__main__":
    main()
