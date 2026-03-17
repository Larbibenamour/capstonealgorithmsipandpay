"""Feature extraction for waiter performance metrics.

Computes efficiency, throughput, and consistency features from order data.
All metrics are computed per waiter per shift for within-shift comparisons.
"""

from typing import Dict, List, Union

import numpy as np
import pandas as pd

from src.scoring.complexity import compute_complexity_adjusted_cycle_time, compute_order_complexity
from src.scoring.schema import Order


def compute_efficiency_raw_values(
    orders: List[Order], item_weights: Dict[Union[str, int], float], epsilon: float = 1e-6
) -> pd.DataFrame:
    """Compute raw efficiency metrics for each order.

    Efficiency raw (eff_raw) = cycle_time / complexity_units
    Lower values indicate better efficiency (faster completion per unit complexity).

    Args:
        orders: List of orders
        item_weights: Item complexity weight mapping
        epsilon: Small constant to prevent division by zero

    Returns:
        DataFrame with columns: order_id, shift_id, waiter_id, cycle_time,
                                 complexity, eff_raw

    Examples:
        >>> orders = [
        ...     Order(order_id=1, shift_id=1, assigned_waiter_id="W1",
        ...           cycle_time=600, items=[OrderItem("A", 2)], ...),
        ... ]
        >>> df = compute_efficiency_raw_values(orders, {"A": 1.0})
        >>> df.loc[0, "eff_raw"]
        300.0  # 600 / 2
    """
    records = []
    for order in orders:
        complexity = compute_order_complexity(order, item_weights, default_weight=1.0)
        eff_raw = compute_complexity_adjusted_cycle_time(
            order.cycle_time_seconds, complexity, epsilon
        )
        records.append(
            {
                "order_id": order.order_id,
                "shift_id": order.waiter_shift_id,
                "waiter_id": order.assigned_waiter_id,
                "cycle_time": order.cycle_time_seconds,
                "complexity": complexity,
                "eff_raw": eff_raw,
            }
        )
    return pd.DataFrame(records)


