"""Mock data generator for testing and demonstration.

Generates realistic synthetic data for orders, shifts, and staffing
with configurable parameters and realistic variability.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def generate_mock_data(
    n_shifts: int = 10,
    n_waiters: int = 8,
    orders_per_shift: int = 50,
    start_date: datetime = datetime(2026, 1, 1),
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate mock data for orders, shifts, and staffing.

    Creates realistic synthetic data with:
    - Variable waiter performance levels (fast, average, slow)
    - Realistic order complexity distributions
    - Time-based staffing patterns
    - Consistent waiter behavior across shifts

    Args:
        n_shifts: Number of shifts to generate
        n_waiters: Number of waiters per shift
        orders_per_shift: Average orders per shift
        start_date: Starting date for shift generation
        seed: Random seed for reproducibility

    Returns:
        Tuple of (orders_df, shifts_df, staffing_df)

    Examples:
        >>> orders_df, shifts_df, staffing_df = generate_mock_data(n_shifts=5)
        >>> len(shifts_df)
        5
        >>> "order_id" in orders_df.columns
        True
    """
    np.random.seed(seed)
    random.seed(seed)

    # Generate shifts
    shifts_df = _generate_shifts(n_shifts, start_date)

    # Generate staffing patterns
    staffing_df = _generate_staffing(shifts_df, n_waiters)

    # Generate waiter performance profiles
    waiter_profiles = _generate_waiter_profiles(n_waiters)

    # Generate orders
    orders_df = _generate_orders(
        shifts_df, waiter_profiles, orders_per_shift, staffing_df
    )

    return orders_df, shifts_df, staffing_df


