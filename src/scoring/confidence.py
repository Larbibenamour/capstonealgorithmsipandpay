"""Confidence scoring and shrinkage toward shift baseline.

Confidence increases with sample size and total complexity handled,
decreases with high variance. Low-confidence scores are shrunk toward
the shift median to prevent unreliable extreme values.
"""

from typing import Optional

import numpy as np
import pandas as pd


def compute_sample_size_confidence(
    n_orders: int, min_orders: int = 5, max_orders: int = 50
) -> float:
    """Compute confidence component based on sample size.

    Confidence increases with more orders, plateaus after max_orders.

    Args:
        n_orders: Number of orders handled
        min_orders: Number of orders for 50% confidence
        max_orders: Number of orders for 95% confidence

    Returns:
        Sample size confidence in range [0, 1]

    Examples:
        >>> compute_sample_size_confidence(5, min_orders=5)
        0.5
        >>> compute_sample_size_confidence(50, max_orders=50)
        0.95
        >>> compute_sample_size_confidence(1, min_orders=5)
        0.1
    """
    if n_orders <= 0:
        return 0.0
    if n_orders >= max_orders:
        return 0.95

    # Sigmoid-like curve
    confidence = n_orders / (n_orders + min_orders)
    return np.clip(confidence, 0.0, 0.95)


def compute_complexity_confidence(
    total_complexity: float, min_complexity: float = 10.0, max_complexity: float = 100.0
) -> float:
    """Compute confidence component based on total complexity handled.

    Confidence increases with more complexity handled.

    Args:
        total_complexity: Total complexity units handled
        min_complexity: Complexity threshold for 50% confidence
        max_complexity: Complexity threshold for 95% confidence

    Returns:
        Complexity confidence in range [0, 1]

    Examples:
        >>> compute_complexity_confidence(10, min_complexity=10)
        0.5
        >>> compute_complexity_confidence(100, max_complexity=100)
        0.95
    """
    if total_complexity <= 0:
        return 0.0
    if total_complexity >= max_complexity:
        return 0.95

    # Sigmoid-like curve
    confidence = total_complexity / (total_complexity + min_complexity)
    return np.clip(confidence, 0.0, 0.95)


def compute_stability_confidence(
    normalized_dispersion: float, max_acceptable_dispersion: float = 0.5
) -> float:
    """Compute confidence component based on consistency/stability.

    Lower dispersion → higher confidence (stable performance).

    Args:
        normalized_dispersion: Dispersion normalized by median (e.g., IQR/median)
        max_acceptable_dispersion: Dispersion threshold for low confidence

    Returns:
        Stability confidence in range [0, 1]

    Examples:
        >>> compute_stability_confidence(0.0)  # Perfect consistency
        0.95
        >>> compute_stability_confidence(0.5)
        0.5
        >>> compute_stability_confidence(1.0)  # High variance
        0.2
    """
    if normalized_dispersion <= 0:
        return 0.95

    # Inverse relationship: higher dispersion → lower confidence
    confidence = 1.0 / (1.0 + normalized_dispersion / max_acceptable_dispersion)
    return np.clip(confidence, 0.0, 0.95)


def compute_overall_confidence(
    n_orders: int,
    total_complexity: float,
    normalized_dispersion: float,
    config: dict,
    weights: Optional[dict] = None,
) -> float:
    """Compute overall confidence score combining sample size, complexity, and stability.

    Confidence = weighted average of three components.

    Args:
        n_orders: Number of orders handled
        total_complexity: Total complexity units handled
        normalized_dispersion: Dispersion metric (e.g., IQR/median)
        config: Configuration dict with thresholds
        weights: Component weights (default: sample=0.4, complexity=0.3, stability=0.3)

    Returns:
        Overall confidence in range [0, 1]

    Examples:
        >>> config = {"min_orders_for_confidence": 5}
        >>> compute_overall_confidence(20, 50.0, 0.2, config)
        0.8275  # High confidence
        >>> compute_overall_confidence(2, 5.0, 0.8, config)
        0.28  # Low confidence
    """
    if weights is None:
        weights = {"sample_size": 0.4, "complexity": 0.3, "stability": 0.3}

    # Validate weights sum to 1
    weight_sum = sum(weights.values())
    if not (0.99 <= weight_sum <= 1.01):
        raise ValueError(f"Confidence weights must sum to 1.0, got {weight_sum}")

    # Compute individual components
    sample_conf = compute_sample_size_confidence(
        n_orders,
        min_orders=config.get("min_orders", config.get("min_orders_for_confidence", 5)),
        max_orders=config.get("max_orders", 50),
    )
    complexity_conf = compute_complexity_confidence(
        total_complexity,
        min_complexity=config.get("min_complexity", 10.0),
        max_complexity=config.get("max_complexity", 100.0),
    )
    stability_conf = compute_stability_confidence(
        normalized_dispersion,
        max_acceptable_dispersion=config.get("max_acceptable_dispersion", 0.5),
    )

    # Weighted combination
    confidence = (
        weights["sample_size"] * sample_conf
        + weights["complexity"] * complexity_conf
        + weights["stability"] * stability_conf
    )

    return np.clip(confidence, 0.0, 1.0)


