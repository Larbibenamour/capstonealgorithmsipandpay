"""Utility functions for creating venue time periods from waiter shift data.

When venue_time_period_id is not provided in the data, these functions can
automatically group overlapping waiter shifts into comparison-fair time periods.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union

import pandas as pd


def create_venue_time_periods_from_shifts(
    waiter_shifts_df: pd.DataFrame,
    min_overlap_hours: float = 2.0,
    venue_id: Union[str, int] = "default_venue",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Automatically create venue_time_periods from individual waiter shifts.
    
    Groups waiter shifts that have significant time overlap into venue_time_periods
    for fair performance comparison.
    
    Args:
        waiter_shifts_df: DataFrame with columns (waiter_shift_id, waiter_id, 
                         clock_in_ts, clock_out_ts)
        min_overlap_hours: Minimum hours of overlap required to group shifts together
        venue_id: Venue identifier
    
    Returns:
        Tuple of (waiter_shifts_with_periods_df, venue_time_periods_df)
        
    Example:
        Friday night:
          Alice: 11:30pm - 4:30am
          Bob:   11:45pm - 5:00am  
          Carol: 12:00am - 4:00am
          
        → All grouped into venue_time_period = "venue_1_20260110_night"
        (they all overlap by >2 hours)
    """
    shifts = waiter_shifts_df.copy()
    
    # Convert to datetime if needed
    shifts["clock_in_ts"] = pd.to_datetime(shifts["clock_in_ts"])
    shifts["clock_out_ts"] = pd.to_datetime(shifts["clock_out_ts"])
    
    # Sort by clock-in time
    shifts = shifts.sort_values("clock_in_ts").reset_index(drop=True)
    
    # Group shifts by date (shifts spanning midnight belong to start date)
    shifts["shift_date"] = shifts["clock_in_ts"].dt.date
    
    venue_time_periods = []
    shift_to_period = {}
    period_counter = 0
    
    for date, date_shifts in shifts.groupby("shift_date"):
        # Find clusters of overlapping shifts
        clusters = _find_overlapping_clusters(
            date_shifts, min_overlap_hours=min_overlap_hours
        )
        
        for cluster_idx, cluster_shift_ids in enumerate(clusters):
            # Create venue_time_period for this cluster
            cluster_shifts = date_shifts[
                date_shifts["waiter_shift_id"].isin(cluster_shift_ids)
            ]
            
            period_start = cluster_shifts["clock_in_ts"].min()
            period_end = cluster_shifts["clock_out_ts"].max()
            
            # Determine period name (day/night based on start hour)
            start_hour = period_start.hour
            if 6 <= start_hour < 14:
                period_type = "morning"
            elif 14 <= start_hour < 22:
                period_type = "evening"
            else:
                period_type = "night"
            
            venue_time_period_id = f"{venue_id}_{date.strftime('%Y%m%d')}_{period_type}_{cluster_idx}"
            
            venue_time_periods.append({
                "venue_time_period_id": venue_time_period_id,
                "venue_id": venue_id,
                "period_start_ts": period_start,
                "period_end_ts": period_end,
                "period_name": f"{date.strftime('%Y-%m-%d')} {period_type.title()} Service",
                "n_waiters": len(cluster_shift_ids),
            })
            
            # Map shifts to this period
            for shift_id in cluster_shift_ids:
                shift_to_period[shift_id] = venue_time_period_id
    
    # Add venue_time_period_id to shifts
    shifts["venue_time_period_id"] = shifts["waiter_shift_id"].map(shift_to_period)
    
    # Create venue_time_periods DataFrame
    periods_df = pd.DataFrame(venue_time_periods)
    
    return shifts, periods_df


def _find_overlapping_clusters(
    shifts_df: pd.DataFrame, min_overlap_hours: float
) -> List[List]:
    """Find clusters of shifts that overlap by at least min_overlap_hours.
    
    Uses a greedy approach: start with earliest shift, add all shifts that
    overlap significantly, then move to next non-clustered shift.
    """
    shifts = shifts_df.sort_values("clock_in_ts").reset_index(drop=True)
    clustered = set()
    clusters = []
    
    for i, shift in shifts.iterrows():
        if shift["waiter_shift_id"] in clustered:
            continue
        
        # Start new cluster with this shift
        cluster = [shift["waiter_shift_id"]]
        cluster_start = shift["clock_in_ts"]
        cluster_end = shift["clock_out_ts"]
        
        # Find all shifts that overlap with this cluster
        for j, other_shift in shifts.iterrows():
            if other_shift["waiter_shift_id"] in clustered:
                continue
            if i == j:
                continue
            
            # Calculate overlap
            overlap_start = max(cluster_start, other_shift["clock_in_ts"])
            overlap_end = min(cluster_end, other_shift["clock_out_ts"])
            
            if overlap_end > overlap_start:
                overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600
                
                if overlap_hours >= min_overlap_hours:
                    cluster.append(other_shift["waiter_shift_id"])
                    clustered.add(other_shift["waiter_shift_id"])
                    
                    # Extend cluster boundaries
                    cluster_end = max(cluster_end, other_shift["clock_out_ts"])
        
        clustered.add(shift["waiter_shift_id"])
        clusters.append(cluster)
    
    return clusters


