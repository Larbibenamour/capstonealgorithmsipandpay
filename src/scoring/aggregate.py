"""Temporal aggregation of shift-level scores to weekly/monthly periods.

Implements weighted averaging, winsorization, and confidence filtering
to produce stable aggregate performance metrics.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import pandas as pd

from src.scoring.normalize import winsorize_values


def aggregate_scores_by_period(
    results: Dict[Union[str, int], Dict[Union[str, int], Dict]],
    shifts_df: pd.DataFrame,
    period: str = "week",
    min_confidence: float = 0.3,
    winsorize_quantile: float = 0.05,
) -> pd.DataFrame:
    """Aggregate shift-level scores to weekly or monthly periods.

    Scores are weighted by total complexity handled. Extreme shift scores
    are winsorized before aggregation to prevent outliers from dominating.

    Args:
        results: Output from compute_scores() - nested dict of shift/waiter scores
        shifts_df: DataFrame with shift metadata (shift_id, start_ts, end_ts)
        period: Aggregation period ('week' or 'month')
        min_confidence: Minimum confidence threshold for inclusion
        winsorize_quantile: Quantile for winsorization (e.g., 0.05 = 5th/95th percentile)

    Returns:
        DataFrame with columns: waiter_id, period_start, period_end, aggregated_score,
                                 mean_confidence, n_shifts, total_complexity

    Examples:
        >>> results = {1: {"W1": {"score": 80, "confidence": 0.8, "metrics": {"total_complexity": 50}}}}
        >>> shifts_df = pd.DataFrame({"shift_id": [1], "start_ts": [datetime(2026,1,1)]})
        >>> agg_df = aggregate_scores_by_period(results, shifts_df, period="week")
        >>> agg_df.loc[0, "aggregated_score"]
        80.0
    """
    # Flatten results to DataFrame
    records = []
    for shift_id, waiters in results.items():
        for waiter_id, data in waiters.items():
            records.append(
                {
                    "shift_id": shift_id,
                    "waiter_id": waiter_id,
                    "score": data["score"],
                    "confidence": data["confidence"],
                    "total_complexity": data["metrics"]["total_complexity"],
                }
            )

    scores_df = pd.DataFrame(records)

    # Merge with shift timestamps — cast to str to avoid int/str type mismatch
    scores_df["shift_id"] = scores_df["shift_id"].astype(str)
    shifts_lookup = shifts_df[["shift_id", "start_ts"]].copy()
    shifts_lookup["shift_id"] = shifts_lookup["shift_id"].astype(str)

    # Try direct merge first
    merged = scores_df.merge(shifts_lookup, on="shift_id", how="left")

    # If no timestamps matched (waiter_shift_id keys like "waiter_3_shift_shift_1"),
    # extract the underlying shift_id suffix and retry
    if merged["start_ts"].isna().all() and not scores_df.empty:
        def extract_shift_id(wshift_id: str) -> str:
            # Pattern: {waiter_id}_shift_{shift_id} → extract suffix after last "_shift_"
            idx = wshift_id.rfind("_shift_")
            return wshift_id[idx + 7:] if idx != -1 else wshift_id

        scores_df["shift_id_lookup"] = scores_df["shift_id"].apply(extract_shift_id)
        shifts_lookup2 = shifts_lookup.rename(columns={"shift_id": "shift_id_lookup"})
        merged = scores_df.merge(shifts_lookup2, on="shift_id_lookup", how="left")
        merged = merged.drop(columns=["shift_id_lookup"])

    scores_df = merged

    # Drop rows where shift timestamp couldn't be matched
    scores_df = scores_df.dropna(subset=["start_ts"])

    # Filter low-confidence scores
    scores_df = scores_df[scores_df["confidence"] >= min_confidence]

    if scores_df.empty:
        return pd.DataFrame(
            columns=[
                "waiter_id",
                "period_start",
                "period_end",
                "aggregated_score",
                "mean_confidence",
                "n_shifts",
                "total_complexity",
            ]
        )

    # Add period identifiers
    scores_df["period_start"] = scores_df["start_ts"].apply(
        lambda ts: _get_period_start(ts, period)
    )

    # Winsorize scores within each waiter to cap extreme shifts
    winsorized_parts = []
    for waiter_id, group in scores_df.groupby("waiter_id"):
        group = group.copy()
        if len(group) > 2:
            group["score"] = winsorize_values(
                group["score"], winsorize_quantile, 1 - winsorize_quantile
            )
        winsorized_parts.append(group)
    scores_df = pd.concat(winsorized_parts) if winsorized_parts else scores_df

    # Aggregate by waiter and period using explicit loop (pandas 2.x safe)
    agg_records = []
    for (waiter_id, period_start), group in scores_df.groupby(["waiter_id", "period_start"]):
        total_c = group["total_complexity"].sum()
        agg_records.append({
            "waiter_id": waiter_id,
            "period_start": period_start,
            "aggregated_score": (group["score"] * group["total_complexity"]).sum() / total_c
            if total_c > 0 else group["score"].mean(),
            "mean_confidence": group["confidence"].mean(),
            "n_shifts": len(group),
            "total_complexity": total_c,
        })
    aggregated = pd.DataFrame(agg_records)
    if not aggregated.empty:
        aggregated["aggregated_score"] = aggregated["aggregated_score"].clip(0, 100)

    # Add period end timestamps
    if period == "week":
        aggregated["period_end"] = aggregated["period_start"] + timedelta(days=7)
    elif period == "month":
        aggregated["period_end"] = aggregated["period_start"] + pd.DateOffset(months=1)
    else:
        raise ValueError(f"Unknown period: {period}")

    return aggregated


def _get_period_start(timestamp: datetime, period: str) -> datetime:
    """Get the start of the period containing the given timestamp.

    Args:
        timestamp: Timestamp to find period for
        period: 'week' or 'month'

    Returns:
        Start of the period
    """
    if period == "week":
        # Start of week (Monday)
        return timestamp - timedelta(days=timestamp.weekday())
    elif period == "month":
        # Start of month
        return timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unknown period: {period}")


def compute_rolling_average(
    aggregated_df: pd.DataFrame, window_size: int = 4, min_periods: int = 2
) -> pd.DataFrame:
    """Compute rolling average of aggregated scores.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        window_size: Number of periods to include in rolling window
        min_periods: Minimum periods required for valid rolling average

    Returns:
        DataFrame with added column: rolling_avg_score

    Examples:
        >>> agg_df = pd.DataFrame({
        ...     "waiter_id": ["W1", "W1", "W1"],
        ...     "period_start": pd.date_range("2026-01-01", periods=3, freq="W"),
        ...     "aggregated_score": [70, 75, 80]
        ... })
        >>> result = compute_rolling_average(agg_df, window_size=2)
        >>> result.loc[2, "rolling_avg_score"]
        77.5  # (75 + 80) / 2
    """
    aggregated_df = aggregated_df.copy()

    # Sort by waiter and period
    aggregated_df = aggregated_df.sort_values(["waiter_id", "period_start"])

    # Compute rolling average per waiter
    aggregated_df["rolling_avg_score"] = aggregated_df.groupby("waiter_id")[
        "aggregated_score"
    ].transform(lambda x: x.rolling(window=window_size, min_periods=min_periods).mean())

    return aggregated_df


def compute_trend(aggregated_df: pd.DataFrame) -> pd.DataFrame:
    """Compute performance trend (slope) for each waiter over time.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()

    Returns:
        DataFrame with columns: waiter_id, trend_slope, trend_pvalue, n_periods

    Examples:
        >>> agg_df = pd.DataFrame({
        ...     "waiter_id": ["W1", "W1", "W1"],
        ...     "period_start": pd.date_range("2026-01-01", periods=3, freq="W"),
        ...     "aggregated_score": [70, 75, 80]
        ... })
        >>> trends = compute_trend(agg_df)
        >>> trends.loc[0, "trend_slope"] > 0  # Positive trend
        True
    """
    from scipy import stats

    trend_records = []

    for waiter_id, group in aggregated_df.groupby("waiter_id"):
        if len(group) < 2:
            trend_records.append(
                {"waiter_id": waiter_id, "trend_slope": 0.0, "trend_pvalue": 1.0, "n_periods": len(group)}
            )
            continue

        # Sort by time
        group = group.sort_values("period_start")

        # Linear regression: score ~ period_index
        x = list(range(len(group)))
        y = group["aggregated_score"].values

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        trend_records.append(
            {
                "waiter_id": waiter_id,
                "trend_slope": slope,
                "trend_pvalue": p_value,
                "n_periods": len(group),
                "r_squared": r_value**2,
            }
        )

    return pd.DataFrame(trend_records)


def identify_consistent_performers(
    aggregated_df: pd.DataFrame,
    min_periods: int = 4,
    max_variance: float = 100.0,
    min_mean_score: float = 70.0,
) -> pd.DataFrame:
    """Identify waiters with consistent high performance over time.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        min_periods: Minimum number of periods required
        max_variance: Maximum allowed variance in scores
        min_mean_score: Minimum mean score threshold

    Returns:
        DataFrame of consistent high performers with stats

    Examples:
        >>> agg_df = pd.DataFrame({
        ...     "waiter_id": ["W1", "W1", "W1", "W1"],
        ...     "aggregated_score": [80, 82, 81, 79]
        ... })
        >>> consistent = identify_consistent_performers(agg_df, min_periods=4)
        >>> "W1" in consistent["waiter_id"].values
        True
    """
    stats_records = []

    for waiter_id, group in aggregated_df.groupby("waiter_id"):
        if len(group) < min_periods:
            continue

        mean_score = group["aggregated_score"].mean()
        variance = group["aggregated_score"].var()

        if mean_score >= min_mean_score and variance <= max_variance:
            stats_records.append(
                {
                    "waiter_id": waiter_id,
                    "mean_score": mean_score,
                    "variance": variance,
                    "n_periods": len(group),
                }
            )

    return pd.DataFrame(stats_records).sort_values("mean_score", ascending=False)


def compute_period_over_period_change(aggregated_df: pd.DataFrame) -> pd.DataFrame:
    """Compute period-over-period change in scores.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()

    Returns:
        DataFrame with added columns: prev_score, score_change, pct_change

    Examples:
        >>> agg_df = pd.DataFrame({
        ...     "waiter_id": ["W1", "W1"],
        ...     "period_start": pd.date_range("2026-01-01", periods=2, freq="W"),
        ...     "aggregated_score": [70, 80]
        ... })
        >>> result = compute_period_over_period_change(agg_df)
        >>> result.loc[1, "score_change"]
        10.0
    """
    aggregated_df = aggregated_df.copy()
    aggregated_df = aggregated_df.sort_values(["waiter_id", "period_start"])

    aggregated_df["prev_score"] = aggregated_df.groupby("waiter_id")["aggregated_score"].shift(1)
    aggregated_df["score_change"] = aggregated_df["aggregated_score"] - aggregated_df["prev_score"]
    aggregated_df["pct_change"] = (
        aggregated_df["score_change"] / aggregated_df["prev_score"] * 100
    )

    return aggregated_df


def generate_leaderboard(
    aggregated_df: pd.DataFrame, period_start: Optional[datetime] = None, top_n: int = 10
) -> pd.DataFrame:
    """Generate leaderboard for a specific period or overall.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        period_start: Specific period to filter (None = latest period)
        top_n: Number of top performers to return

    Returns:
        DataFrame with top performers and their stats

    Examples:
        >>> agg_df = pd.DataFrame({
        ...     "waiter_id": ["W1", "W2", "W3"],
        ...     "aggregated_score": [90, 85, 80],
        ...     "mean_confidence": [0.9, 0.85, 0.8]
        ... })
        >>> leaderboard = generate_leaderboard(agg_df, top_n=2)
        >>> len(leaderboard)
        2
        >>> leaderboard.loc[0, "waiter_id"]
        'W1'
    """
    df = aggregated_df.copy()

    if period_start is not None:
        df = df[df["period_start"] == period_start]
    else:
        # Use most recent period
        latest_period = df["period_start"].max()
        df = df[df["period_start"] == latest_period]

    leaderboard = (
        df.sort_values("aggregated_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    leaderboard["rank"] = range(1, len(leaderboard) + 1)

    return leaderboard[
        ["rank", "waiter_id", "aggregated_score", "mean_confidence", "n_shifts", "total_complexity"]
    ]


def export_aggregated_results(aggregated_df: pd.DataFrame, output_path: str) -> None:
    """Export aggregated results to CSV.

    Args:
        aggregated_df: DataFrame from aggregate_scores_by_period()
        output_path: Path to output CSV file
    """
    aggregated_df.to_csv(output_path, index=False)