def _generate_shifts(n_shifts: int, start_date: datetime) -> pd.DataFrame:
    """Generate shift data.

    Shifts are evening shifts (6 PM - 2 AM) on various days.
    """
    shifts = []

    for i in range(n_shifts):
        # Shifts on different days
        day_offset = i % 7  # Spread across a week
        shift_date = start_date + timedelta(days=day_offset + (i // 7) * 7)

        # Evening shift: 6 PM to 2 AM next day
        shift_start = shift_date.replace(hour=18, minute=0, second=0)
        shift_end = shift_start + timedelta(hours=8)

        shifts.append(
            {
                "shift_id": f"shift_{i+1}",
                "start_ts": shift_start,
                "end_ts": shift_end,
                "venue_id": "venue_001",
            }
        )

    return pd.DataFrame(shifts)


def _generate_staffing(shifts_df: pd.DataFrame, n_waiters: int) -> pd.DataFrame:
    """Generate staffing patterns with realistic variation.

    Staffing varies throughout the shift (more during peak hours).
    """
    staffing_records = []
    bucket_minutes = 15

    for _, shift in shifts_df.iterrows():
        shift_start = shift["start_ts"]
        shift_end = shift["end_ts"]
        shift_id = shift["shift_id"]

        # Generate time buckets
        current_time = shift_start
        hour_into_shift = 0

        while current_time < shift_end:
            # Staffing pattern: peak in middle of shift
            hours_elapsed = hour_into_shift / 4.0  # Convert 15-min buckets to hours

            if hours_elapsed < 1.0:
                # Ramp up
                active_waiters = int(n_waiters * 0.6 + np.random.randint(0, 2))
            elif hours_elapsed < 5.0:
                # Peak hours
                active_waiters = int(n_waiters * 0.9 + np.random.randint(-1, 2))
            else:
                # Wind down
                active_waiters = int(n_waiters * 0.7 + np.random.randint(-1, 1))

            active_waiters = max(1, min(active_waiters, n_waiters))

            staffing_records.append(
                {
                    "shift_id": shift_id,
                    "bucket_start_ts": current_time,
                    "active_waiter_count": active_waiters,
                }
            )

            current_time += timedelta(minutes=bucket_minutes)
            hour_into_shift += 1

    return pd.DataFrame(staffing_records)


def _generate_waiter_profiles(n_waiters: int) -> Dict[str, Dict]:
    """Generate waiter performance profiles.

    Creates variation in:
    - Base efficiency (faster/slower completion)
    - Consistency (low/high variance)
    - Throughput capacity
    """
    profiles = {}

    # Create a mix of performance levels
    performance_levels = ["fast", "average", "slow"]

    for i in range(n_waiters):
        waiter_id = f"waiter_{i+1}"

        # Randomly assign performance level
        level = performance_levels[i % len(performance_levels)]

        if level == "fast":
            base_eff_multiplier = 0.7  # 30% faster
            consistency_multiplier = 0.8  # More consistent
            throughput_multiplier = 1.3
        elif level == "average":
            base_eff_multiplier = 1.0
            consistency_multiplier = 1.0
            throughput_multiplier = 1.0
        else:  # slow
            base_eff_multiplier = 1.4  # 40% slower
            consistency_multiplier = 1.3  # Less consistent
            throughput_multiplier = 0.8

        profiles[waiter_id] = {
            "level": level,
            "base_eff_multiplier": base_eff_multiplier,
            "consistency_multiplier": consistency_multiplier,
            "throughput_multiplier": throughput_multiplier,
        }

    return profiles


def _generate_orders(
    shifts_df: pd.DataFrame,
    waiter_profiles: Dict[str, Dict],
    orders_per_shift: int,
    staffing_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate order data with realistic timing and assignments."""
    orders = []
    order_counter = 1

    # Item catalog (nightlife drinks and bottles)
    items_catalog = [
        {"item_id": "beer", "base_complexity": 1.0, "category": "drink"},
        {"item_id": "cocktail", "base_complexity": 2.0, "category": "drink"},
        {"item_id": "wine", "base_complexity": 1.0, "category": "drink"},
        {"item_id": "champagne_bottle", "base_complexity": 3.0, "category": "bottle"},
        {"item_id": "shot", "base_complexity": 1.5, "category": "drink"},
        {"item_id": "gin_tonic", "base_complexity": 2.0, "category": "drink"},
        {"item_id": "vodka_bottle", "base_complexity": 4.0, "category": "bottle"},
        {"item_id": "mojito", "base_complexity": 2.5, "category": "drink"},
    ]

    for _, shift in shifts_df.iterrows():
        shift_id = shift["shift_id"]
        shift_start = shift["start_ts"]
        shift_end = shift["end_ts"]

        # Get available waiters for this shift
        waiter_ids = list(waiter_profiles.keys())

        # Generate orders throughout shift
        n_orders = int(orders_per_shift * np.random.uniform(0.8, 1.2))

        for _ in range(n_orders):
            # Random order time during shift
            order_offset = np.random.uniform(0, (shift_end - shift_start).total_seconds())
            accepted_ts = shift_start + timedelta(seconds=order_offset)

            # Assign to random waiter
            waiter_id = random.choice(waiter_ids)
            waiter_profile = waiter_profiles[waiter_id]

            # Generate items for order
            n_items = np.random.randint(1, 5)
            order_items = []
            total_complexity = 0

            for _ in range(n_items):
                item = random.choice(items_catalog)
                quantity = np.random.randint(1, 4)

                order_items.append(
                    {
                        "item_id": item["item_id"],
                        "quantity": quantity,
                        "category": item["category"],
                    }
                )
                total_complexity += quantity * item["base_complexity"]

            # Compute cycle time based on waiter profile and order complexity
            base_cycle_time = 600  # 10 minutes base
            complexity_effect = total_complexity * 60  # 60 seconds per complexity unit

            # Waiter efficiency effect
            waiter_multiplier = waiter_profile["base_eff_multiplier"]

            # Add random variance based on consistency
            variance = (
                waiter_profile["consistency_multiplier"]
                * np.random.normal(0, 0.2)
            )

            cycle_time = (base_cycle_time + complexity_effect) * waiter_multiplier * (
                1 + variance
            )

            # Ensure positive cycle time
            cycle_time = max(cycle_time, 60)  # Minimum 1 minute

            # Add workload effect from staffing
            shift_staffing = staffing_df[staffing_df["shift_id"] == shift_id]
            nearest_bucket = shift_staffing.iloc[
                (shift_staffing["bucket_start_ts"] - accepted_ts).abs().argsort()[:1]
            ]
            if not nearest_bucket.empty:
                active_count = nearest_bucket.iloc[0]["active_waiter_count"]
                # More waiters → slightly faster (distributed load)
                cycle_time *= 1.0 / (0.8 + 0.2 * active_count / len(waiter_ids))

            completed_ts = accepted_ts + timedelta(seconds=cycle_time)

            orders.append(
                {
                    "order_id": f"order_{order_counter}",
                    "shift_id": shift_id,  # Venue-level shift for fair comparison grouping
                    "waiter_shift_id": f"{waiter_id}_shift_{shift_id}",  # Individual waiter session
                    "assigned_waiter_id": waiter_id,
                    "accepted_ts": accepted_ts,
                    "completed_ts": completed_ts,
                    "items": order_items,
                }
            )

            order_counter += 1

    return pd.DataFrame(orders)


def generate_simple_mock_data(n_orders: int = 100) -> pd.DataFrame:
    """Generate simple mock data for quick testing (orders only).

    Args:
        n_orders: Number of orders to generate

    Returns:
        DataFrame with simple order data
    """
    np.random.seed(42)

    orders = []
    for i in range(n_orders):
        waiter_id = f"W{(i % 5) + 1}"
        shift_id = f"S{(i % 3) + 1}"

        items = [
            {"item_id": f"item_{j}", "quantity": np.random.randint(1, 4)}
            for j in range(np.random.randint(1, 4))
        ]

        accepted_ts = datetime(2026, 1, 1, 18, 0) + timedelta(minutes=i * 5)
        cycle_time = np.random.uniform(300, 900)  # 5-15 minutes
        completed_ts = accepted_ts + timedelta(seconds=cycle_time)

        orders.append(
            {
                "order_id": f"O{i+1}",
                "shift_id": shift_id,
                "assigned_waiter_id": waiter_id,
                "accepted_ts": accepted_ts,
                "completed_ts": completed_ts,
                "items": items,
            }
        )

    return pd.DataFrame(orders)


def add_noise_to_data(
    orders_df: pd.DataFrame, noise_level: float = 0.1
) -> pd.DataFrame:
    """Add random noise to order completion times.

    Useful for testing robustness of the algorithm.

    Args:
        orders_df: Orders DataFrame
        noise_level: Fraction of noise to add (0-1)

    Returns:
        Modified orders DataFrame
    """
    orders_df = orders_df.copy()

    for idx in orders_df.index:
        accepted = orders_df.loc[idx, "accepted_ts"]
        completed = orders_df.loc[idx, "completed_ts"]
        cycle_time = (completed - accepted).total_seconds()

        # Add noise
        noise = np.random.normal(0, noise_level * cycle_time)
        new_cycle_time = max(cycle_time + noise, 60)  # Min 1 minute

        orders_df.loc[idx, "completed_ts"] = accepted + timedelta(seconds=new_cycle_time)

    return orders_df