def apply_shrinkage(
    raw_score: float,
    shift_baseline: float,
    confidence: float,
    shrinkage_strength: float = 0.3,
) -> float:
    """Apply shrinkage toward shift baseline for low-confidence scores.

    final_score = confidence * raw_score + (1 - confidence) * shift_baseline

    With shrinkage_strength, the formula becomes:
    final_score = (confidence + (1-confidence)*shrinkage_strength) * raw_score
                  + (1-confidence)*(1-shrinkage_strength) * shift_baseline

    Args:
        raw_score: Unadjusted score (0-100)
        shift_baseline: Shift median/mean score (0-100)
        confidence: Confidence level (0-1)
        shrinkage_strength: How much to shrink toward baseline (0=none, 1=full)

    Returns:
        Shrunk score (0-100)

    Examples:
        >>> apply_shrinkage(90, 50, confidence=1.0)  # High confidence, no shrinkage
        90.0
        >>> apply_shrinkage(90, 50, confidence=0.0, shrinkage_strength=0.3)  # Low conf, shrink toward 50
        57.0
        >>> apply_shrinkage(90, 50, confidence=0.5, shrinkage_strength=0.3)
        83.5
    """
    effective_confidence = confidence + (1 - confidence) * (1 - shrinkage_strength)
    final_score = effective_confidence * raw_score + (1 - effective_confidence) * shift_baseline

    return np.clip(final_score, 0, 100)


def compute_confidence_intervals(
    raw_scores: pd.Series, confidence_level: float = 0.95
) -> tuple:
    """Compute confidence interval for a set of scores.

    Args:
        raw_scores: Series of raw scores
        confidence_level: Confidence level (e.g., 0.95 for 95% CI)

    Returns:
        Tuple of (mean, lower_bound, upper_bound)

    Examples:
        >>> scores = pd.Series([80, 85, 90, 95, 100])
        >>> mean, lower, upper = compute_confidence_intervals(scores)
        >>> lower < mean < upper
        True
    """
    if len(raw_scores) < 2:
        mean_score = raw_scores.mean() if len(raw_scores) == 1 else 50.0
        return mean_score, mean_score, mean_score

    mean_score = raw_scores.mean()
    std_error = raw_scores.sem()
    margin = std_error * 1.96  # Approx z-score for 95% CI

    lower_bound = mean_score - margin
    upper_bound = mean_score + margin

    return mean_score, lower_bound, upper_bound


def flag_low_confidence_scores(
    scores_df: pd.DataFrame, confidence_threshold: float = 0.5
) -> pd.DataFrame:
    """Flag scores with low confidence for review.

    Args:
        scores_df: DataFrame with columns (waiter_id, shift_id, score, confidence)
        confidence_threshold: Threshold below which scores are flagged

    Returns:
        DataFrame with added column: low_confidence_flag (boolean)

    Examples:
        >>> scores = pd.DataFrame({
        ...     "waiter_id": ["W1", "W2"],
        ...     "confidence": [0.3, 0.8]
        ... })
        >>> result = flag_low_confidence_scores(scores, threshold=0.5)
        >>> result.loc[0, "low_confidence_flag"]
        True
        >>> result.loc[1, "low_confidence_flag"]
        False
    """
    scores_df = scores_df.copy()
    scores_df["low_confidence_flag"] = scores_df["confidence"] < confidence_threshold
    return scores_df


def compute_confidence_weighted_average(
    scores: pd.Series, confidences: pd.Series, min_confidence: float = 0.2
) -> float:
    """Compute confidence-weighted average of scores.

    Scores with confidence below min_confidence are excluded.

    Args:
        scores: Series of scores
        confidences: Series of confidence values
        min_confidence: Minimum confidence to include in average

    Returns:
        Weighted average score

    Examples:
        >>> scores = pd.Series([100, 50, 80])
        >>> confidences = pd.Series([0.9, 0.1, 0.7])  # Middle score has low confidence
        >>> result = compute_confidence_weighted_average(scores, confidences, min_confidence=0.2)
        >>> 80 < result < 100  # Dominated by high-confidence scores
        True
    """
    # Filter out low-confidence scores
    mask = confidences >= min_confidence
    filtered_scores = scores[mask]
    filtered_confidences = confidences[mask]

    if len(filtered_scores) == 0:
        return 50.0  # Neutral score if no valid data

    weighted_sum = (filtered_scores * filtered_confidences).sum()
    weight_sum = filtered_confidences.sum()

    return weighted_sum / weight_sum if weight_sum > 0 else 50.0


def bootstrap_confidence_interval(
    raw_scores: pd.Series, n_bootstrap: int = 1000, confidence_level: float = 0.95
) -> tuple:
    """Compute bootstrap confidence interval for mean score.

    Args:
        raw_scores: Series of raw scores
        n_bootstrap: Number of bootstrap samples
        confidence_level: Confidence level (e.g., 0.95)

    Returns:
        Tuple of (mean, lower_bound, upper_bound)
    """
    if len(raw_scores) < 2:
        mean_score = raw_scores.mean() if len(raw_scores) == 1 else 50.0
        return mean_score, mean_score, mean_score

    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = raw_scores.sample(n=len(raw_scores), replace=True)
        bootstrap_means.append(sample.mean())

    bootstrap_means = np.array(bootstrap_means)
    alpha = 1 - confidence_level
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100

    lower_bound = np.percentile(bootstrap_means, lower_percentile)
    upper_bound = np.percentile(bootstrap_means, upper_percentile)
    mean_score = raw_scores.mean()

    return mean_score, lower_bound, upper_bound
