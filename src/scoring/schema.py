"""Data models and schema definitions using Pydantic.

This module defines the core data structures for orders, shifts, staffing,
and scoring outputs. Designed to support both single-waiter and future
multi-waiter order assignments.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class OrderItem(BaseModel):
    """Represents a single item in an order."""

    item_id: Union[str, int] = Field(..., description="Unique item identifier or name")
    quantity: int = Field(..., ge=1, description="Number of units ordered")
    category: Optional[str] = Field(None, description="Item category (e.g., 'drink', 'food')")
    price: Optional[float] = Field(None, ge=0, description="Item price (optional)")


class Order(BaseModel):
    """Represents a single order in the system."""

    order_id: Union[str, int] = Field(..., description="Unique order identifier")
    waiter_shift_id: Union[str, int] = Field(..., description="Individual waiter's shift session")
    assigned_waiter_id: Union[str, int] = Field(..., description="Primary waiter assigned (MVP v1)")
    accepted_ts: datetime = Field(..., description="Timestamp when kitchen accepted order")
    completed_ts: datetime = Field(..., description="Timestamp when order marked completed")
    items: List[OrderItem] = Field(..., min_length=1, description="Items in the order")
    venue_time_period_id: Optional[Union[str, int]] = Field(
        None, description="Groups waiters working overlapping times (for fair comparison)"
    )

    @field_validator("completed_ts")
    @classmethod
    def validate_timestamps(cls, v: datetime, info: Any) -> datetime:
        """Ensure completed_ts is after accepted_ts."""
        if "accepted_ts" in info.data and v <= info.data["accepted_ts"]:
            raise ValueError("completed_ts must be after accepted_ts")
        return v

    @property
    def cycle_time_seconds(self) -> float:
        """Compute cycle time in seconds (completed - accepted)."""
        return (self.completed_ts - self.accepted_ts).total_seconds()


class WaiterShift(BaseModel):
    """Represents an individual waiter's work session (clock-in to clock-out).
    
    Note: Multiple waiters working overlapping times will have different waiter_shift_ids
    but share the same venue_time_period_id for fair comparison.
    """

    waiter_shift_id: Union[str, int] = Field(..., description="Unique waiter shift session ID")
    waiter_id: Union[str, int] = Field(..., description="Waiter identifier")
    clock_in_ts: datetime = Field(..., description="When waiter clocked in")
    clock_out_ts: datetime = Field(..., description="When waiter clocked out")
    venue_time_period_id: Optional[Union[str, int]] = Field(
        None, description="Links to venue time period for comparison grouping"
    )

    @field_validator("clock_out_ts")
    @classmethod
    def validate_shift_times(cls, v: datetime, info: Any) -> datetime:
        """Ensure clock_out_ts is after clock_in_ts."""
        if "clock_in_ts" in info.data and v < info.data["clock_in_ts"]:
            raise ValueError("clock_out_ts must be after clock_in_ts")
        return v


class VenueTimePeriod(BaseModel):
    """Represents a time period at a venue where multiple waiters worked overlapping shifts.
    
    This is the comparison unit - waiters in the same venue_time_period faced the same
    kitchen crew, rush hours, and operational conditions, making comparison fair.
    
    Example: Friday night service at Downtown location (11pm-5am) would be one venue_time_period,
    grouping all waiters who worked during that time for fair performance comparison.
    """

    venue_time_period_id: Union[str, int] = Field(..., description="Unique period identifier")
    venue_id: Union[str, int] = Field(..., description="Venue/location identifier")
    period_start_ts: datetime = Field(..., description="Service period start")
    period_end_ts: datetime = Field(..., description="Service period end")
    period_name: Optional[str] = Field(
        None, description="Human-readable name (e.g., 'Friday Night Service')"
    )

    @field_validator("period_end_ts")
    @classmethod
    def validate_period_times(cls, v: datetime, info: Any) -> datetime:
        """Ensure period_end_ts is after period_start_ts."""
        if "period_start_ts" in info.data and v < info.data["period_start_ts"]:
            raise ValueError("period_end_ts must be after period_start_ts")
        return v


# Legacy alias for backward compatibility
Shift = WaiterShift


class StaffingInterval(BaseModel):
    """Represents staffing levels in a time bucket for a venue time period."""

    venue_time_period_id: Union[str, int] = Field(..., description="Associated venue time period")
    bucket_start_ts: datetime = Field(..., description="Start of time bucket")
    active_waiter_count: int = Field(..., ge=0, description="Number of active waiters")


class ClockLog(BaseModel):
    """Staff clock-in/out log entry (alternative to pre-computed staffing).
    
    Note: This represents the raw clock data. The waiter_shift_id links to WaiterShift,
    which in turn links to venue_time_period_id for comparison grouping.
    """

    waiter_shift_id: Union[str, int] = Field(..., description="Individual waiter shift session")
    staff_id: Union[str, int] = Field(..., description="Staff member identifier")
    clock_in_ts: datetime = Field(..., description="Clock-in timestamp")
    clock_out_ts: Optional[datetime] = Field(None, description="Clock-out timestamp (if available)")


class OrderCredit(BaseModel):
    """Credit allocation for an order (supports future order-splitting).
    
    In MVP v1, each order has a single credit entry: (assigned_waiter_id, 1.0).
    In future versions, orders may split across multiple waiters with fractional credits.
    """

    order_id: Union[str, int] = Field(..., description="Order identifier")
    waiter_id: Union[str, int] = Field(..., description="Waiter receiving credit")
    credit_share: float = Field(..., ge=0, le=1, description="Fraction of order credited (0-1)")


class ComponentScores(BaseModel):
    """Individual component scores for a waiter in a shift."""

    efficiency: float = Field(..., ge=0, le=100, description="Efficiency score (0-100)")
    throughput: float = Field(..., ge=0, le=100, description="Throughput score (0-100)")
    consistency: float = Field(..., ge=0, le=100, description="Consistency score (0-100)")


class WaiterMetrics(BaseModel):
    """Raw metrics used for scoring a waiter in a shift."""

    n_orders: int = Field(..., ge=0, description="Number of orders handled")
    total_complexity: float = Field(..., ge=0, description="Total complexity units handled")
    active_hours: float = Field(..., ge=0, description="Hours actively working")
    median_eff_raw: float = Field(..., ge=0, description="Median efficiency raw value")
    eff_dispersion: float = Field(..., ge=0, description="Dispersion of efficiency (IQR or MAD)")


class WaiterShiftScore(BaseModel):
    """Complete scoring output for a waiter in a work session."""

    waiter_id: Union[str, int] = Field(..., description="Waiter identifier")
    waiter_shift_id: Union[str, int] = Field(..., description="Waiter shift session identifier")
    venue_time_period_id: Union[str, int] = Field(..., description="Venue time period (comparison group)")
    score: float = Field(..., ge=0, le=100, description="Composite score (0-100)")
    confidence: float = Field(..., ge=0, le=1, description="Confidence level (0-1)")
    components: ComponentScores = Field(..., description="Individual component scores")
    metrics: WaiterMetrics = Field(..., description="Raw metrics")


class ScoringConfig(BaseModel):
    """Configuration for the scoring algorithm."""

    weights: Dict[str, float] = Field(
        default={"efficiency": 0.50, "throughput": 0.30, "consistency": 0.20},
        description="Component weights (must sum to 1.0)",
    )
    item_weights: Dict[Union[str, int], float] = Field(
        default_factory=dict,
        description="Item-specific complexity weights (default 1.0 if not specified)",
    )
    workload_adjustment: str = Field(
        default="multiplicative",
        description="Workload adjustment method: 'multiplicative' or 'stratified'",
    )
    shrinkage_strength: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="Shrinkage toward shift median for low-confidence scores (0-1)",
    )
    winsorize_quantile: float = Field(
        default=0.05,
        ge=0,
        le=0.2,
        description="Quantile for winsorization in temporal aggregation",
    )
    bucket_minutes: int = Field(
        default=15, ge=1, description="Time bucket size for staffing aggregation (minutes)"
    )
    min_orders_for_confidence: int = Field(
        default=5, ge=1, description="Minimum orders for high confidence"
    )
    epsilon: float = Field(
        default=1e-6, gt=0, description="Small constant to prevent division by zero"
    )
    min_orders: int = Field(
        default=5, ge=1, description="Number of orders for 50% sample-size confidence"
    )
    max_orders: int = Field(
        default=50, ge=1, description="Number of orders for 95% sample-size confidence"
    )
    min_complexity: float = Field(
        default=10.0, gt=0, description="Complexity threshold for 50% complexity confidence"
    )
    max_complexity: float = Field(
        default=100.0, gt=0, description="Complexity threshold for 95% complexity confidence"
    )
    max_acceptable_dispersion: float = Field(
        default=0.5, gt=0, description="Dispersion threshold for stability confidence"
    )
    min_confidence_for_aggregation: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for inclusion in temporal aggregation",
    )

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Ensure weights sum to approximately 1.0."""
        required_keys = {"efficiency", "throughput", "consistency"}
        if not required_keys.issubset(v.keys()):
            raise ValueError(f"weights must contain keys: {required_keys}")
        weight_sum = sum(v.values())
        if not (0.99 <= weight_sum <= 1.01):
            raise ValueError(f"weights must sum to 1.0, got {weight_sum}")
        return v

    @field_validator("workload_adjustment")
    @classmethod
    def validate_workload_method(cls, v: str) -> str:
        """Validate workload adjustment method."""
        if v not in {"multiplicative", "stratified"}:
            raise ValueError("workload_adjustment must be 'multiplicative' or 'stratified'")
        return v
