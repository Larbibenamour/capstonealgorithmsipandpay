"""Main orchestration for shift-level waiter performance scoring.

This module ties together all scoring components to compute final scores
for each waiter in each shift, with confidence estimates and component breakdowns.
"""

from typing import Any, Dict, List, Union

import pandas as pd

from src.scoring import confidence as conf_module
from src.scoring import features, normalize
from src.scoring.schema import ComponentScores, Order, ScoringConfig, WaiterMetrics, WaiterShiftScore


def compute_scores(
    orders_df: pd.DataFrame,
    waiter_shifts_df: pd.DataFrame,
    staffing_df: pd.DataFrame,
    config: Union[Dict[str, Any], ScoringConfig],
) -> Dict[Union[str, int], Dict[Union[str, int], Dict[str, Any]]]:
    """Compute shift-level performance scores for all waiters.

    Main entry point for the scoring system. Returns nested dictionary of results.

    Args:
        orders_df: DataFrame with order data (order_id, waiter_shift_id, assigned_waiter_id,
                   accepted_ts, completed_ts, items)
        waiter_shifts_df: DataFrame with shift data (shift_id, start_ts, end_ts)
        staffing_df: DataFrame with staffing data (shift_id, bucket_start_ts, active_waiter_count)
        config: ScoringConfig object or dict with configuration parameters

    Returns:
        Nested dictionary: {shift_id: {waiter_id: {score, confidence, components, metrics}}}

    Examples:
        >>> orders_df = pd.DataFrame(...)  # Order data
        >>> waiter_shifts_df = pd.DataFrame(...)  # Shift data
        >>> staffing_df = pd.DataFrame(...)  # Staffing data
        >>> config = {"weights": {"efficiency": 0.5, "throughput": 0.3, "consistency": 0.2}}
        >>> results = compute_scores(orders_df, waiter_shifts_df, staffing_df, config)
        >>> results["shift_123"]["waiter_456"]["score"]
        78.5
    """
    # Convert config dict to ScoringConfig object if needed
    if isinstance(config, dict):
        config = ScoringConfig(**config)

    # Convert DataFrame rows to Order objects
    orders = _parse_orders_from_dataframe(orders_df)

    # Validate input
    _validate_inputs(orders, waiter_shifts_df, staffing_df, config)

    # Compute features for all orders
    item_weights = config.item_weights
    epsilon = config.epsilon

    # 1. Compute efficiency raw values
    eff_df = features.compute_efficiency_raw_values(orders, item_weights, epsilon)

    # 2. Apply workload adjustment if configured
    if config.workload_adjustment == "multiplicative":
        workload_df = features.compute_workload_intensity(
            orders, staffing_df, config.bucket_minutes
        )
        eff_df = features.apply_workload_adjustment_multiplicative(eff_df, workload_df)
        eff_col = "eff_raw_adjusted"
    else:
        # Stratified mode: would compute percentiles within staffing buckets
        # For MVP v1, use unadjusted
        eff_col = "eff_raw"

    # 3. Aggregate efficiency stats per waiter per shift
    eff_df_for_stats = eff_df.copy()
    eff_df_for_stats["eff_raw"] = eff_df_for_stats[eff_col]
    eff_stats = features.compute_waiter_efficiency_stats(eff_df_for_stats)

    # 4. Compute consistency scores
    eff_stats = features.compute_consistency_score(eff_stats, method="iqr", epsilon=epsilon)

    # 5. Compute throughput
    waiter_active_hours = _compute_waiter_active_hours(orders, waiter_shifts_df)
    throughput_df = features.compute_throughput(orders, item_weights, waiter_active_hours)

    # 6. Normalize within shifts
    eff_stats = normalize.normalize_efficiency_within_shift(eff_stats, lower_is_better=True)
    throughput_df = normalize.normalize_throughput_within_shift(throughput_df)
    eff_stats = normalize.normalize_consistency_within_shift(eff_stats)

    # 7. Merge all components
    scores_df = eff_stats.merge(throughput_df, on=["shift_id", "waiter_id"], how="outer")

    # 8. Compute composite scores
    scores_df["composite_score"] = scores_df.apply(
        lambda row: normalize.compute_composite_score(
            row["efficiency_score"], row["throughput_score"], row["consistency_score"], config.weights
        ),
        axis=1,
    )

    # 9. Compute confidence scores
    scores_df["confidence"] = scores_df.apply(
        lambda row: conf_module.compute_overall_confidence(
            n_orders=int(row["n_orders"]),
            total_complexity=float(row["total_complexity"]),
            normalized_dispersion=float(row.get("normalized_dispersion", 0.0)),
            config=config.dict() if hasattr(config, "dict") else config,
        ),
        axis=1,
    )

    # 10. Apply shrinkage toward shift median for low-confidence scores
    scores_df = _apply_shift_shrinkage(scores_df, config.shrinkage_strength)

    # 11. Format output
    results = _format_results(scores_df)

    return results


