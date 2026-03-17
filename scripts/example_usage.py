"""Example usage of the Sip&Pay scoring system.

This script demonstrates how to:
1. Generate or load order data
2. Configure the scoring algorithm
3. Compute shift-level scores
4. Aggregate scores to weekly/monthly periods
5. Export results
"""

import json

from src.data.mock_data import generate_mock_data
from src.scoring.aggregate import aggregate_scores_by_period, compute_trend, generate_leaderboard
from src.scoring.score_shift import compute_scores


def main():
    """Run example scoring workflow."""

    print("=" * 70)
    print("SIP&PAY WAITER PERFORMANCE SCORING - EXAMPLE USAGE")
    print("=" * 70)

    # Step 1: Generate mock data
    print("\n[1/5] Generating mock data...")
    orders_df, shifts_df, staffing_df = generate_mock_data(
        n_shifts=20, n_waiters=8, orders_per_shift=50, seed=42
    )

    print(f"  Generated {len(orders_df)} orders across {len(shifts_df)} shifts")
    print(f"  Number of waiters: 8")

    # Step 2: Configure scoring
    print("\n[2/5] Configuring scoring algorithm...")
    config = {
        "weights": {
            "efficiency": 0.50,  # Highest weight
            "throughput": 0.30,  # Medium weight
            "consistency": 0.20,  # Lower weight
        },
        "item_weights": {
            # Default: all items have weight 1.0
            # Can customize per item: "burger": 2.0, "cocktail": 1.5, etc.
        },
        "workload_adjustment": "multiplicative",  # or "stratified"
        "shrinkage_strength": 0.3,  # 30% shrinkage toward shift median
        "winsorize_quantile": 0.05,  # Cap extreme shifts at 5th/95th percentile
        "min_orders_for_confidence": 5,  # Orders needed for 50% confidence
    }

    print("  Component weights:")
    for component, weight in config["weights"].items():
        print(f"    {component.capitalize()}: {weight:.0%}")

    # Step 3: Compute shift-level scores
    print("\n[3/5] Computing shift-level scores...")
    results = compute_scores(orders_df, shifts_df, staffing_df, config)

    print(f"  Scored {len(results)} shifts")

    # Display sample results
    print("\n  Sample shift results (Shift 1):")
    shift_1_results = results.get("shift_1", {})
    for waiter_id, data in list(shift_1_results.items())[:3]:
        print(f"\n    {waiter_id}:")
        print(f"      Score: {data['score']:.1f}/100")
        print(f"      Confidence: {data['confidence']:.2f}")
        print(f"      Components:")
        print(f"        Efficiency: {data['components']['efficiency']:.1f}")
        print(f"        Throughput: {data['components']['throughput']:.1f}")
        print(f"        Consistency: {data['components']['consistency']:.1f}")
        print(f"      Orders handled: {data['metrics']['n_orders']}")

    # Step 4: Aggregate to weekly scores
    print("\n[4/5] Aggregating to weekly scores...")
    weekly_scores = aggregate_scores_by_period(
        results, shifts_df, period="week", min_confidence=0.3, winsorize_quantile=0.05
    )

    print(f"  Generated {len(weekly_scores)} waiter-week combinations")

    if not weekly_scores.empty:
        print("\n  Top performers (Week 1):")
        leaderboard = generate_leaderboard(weekly_scores, top_n=5)
        for _, row in leaderboard.iterrows():
            print(
                f"    #{int(row['rank'])} {row['waiter_id']}: "
                f"{row['aggregated_score']:.1f} (conf: {row['mean_confidence']:.2f}, "
                f"shifts: {int(row['n_shifts'])})"
            )

        # Compute trends
        trends = compute_trend(weekly_scores)
        print("\n  Performance trends:")
        for _, row in trends.head(5).iterrows():
            direction = "improving" if row["trend_slope"] > 0 else "declining"
            print(
                f"    {row['waiter_id']}: {direction} "
                f"(slope: {row['trend_slope']:+.2f} points/week)"
            )

    # Step 5: Export results
    print("\n[5/5] Exporting results...")

    # Export shift-level scores to JSON
    with open("shift_scores.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("  Shift scores saved to: shift_scores.json")

    # Export weekly aggregated scores to CSV
    if not weekly_scores.empty:
        weekly_scores.to_csv("weekly_scores.csv", index=False)
        print("  Weekly scores saved to: weekly_scores.csv")

    print("\n" + "=" * 70)
    print("EXAMPLE COMPLETE")
    print("=" * 70)

    print("\nNext steps:")
    print("  1. Review shift_scores.json for detailed results")
    print("  2. Analyze weekly_scores.csv for trends over time")
    print("  3. Run evaluation scripts:")
    print("     - python src/evaluation/eda.py")
    print("     - python src/evaluation/comparisons.py")
    print("     - python src/evaluation/sensitivity.py")
    print("     - python src/evaluation/stability.py")


if __name__ == "__main__":
    main()
