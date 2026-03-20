"""Unit tests for src/scoring/venue_periods.py."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.scoring.venue_periods import (
    assign_orders_to_venue_time_periods,
    create_venue_time_periods_from_shifts,
    validate_venue_time_period_fairness,
)


def _make_shifts(shift_defs):
    """Helper: create a waiter_shifts DataFrame from a list of (id, waiter, in, out) tuples."""
    rows = []
    for shift_id, waiter_id, clock_in, clock_out in shift_defs:
        rows.append(
            {
                "waiter_shift_id": shift_id,
                "waiter_id": waiter_id,
                "clock_in_ts": clock_in,
                "clock_out_ts": clock_out,
            }
        )
    return pd.DataFrame(rows)


BASE = datetime(2026, 1, 10, 22, 0, 0)  # 10pm


class TestCreateVenueTimePeriodsFromShifts:
    """Tests for create_venue_time_periods_from_shifts."""

    def test_overlapping_shifts_grouped_into_one_period(self):
        """Three waiters with heavily overlapping shifts should form a single period."""
        shifts_df = _make_shifts(
            [
                ("ws1", "w1", BASE, BASE + timedelta(hours=6)),
                ("ws2", "w2", BASE + timedelta(minutes=15), BASE + timedelta(hours=6, minutes=15)),
                ("ws3", "w3", BASE + timedelta(minutes=30), BASE + timedelta(hours=5, minutes=30)),
            ]
        )
        updated_shifts, periods_df = create_venue_time_periods_from_shifts(shifts_df, min_overlap_hours=2.0)

        assert len(periods_df) == 1, "All overlapping shifts should be in one period"
        assert updated_shifts["venue_time_period_id"].nunique() == 1
        assert updated_shifts["venue_time_period_id"].notna().all()

    def test_non_overlapping_shifts_produce_separate_periods(self):
        """Shifts on completely different days should form separate periods."""
        day1 = datetime(2026, 1, 10, 22, 0, 0)
        day2 = datetime(2026, 1, 11, 22, 0, 0)
        shifts_df = _make_shifts(
            [
                ("ws1", "w1", day1, day1 + timedelta(hours=5)),
                ("ws2", "w2", day2, day2 + timedelta(hours=5)),
            ]
        )
        updated_shifts, periods_df = create_venue_time_periods_from_shifts(shifts_df, min_overlap_hours=2.0)

        assert len(periods_df) == 2, "Non-overlapping days should produce two separate periods"
        assert updated_shifts["venue_time_period_id"].nunique() == 2

    def test_returned_periods_df_has_required_columns(self):
        """periods_df must contain the expected schema columns."""
        shifts_df = _make_shifts(
            [
                ("ws1", "w1", BASE, BASE + timedelta(hours=5)),
                ("ws2", "w2", BASE + timedelta(minutes=10), BASE + timedelta(hours=5)),
            ]
        )
        _, periods_df = create_venue_time_periods_from_shifts(shifts_df)

        required_cols = {"venue_time_period_id", "venue_id", "period_start_ts", "period_end_ts"}
        assert required_cols.issubset(set(periods_df.columns))

    def test_period_start_and_end_span_all_shifts(self):
        """Period boundaries should encompass the earliest clock-in and latest clock-out."""
        clock_in_1 = BASE
        clock_out_2 = BASE + timedelta(hours=7)
        shifts_df = _make_shifts(
            [
                ("ws1", "w1", clock_in_1, BASE + timedelta(hours=5)),
                ("ws2", "w2", BASE + timedelta(minutes=30), clock_out_2),
            ]
        )
        _, periods_df = create_venue_time_periods_from_shifts(shifts_df, min_overlap_hours=2.0)

        assert len(periods_df) == 1
        assert periods_df.iloc[0]["period_start_ts"] == clock_in_1
        assert periods_df.iloc[0]["period_end_ts"] == clock_out_2


class TestAssignOrdersToVenueTimePeriods:
    """Tests for assign_orders_to_venue_time_periods."""

    def test_orders_receive_correct_period_id(self):
        """Orders should be mapped to the venue_time_period_id of their waiter's shift."""
        shifts_df = pd.DataFrame(
            [
                {"waiter_shift_id": "ws1", "venue_time_period_id": "period_A"},
                {"waiter_shift_id": "ws2", "venue_time_period_id": "period_B"},
            ]
        )
        orders_df = pd.DataFrame(
            [
                {"order_id": 1, "waiter_shift_id": "ws1"},
                {"order_id": 2, "waiter_shift_id": "ws2"},
                {"order_id": 3, "waiter_shift_id": "ws1"},
            ]
        )
        result = assign_orders_to_venue_time_periods(orders_df, shifts_df)

        assert result.loc[result["order_id"] == 1, "venue_time_period_id"].iloc[0] == "period_A"
        assert result.loc[result["order_id"] == 2, "venue_time_period_id"].iloc[0] == "period_B"
        assert result.loc[result["order_id"] == 3, "venue_time_period_id"].iloc[0] == "period_A"

    def test_orders_with_unknown_shift_get_nan(self):
        """Orders whose waiter_shift_id is not in shifts_df should get NaN period id."""
        shifts_df = pd.DataFrame([{"waiter_shift_id": "ws1", "venue_time_period_id": "period_A"}])
        orders_df = pd.DataFrame([{"order_id": 99, "waiter_shift_id": "ws_unknown"}])
        result = assign_orders_to_venue_time_periods(orders_df, shifts_df)

        assert pd.isna(result.loc[0, "venue_time_period_id"])

    def test_original_dataframe_is_not_mutated(self):
        """Input DataFrames should not be modified in place."""
        shifts_df = pd.DataFrame([{"waiter_shift_id": "ws1", "venue_time_period_id": "period_A"}])
        orders_df = pd.DataFrame([{"order_id": 1, "waiter_shift_id": "ws1"}])
        original_cols = list(orders_df.columns)

        assign_orders_to_venue_time_periods(orders_df, shifts_df)

        assert list(orders_df.columns) == original_cols