def assign_orders_to_venue_time_periods(
    orders_df: pd.DataFrame, waiter_shifts_df: pd.DataFrame
) -> pd.DataFrame:
    """Assign venue_time_period_id to orders based on their waiter_shift_id.
    
    Args:
        orders_df: DataFrame with order data (must have waiter_shift_id)
        waiter_shifts_df: DataFrame with waiter_shift_id and venue_time_period_id
    
    Returns:
        orders_df with venue_time_period_id column added
    """
    orders = orders_df.copy()
    
    # Create mapping from waiter_shift_id to venue_time_period_id
    shift_to_period = dict(
        zip(
            waiter_shifts_df["waiter_shift_id"],
            waiter_shifts_df["venue_time_period_id"],
        )
    )
    
    # Assign to orders
    orders["venue_time_period_id"] = orders["waiter_shift_id"].map(shift_to_period)
    
    return orders


def validate_venue_time_period_fairness(
    waiter_shifts_df: pd.DataFrame, venue_time_periods_df: pd.DataFrame
) -> Dict[str, any]:
    """Validate that venue_time_periods have sufficient overlap for fair comparison.
    
    Returns statistics about the created periods.
    """
    stats = {
        "n_periods": len(venue_time_periods_df),
        "periods_with_multiple_waiters": 0,
        "avg_waiters_per_period": 0,
        "min_waiters": float("inf"),
        "max_waiters": 0,
        "single_waiter_periods": [],
    }
    
    for _, period in venue_time_periods_df.iterrows():
        period_id = period["venue_time_period_id"]
        n_waiters = len(
            waiter_shifts_df[waiter_shifts_df["venue_time_period_id"] == period_id]
        )
        
        if n_waiters > 1:
            stats["periods_with_multiple_waiters"] += 1
        else:
            stats["single_waiter_periods"].append(period_id)
        
        stats["min_waiters"] = min(stats["min_waiters"], n_waiters)
        stats["max_waiters"] = max(stats["max_waiters"], n_waiters)
    
    if len(venue_time_periods_df) > 0:
        total_waiters = len(waiter_shifts_df)
        stats["avg_waiters_per_period"] = total_waiters / len(venue_time_periods_df)
    
    return stats


def create_staffing_intervals_for_periods(
    waiter_shifts_df: pd.DataFrame,
    venue_time_periods_df: pd.DataFrame,
    bucket_minutes: int = 15,
) -> pd.DataFrame:
    """Create staffing intervals (active waiter counts) for venue time periods.
    
    Args:
        waiter_shifts_df: DataFrame with waiter shifts and venue_time_period_id
        venue_time_periods_df: DataFrame with venue time periods
        bucket_minutes: Size of time buckets in minutes
    
    Returns:
        DataFrame with columns (venue_time_period_id, bucket_start_ts, active_waiter_count)
    """
    staffing_records = []
    
    for _, period in venue_time_periods_df.iterrows():
        period_id = period["venue_time_period_id"]
        period_start = period["period_start_ts"]
        period_end = period["period_end_ts"]
        
        # Get shifts in this period
        period_shifts = waiter_shifts_df[
            waiter_shifts_df["venue_time_period_id"] == period_id
        ]
        
        # Create time buckets
        current_time = period_start
        while current_time < period_end:
            bucket_end = current_time + timedelta(minutes=bucket_minutes)
            
            # Count active waiters in this bucket
            active_count = 0
            for _, shift in period_shifts.iterrows():
                # Waiter is active if their shift overlaps this bucket
                if shift["clock_in_ts"] < bucket_end and shift["clock_out_ts"] > current_time:
                    active_count += 1
            
            staffing_records.append({
                "venue_time_period_id": period_id,
                "bucket_start_ts": current_time,
                "active_waiter_count": active_count,
            })
            
            current_time = bucket_end
    
    return pd.DataFrame(staffing_records)
