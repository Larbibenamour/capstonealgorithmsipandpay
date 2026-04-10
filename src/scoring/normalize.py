"""Within-shift normalization and scoring.

Implements robust scaling and percentile-based normalization to convert
raw metrics into 0-100 scores while maintaining within-shift comparability.
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


def percentile_rank(values: np.ndarray, value: float) -> float:
    """Compute percentile rank of a value within a distribution.

    Args:
        values: Array of values defining the distribution
        value: Value to rank

    Returns:
        Percentile rank in range [0, 100]

    Examples:
        >>> percentile_rank(np.array([1, 2, 3, 4, 5]), 3)
        50.0
        >>> percentile_rank(np.array([1, 2, 3, 4, 5]), 1)
        0.0
    """
    if len(values) == 0:
        return 50.0
    return stats.percentileofscore(values, value, kind="rank")


def robust_scale(
    values: pd.Series, center: str = "median", scale: str = "iqr", epsilon: float = 1e-6
) -> pd.Series:
    """Apply robust scaling using median and IQR.

    scaled_value = (value - center) / scale

    Args:
        values: Series of values to scale
        center: Centering method ('median' or 'mean')
        scale: Scaling method ('iqr' or 'std')
        epsilon: Small constant to prevent division by zero

    Returns:
        Scaled series

    Examples:
        >>> data = pd.Series([10, 20, 30, 40, 50])
        >>> scaled = robust_scale(data, center="median", scale="iqr")
        >>> abs(scaled.median()) < 0.01  # Centered at 0
        True
    """
    if center == "median":
        center_value = values.median()
    elif center == "mean":
        center_value = values.mean()
    else:
        raise ValueError(f"Unknown center method: {center}")

    if scale == "iqr":
        scale_value = values.quantile(0.75) - values.quantile(0.25)
    elif scale == "std":
        scale_value = values.std()
    else:
        raise ValueError(f"Unknown scale method: {scale}")

    scale_value = max(scale_value, epsilon)
    return (values - center_value) / scale_value


def normalize_efficiency_within_shift(
    eff_stats: pd.DataFrame, lower_is_better: bool = True
) -> pd.DataFrame:
    """Normalize efficiency scores within each shift using percentile ranks.

    Lower eff_raw → higher efficiency score (faster completion per complexity unit)

    Args:
        eff_stats: DataFrame with columns (shift_id, waiter_id, median_eff_raw)
        lower_is_better: If True, invert ranking (lower raw value = higher score)

    Returns:
        DataFrame with added column: efficiency_score (0-100)

    Examples:
        >>> eff_stats = pd.DataFrame({
        ...     "shift_id": [1, 1, 1],
        ...     "waiter_id": ["W1", "W2", "W3"],
        ...     "median_eff_raw": [80, 100, 120]  # W1 fastest
        ... })
        >>> result = normalize_efficiency_within_shift(eff_stats)
        >>> result.loc[0, "efficiency_score"] > result.loc[2, "efficiency_score"]
        True  # W1 has lower eff_raw, higher score
    """
    eff_stats = eff_stats.copy()
    eff_stats["efficiency_score"] = 50.0  # default

    for shift_id, group in eff_stats.groupby("shift_id"):
        # Single-waiter shifts receive neutral score — no peer comparison possible
        if len(group) == 1:
            eff_stats.loc[group.index, "efficiency_score"] = 50.0
            continue
        values = group["median_eff_raw"].values
        scores = []
        for v in values:
            rank = percentile_rank(values, v)
            scores.append(100.0 - rank if lower_is_better else rank)
        eff_stats.loc[group.index, "efficiency_score"] = scores

    return eff_stats


def normalize_throughput_within_shift(throughput_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize throughput scores within each shift using percentile ranks.

    Higher throughput → higher score

    Args:
        throughput_df: DataFrame with columns (shift_id, waiter_id, throughput)

    Returns:
        DataFrame with added column: throughput_score (0-100)
    """
    throughput_df = throughput_df.copy()
    throughput_df["throughput_score"] = 50.0  # default

    for shift_id, group in throughput_df.groupby("shift_id"):
        # Single-waiter shifts receive neutral score — no peer comparison possible
        if len(group) == 1:
            throughput_df.loc[group.index, "throughput_score"] = 50.0
            continue
        values = group["throughput"].values
        scores = [percentile_rank(values, v) for v in values]
        throughput_df.loc[group.index, "throughput_score"] = scores

    return throughput_df