class TestValidateVenueTimePeriodFairness:
    """Tests for validate_venue_time_period_fairness."""

    def test_returns_correct_period_count(self):
        """n_periods should equal the number of rows in venue_time_periods_df."""
        shifts_df = pd.DataFrame(
            [
                {"waiter_shift_id": "ws1", "venue_time_period_id": "p1"},
                {"waiter_shift_id": "ws2", "venue_time_period_id": "p1"},
                {"waiter_shift_id": "ws3", "venue_time_period_id": "p2"},
            ]
        )
        periods_df = pd.DataFrame(
            [
                {"venue_time_period_id": "p1"},
                {"venue_time_period_id": "p2"},
            ]
        )
        stats = validate_venue_time_period_fairness(shifts_df, periods_df)

        assert stats["n_periods"] == 2

    def test_single_waiter_period_is_flagged(self):
        """Periods with only one waiter should appear in single_waiter_periods list."""
        shifts_df = pd.DataFrame(
            [
                {"waiter_shift_id": "ws1", "venue_time_period_id": "p1"},
                {"waiter_shift_id": "ws2", "venue_time_period_id": "p2"},
                {"waiter_shift_id": "ws3", "venue_time_period_id": "p2"},
            ]
        )
        periods_df = pd.DataFrame(
            [
                {"venue_time_period_id": "p1"},
                {"venue_time_period_id": "p2"},
            ]
        )
        stats = validate_venue_time_period_fairness(shifts_df, periods_df)

        assert "p1" in stats["single_waiter_periods"]
        assert "p2" not in stats["single_waiter_periods"]
        assert stats["periods_with_multiple_waiters"] == 1

    def test_empty_periods_df_returns_zero_counts(self):
        """An empty periods_df should return zero for all numeric stats."""
        shifts_df = pd.DataFrame(columns=["waiter_shift_id", "venue_time_period_id"])
        periods_df = pd.DataFrame(columns=["venue_time_period_id"])
        stats = validate_venue_time_period_fairness(shifts_df, periods_df)

        assert stats["n_periods"] == 0
        assert stats["avg_waiters_per_period"] == 0