def _parse_orders_from_dataframe(orders_df: pd.DataFrame) -> List[Order]:
    """Convert DataFrame to list of Order objects.

    Supports both JSON items column and separate order_items table.
    """
    orders = []
    for _, row in orders_df.iterrows():
        # Handle items: could be JSON string, list of dicts, or already parsed
        items = row.get("items", [])
        if isinstance(items, str):
            import json

            items = json.loads(items)

        # Convert items to OrderItem objects
        from src.scoring.schema import OrderItem

        order_items = []
        for item in items:
            if isinstance(item, dict):
                order_items.append(OrderItem(**item))
            else:
                order_items.append(item)

        order = Order(
            order_id=row["order_id"],
            waiter_shift_id=row["waiter_shift_id"],
            assigned_waiter_id=row["assigned_waiter_id"],
            accepted_ts=pd.to_datetime(row["accepted_ts"]),
            completed_ts=pd.to_datetime(row["completed_ts"]),
            items=order_items,
        )
        orders.append(order)

    return orders


def _validate_inputs(
    orders: List[Order], shifts_df: pd.DataFrame, staffing_df: pd.DataFrame, config: ScoringConfig
) -> None:
    """Validate input data and configuration."""
    if len(orders) == 0:
        raise ValueError("No orders provided")

    if shifts_df.empty:
        raise ValueError("No shifts data provided")

    required_shift_cols = {"shift_id", "start_ts", "end_ts"}
    if not required_shift_cols.issubset(shifts_df.columns):
        raise ValueError(f"shifts_df must contain columns: {required_shift_cols}")

    if not staffing_df.empty:
        required_staffing_cols = {"shift_id", "bucket_start_ts", "active_waiter_count"}
        if not required_staffing_cols.issubset(staffing_df.columns):
            raise ValueError(f"staffing_df must contain columns: {required_staffing_cols}")


def _compute_waiter_active_hours(
    orders: List[Order], shifts_df: pd.DataFrame
) -> Dict[tuple, float]:
    """Compute active hours for each waiter in each shift.

    Uses order timestamps as a fallback estimate.
    Keys are (waiter_shift_id, waiter_id).
    """
    # Build shift_times keyed by shift_id for reference (not directly used here)
    shift_times = {
        row["shift_id"]: (row["start_ts"], row["end_ts"]) for _, row in shifts_df.iterrows()
    }

    return features.extract_waiter_active_hours_from_orders(orders, shift_times)


def _apply_shift_shrinkage(scores_df: pd.DataFrame, shrinkage_strength: float) -> pd.DataFrame:
    """Apply shrinkage toward shift median for low-confidence scores."""
    scores_df = scores_df.copy()

    def apply_shrinkage_to_group(group: pd.DataFrame) -> pd.DataFrame:
        """Apply shrinkage within a shift group."""
        shift_median = group["composite_score"].median()

        group["composite_score"] = group.apply(
            lambda row: conf_module.apply_shrinkage(
                row["composite_score"], shift_median, row["confidence"], shrinkage_strength
            ),
            axis=1,
        )
        return group

    scores_df = scores_df.groupby("shift_id", group_keys=False).apply(apply_shrinkage_to_group)

    # groupby can drop the column when used as index — restore it
    if "shift_id" not in scores_df.columns:
        scores_df = scores_df.reset_index(names="shift_id")

    return scores_df


def _format_results(scores_df: pd.DataFrame) -> Dict[Union[str, int], Dict[Union[str, int], Dict[str, Any]]]:
    """Format scoring results as nested dictionary for JSON serialization."""
    results: Dict[Union[str, int], Dict[Union[str, int], Dict[str, Any]]] = {}

    for _, row in scores_df.iterrows():
        shift_id = row["shift_id"]
        waiter_id = row["waiter_id"]

        if shift_id not in results:
            results[shift_id] = {}

        results[shift_id][waiter_id] = {
            "score": float(row["composite_score"]),
            "confidence": float(row["confidence"]),
            "components": {
                "efficiency": float(row["efficiency_score"]),
                "throughput": float(row["throughput_score"]),
                "consistency": float(row["consistency_score"]),
            },
            "metrics": {
                "n_orders": int(row["n_orders"]),
                "total_complexity": float(row["total_complexity"]),
                "active_hours": float(row.get("active_hours", 0.0)),
                "median_eff_raw": float(row.get("median_eff_raw", 0.0)),
                "eff_dispersion": float(row.get("eff_iqr", 0.0)),
            },
        }

    return results


def compute_shift_summary(results: Dict[Union[str, int], Dict]) -> pd.DataFrame:
    """Generate summary statistics for each shift.

    Args:
        results: Output from compute_scores()

    Returns:
        DataFrame with shift-level summary stats
    """
    summary_records = []

    for shift_id, waiters in results.items():
        scores = [w["score"] for w in waiters.values()]
        confidences = [w["confidence"] for w in waiters.values()]

        summary_records.append(
            {
                "shift_id": shift_id,
                "n_waiters": len(waiters),
                "mean_score": sum(scores) / len(scores) if scores else 0,
                "median_score": sorted(scores)[len(scores) // 2] if scores else 0,
                "min_score": min(scores) if scores else 0,
                "max_score": max(scores) if scores else 0,
                "mean_confidence": sum(confidences) / len(confidences) if confidences else 0,
            }
        )

    return pd.DataFrame(summary_records)


def export_results_to_json(results: Dict, output_path: str) -> None:
    """Export scoring results to JSON file.

    Args:
        results: Output from compute_scores()
        output_path: Path to output JSON file
    """
    import json

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