def normalize_consistency_within_shift(consistency_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize consistency scores within each shift using percentile ranks.

    Higher consistency_raw → higher score

    Args:
        consistency_df: DataFrame with columns (shift_id, waiter_id, consistency_raw)

    Returns:
        DataFrame with added column: consistency_score (0-100)
    """
    consistency_df = consistency_df.copy()
    consistency_df["consistency_score"] = 50.0  # default

    for shift_id, group in consistency_df.groupby("shift_id"):
        # Single-waiter shifts receive neutral score — no peer comparison possible
        if len(group) == 1:
            consistency_df.loc[group.index, "consistency_score"] = 50.0
            continue
        values = group["consistency_raw"].values
        scores = [percentile_rank(values, v) for v in values]
        consistency_df.loc[group.index, "consistency_score"] = scores

    return consistency_df


def compute_composite_score(
    efficiency_score: float, throughput_score: float, consistency_score: float, weights: dict
) -> float:
    """Compute weighted composite score from component scores.

    score = w_eff * eff + w_thr * thr + w_cons * cons

    Args:
        efficiency_score: Efficiency score (0-100)
        throughput_score: Throughput score (0-100)
        consistency_score: Consistency score (0-100)
        weights: Dictionary with keys 'efficiency', 'throughput', 'consistency'

    Returns:
        Composite score (0-100)

    Examples:
        >>> compute_composite_score(80, 70, 60, {"efficiency": 0.5, "throughput": 0.3, "consistency": 0.2})
        73.0  # 0.5*80 + 0.3*70 + 0.2*60
    """
    score = (
        weights["efficiency"] * efficiency_score
        + weights["throughput"] * throughput_score
        + weights["consistency"] * consistency_score
    )
    return np.clip(score, 0, 100)


def winsorize_values(
    values: pd.Series, lower_quantile: float = 0.05, upper_quantile: float = 0.95
) -> pd.Series:
    """Winsorize extreme values by capping at specified quantiles.

    Args:
        values: Series of values to winsorize
        lower_quantile: Lower quantile threshold (e.g., 0.05 for 5th percentile)
        upper_quantile: Upper quantile threshold (e.g., 0.95 for 95th percentile)

    Returns:
        Winsorized series

    Examples:
        >>> data = pd.Series([1, 2, 3, 4, 5, 100])
        >>> winsorized = winsorize_values(data, 0.1, 0.9)
        >>> winsorized.max() < 100
        True  # Extreme value capped
    """
    lower_bound = values.quantile(lower_quantile)
    upper_bound = values.quantile(upper_quantile)
    return values.clip(lower=lower_bound, upper=upper_bound)


def handle_single_waiter_shift(
    shift_id: int, waiter_id: int, n_orders: int, total_complexity: float
) -> dict:
    """Handle edge case where shift has only one waiter.

    Single-waiter shifts receive neutral scores (50) with adjusted confidence.

    Args:
        shift_id: Shift identifier
        waiter_id: Waiter identifier
        n_orders: Number of orders handled
        total_complexity: Total complexity units

    Returns:
        Dictionary with neutral scores
    """
    return {
        "shift_id": shift_id,
        "waiter_id": waiter_id,
        "efficiency_score": 50.0,
        "throughput_score": 50.0,
        "consistency_score": 50.0,
        "composite_score": 50.0,
        "n_orders": n_orders,
        "total_complexity": total_complexity,
        "is_single_waiter_shift": True,
    }


def apply_floor_and_ceiling(
    score: float, floor: Optional[float] = None, ceiling: Optional[float] = None
) -> float:
    """Apply optional floor and ceiling constraints to a score.

    Args:
        score: Raw score
        floor: Minimum allowed score (optional)
        ceiling: Maximum allowed score (optional)

    Returns:
        Constrained score

    Examples:
        >>> apply_floor_and_ceiling(45, floor=50)
        50.0
        >>> apply_floor_and_ceiling(105, ceiling=100)
        100.0
    """
    if floor is not None:
        score = max(score, floor)
    if ceiling is not None:
        score = min(score, ceiling)
    return score