def compute_waiter_efficiency_stats(eff_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate efficiency statistics per waiter per shift.

    Computes median, mean, IQR, and MAD of eff_raw for each waiter in each shift.

    Args:
        eff_df: DataFrame from compute_efficiency_raw_values()

    Returns:
        DataFrame with columns: shift_id, waiter_id, n_orders, median_eff_raw,
                                 mean_eff_raw, eff_iqr, eff_mad

    Examples:
        >>> eff_df = pd.DataFrame({
        ...     "shift_id": [1, 1, 1],
        ...     "waiter_id": ["W1", "W1", "W2"],
        ...     "eff_raw": [100, 120, 90]
        ... })
        >>> stats = compute_waiter_efficiency_stats(eff_df)
        >>> stats.loc[stats.waiter_id == "W1", "median_eff_raw"].values[0]
        110.0
    """
    grouped = eff_df.groupby(["shift_id", "waiter_id"])

    stats = grouped.agg(
        n_orders=("eff_raw", "count"),
        median_eff_raw=("eff_raw", "median"),
        mean_eff_raw=("eff_raw", "mean"),
        eff_iqr=("eff_raw", lambda x: np.percentile(x, 75) - np.percentile(x, 25)),
        eff_mad=("eff_raw", lambda x: np.median(np.abs(x - np.median(x)))),
    ).reset_index()

    return stats


def compute_throughput(
    orders: List[Order],
    item_weights: Dict[Union[str, int], float],
    waiter_active_hours: Dict[Union[str, int], float],
) -> pd.DataFrame:
    """Compute throughput (complexity units per active hour) per waiter per shift.

    Throughput = total_complexity_units / active_hours

    Args:
        orders: List of orders
        item_weights: Item complexity weight mapping
        waiter_active_hours: Mapping of (shift_id, waiter_id) to active hours

    Returns:
        DataFrame with columns: shift_id, waiter_id, total_complexity, active_hours, throughput

    Examples:
        >>> orders = [
        ...     Order(order_id=1, shift_id=1, assigned_waiter_id="W1",
        ...           items=[OrderItem("A", quantity=5)], ...),
        ... ]
        >>> item_weights = {"A": 2.0}
        >>> waiter_hours = {(1, "W1"): 4.0}
        >>> df = compute_throughput(orders, item_weights, waiter_hours)
        >>> df.loc[0, "throughput"]
        2.5  # (5 * 2.0) / 4.0
    """
    # Aggregate complexity by (shift_id, waiter_id)
    complexity_records = []
    for order in orders:
        complexity = compute_order_complexity(order, item_weights, default_weight=1.0)
        complexity_records.append(
            {
                "shift_id": order.waiter_shift_id,
                "waiter_id": order.assigned_waiter_id,
                "complexity": complexity,
            }
        )

    complexity_df = pd.DataFrame(complexity_records)
    total_complexity = (
        complexity_df.groupby(["shift_id", "waiter_id"])["complexity"].sum().reset_index()
    )
    total_complexity.rename(columns={"complexity": "total_complexity"}, inplace=True)

    # Add active hours
    hours_records = [
        {"shift_id": shift_id, "waiter_id": waiter_id, "active_hours": hours}
        for (shift_id, waiter_id), hours in waiter_active_hours.items()
    ]
    hours_df = pd.DataFrame(hours_records)

    # Merge and compute throughput
    throughput_df = total_complexity.merge(hours_df, on=["shift_id", "waiter_id"], how="left")
    throughput_df["active_hours"] = throughput_df["active_hours"].fillna(1.0)  # Prevent div by 0
    throughput_df["throughput"] = throughput_df["total_complexity"] / throughput_df["active_hours"]

    return throughput_df


def compute_consistency_score(
    eff_stats: pd.DataFrame, method: str = "iqr", epsilon: float = 1e-6
) -> pd.DataFrame:
    """Compute consistency score from efficiency dispersion.

    Consistency = 1 / (1 + normalized_dispersion)
    Lower dispersion → higher consistency.

    Args:
        eff_stats: DataFrame from compute_waiter_efficiency_stats()
        method: Dispersion metric to use ('iqr' or 'mad')
        epsilon: Small constant to prevent division by zero

    Returns:
        DataFrame with added column: consistency_raw

    Examples:
        >>> eff_stats = pd.DataFrame({
        ...     "shift_id": [1, 1],
        ...     "waiter_id": ["W1", "W2"],
        ...     "eff_iqr": [20, 50],
        ...     "median_eff_raw": [100, 100]
        ... })
        >>> result = compute_consistency_score(eff_stats, method="iqr")
        >>> result.loc[0, "consistency_raw"] > result.loc[1, "consistency_raw"]
        True  # W1 has lower IQR, higher consistency
    """
    if method == "iqr":
        dispersion_col = "eff_iqr"
    elif method == "mad":
        dispersion_col = "eff_mad"
    else:
        raise ValueError(f"Unknown consistency method: {method}")

    eff_stats = eff_stats.copy()

    # Normalize dispersion by median efficiency (coefficient of variation analog)
    eff_stats["normalized_dispersion"] = eff_stats[dispersion_col] / (
        eff_stats["median_eff_raw"] + epsilon
    )

    # Consistency score: higher is better
    eff_stats["consistency_raw"] = 1.0 / (1.0 + eff_stats["normalized_dispersion"])

    return eff_stats


def extract_waiter_active_hours_from_orders(
    orders: List[Order], shift_start_end: Dict[Union[str, int], tuple]
) -> Dict[tuple, float]:
    """Estimate waiter active hours from order timestamps (fallback method).

    Active hours = (last_completed_ts - first_accepted_ts) / 3600

    Args:
        orders: List of orders
        shift_start_end: Mapping of shift_id to (start_ts, end_ts)

    Returns:
        Dictionary mapping (shift_id, waiter_id) to estimated active hours

    Note:
        This is a rough estimate. Prefer clock-in/out logs if available.
    """
    waiter_times: Dict[tuple, Dict[str, float]] = {}

    for order in orders:
        key = (order.waiter_shift_id, order.assigned_waiter_id)
        if key not in waiter_times:
            waiter_times[key] = {"first_accepted": float("inf"), "last_completed": 0}

        waiter_times[key]["first_accepted"] = min(
            waiter_times[key]["first_accepted"], order.accepted_ts.timestamp()
        )
        waiter_times[key]["last_completed"] = max(
            waiter_times[key]["last_completed"], order.completed_ts.timestamp()
        )

    active_hours = {}
    for key, times in waiter_times.items():
        duration_seconds = times["last_completed"] - times["first_accepted"]
        active_hours[key] = max(duration_seconds / 3600.0, 0.1)  # Min 0.1 hours

    return active_hours


def compute_workload_intensity(
    orders: List[Order], staffing_df: pd.DataFrame, bucket_minutes: int = 15
) -> pd.DataFrame:
    """Compute workload intensity for each order based on staffing levels.

    Workload intensity = 1 / active_waiter_count (higher when fewer waiters)

    Args:
        orders: List of orders
        staffing_df: DataFrame with columns (shift_id, bucket_start_ts, active_waiter_count)
        bucket_minutes: Time bucket size in minutes

    Returns:
        DataFrame with columns: order_id, shift_id, active_waiter_count, workload_intensity

    Examples:
        >>> orders = [Order(order_id=1, shift_id=1, accepted_ts=datetime(2026,1,1,12,0), ...)]
        >>> staffing = pd.DataFrame({
        ...     "shift_id": [1],
        ...     "bucket_start_ts": [datetime(2026,1,1,12,0)],
        ...     "active_waiter_count": [5]
        ... })
        >>> df = compute_workload_intensity(orders, staffing)
        >>> df.loc[0, "workload_intensity"]
        0.2  # 1 / 5
    """
    order_records = []
    for order in orders:
        # Find staffing bucket for order's accepted_ts
        shift_staffing = staffing_df[staffing_df["shift_id"] == order.waiter_shift_id]
        if shift_staffing.empty:
            # Default to median staffing if no data
            active_count = staffing_df["active_waiter_count"].median()
        else:
            # Find nearest bucket
            shift_staffing = shift_staffing.copy()
            shift_staffing["time_diff"] = (
                shift_staffing["bucket_start_ts"] - order.accepted_ts
            ).abs()
            nearest = shift_staffing.loc[shift_staffing["time_diff"].idxmin()]
            active_count = nearest["active_waiter_count"]

        workload_intensity = 1.0 / max(active_count, 1.0)

        order_records.append(
            {
                "order_id": order.order_id,
                "shift_id": order.waiter_shift_id,
                "active_waiter_count": active_count,
                "workload_intensity": workload_intensity,
            }
        )

    return pd.DataFrame(order_records)


def apply_workload_adjustment_multiplicative(
    eff_df: pd.DataFrame, workload_df: pd.DataFrame
) -> pd.DataFrame:
    """Apply multiplicative workload adjustment to efficiency raw values.

    adjusted_eff_raw = eff_raw * (active_waiters / median_shift_staffing)

    Higher staffing → adjusted time increases (less impressive efficiency)
    Lower staffing → adjusted time decreases (more impressive efficiency)

    Args:
        eff_df: DataFrame from compute_efficiency_raw_values()
        workload_df: DataFrame from compute_workload_intensity()

    Returns:
        DataFrame with added column: eff_raw_adjusted
    """
    merged = eff_df.merge(workload_df, on=["order_id", "shift_id"], how="left")

    # Compute median staffing per shift
    shift_median_staffing = merged.groupby("shift_id")["active_waiter_count"].median()
    merged["shift_median_staffing"] = merged["shift_id"].map(shift_median_staffing)

    # Adjustment factor
    merged["adjustment_factor"] = merged["active_waiter_count"] / merged["shift_median_staffing"]
    merged["eff_raw_adjusted"] = merged["eff_raw"] * merged["adjustment_factor"]

    return merged
