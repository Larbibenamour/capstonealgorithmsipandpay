# Sip & Pay — Waiter Performance Scoring Algorithm

A capstone project implementing a fair, interpretable, complexity-adjusted waiter
performance scoring system for nightlife digital ordering platforms.

The algorithm scores waiters from 0–100 per shift using only data that the ordering
system naturally logs. It does NOT use kitchen completion times or delivery timestamps —
it is designed as a relative, within-group comparison.

---

## Repository Structure

```
src/scoring/        Core algorithm modules
src/data/           Synthetic data generator
src/evaluation/     Evaluation and validation scripts
scripts/            Runnable demo and usage scripts
tests/              Pytest unit test suite
.github/workflows/  CI/CD configuration
```

---

## Quick Start

### Prerequisites
- Python 3.9+
- A virtual environment (already set up as `venv/`)

### 1. Activate the Virtual Environment
```bash
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
# or with dev/evaluation extras:
pip install -e ".[dev]"
pip install -e ".[evaluation]"
```

### 3. Run the Algorithm — Demo Scripts

#### Full Algorithm Walkthrough (recommended starting point)
Walks through all 5 scoring steps with printed output for each stage.
```bash
python scripts/demo_algorithm.py
```

#### Minimal Usage Example
Shows how to call `compute_scores()` and inspect the JSON output.
```bash
python scripts/example_usage.py
```

#### Randomized 3-Waiter Test
Generates a random set of 3 waiters and scores them. Output differs every run.
```bash
python scripts/test_random.py
```

---

## Running the Test Suite

All unit tests live in `tests/` and are run with `pytest`.

```bash
# Run all 60 tests
pytest tests/

# Verbose output
pytest tests/ -v

# With coverage report
pytest tests/ --cov=src --cov-report=term-missing
```

### What Each Test File Covers

| File | What It Tests |
|---|---|
| `tests/test_algorithm.py` | End-to-end scoring pipeline with synthetic data |
| `tests/test_components.py` | Each individual component: complexity, normalization, confidence, shrinkage, aggregation |
| `tests/test_complexity.py` | Order complexity calculation and credit allocation |
| `tests/test_normalize.py` | Percentile ranking and composite score calculation |
| `tests/test_confidence.py` | Confidence scoring and shrinkage monotonicity |
| `tests/test_aggregate.py` | Weekly/monthly aggregation and winsorization |
| `tests/test_ablations.py` | Ablation study pipeline |
| `tests/test_venue_periods.py` | Venue time period clustering |

---

## Running Evaluation Scripts

```bash
# Exploratory data analysis on synthetic data
python src/evaluation/eda.py

# Compare naive ranking vs complexity-adjusted ranking
python src/evaluation/comparisons.py

# Sensitivity analysis: vary weights and measure score variance
python src/evaluation/sensitivity.py

# Temporal stability: week-to-week score correlation
python src/evaluation/stability.py

# Ablation studies: disable one component at a time
python src/evaluation/ablations.py
```

---

## Core Algorithm Modules (`src/scoring/`)

| File | Purpose |
|---|---|
| `schema.py` | Pydantic data models: `Order`, `WaiterShift`, `VenueTimePeriod`, `StaffingBucket` |
| `complexity.py` | Computes order complexity as `Σ(quantity_i × item_weight_i)`. Defaults to weight = 1.0 per item. |
| `features.py` | Derives `eff_raw` (efficiency), `throughput`, `consistency`, and applies workload intensity adjustment |
| `normalize.py` | Converts raw metrics to 0–100 percentile scores within each `venue_time_period_id`. Applies winsorization. |
| `confidence.py` | Computes confidence score from sample size, total complexity, and stability. Applies Bayesian-inspired shrinkage. |
| `score_shift.py` | Main entry point: `compute_scores(orders_df, shifts_df, staffing_df, config)`. Orchestrates all steps. |
| `aggregate.py` | Aggregates shift-level scores into weekly/monthly summaries using complexity-weighted averages. |
| `venue_periods.py` | Auto-generates `venue_time_period_id` by clustering waiter shifts with ≥2 hours overlap at the same venue. |

---

## Key Design Decisions

### 1. Venue Time Period (`venue_time_period_id`)
Waiters are grouped into overlapping work windows at the same venue. All scoring comparisons
happen only within this group — ensuring fair peer comparison under shared conditions
(same kitchen speed, same rush hour, same night).

### 2. Within-Group Percentile Normalization
Raw metrics are converted to 0–100 using percentile ranking relative to peers.
Robust statistics (median, IQR) are used throughout to handle outliers.

### 3. Workload Intensity Adjustment
A multiplicative factor based on `active_waiter_count` per 15-minute bucket adjusts scores.
Fewer active waiters = higher load = the efficiency score is adjusted upward to credit harder work.

### 4. Confidence Score
Combines three sub-scores:
- **Sample size confidence**: increases with more orders handled
- **Complexity confidence**: increases with higher total workload
- **Stability confidence**: increases as performance variance decreases

### 5. Shrinkage (Bayesian-inspired)
Low-confidence scores are blended toward the group median:
```
final_score = raw_score × C_eff + median × (1 − C_eff)
```
This prevents a waiter with few lucky orders from topping the leaderboard.

### 6. Temporal Aggregation
Weekly/monthly scores are complexity-weighted averages of shift scores.
Winsorization (5th–95th percentile cap) prevents a single outlier shift from dominating.

---

## Component Weights (Configurable)

| Component | Default Weight | Rationale |
|---|---|---|
| Efficiency | 50% | Primary indicator of speed per unit of work |
| Throughput | 30% | Measures volume handled per hour |
| Consistency | 20% | Rewards reliable, stable performance |

Composite formula: `Score = 0.50 × S_eff + 0.30 × S_thr + 0.20 × S_cons`

---

## Output Format

`compute_scores()` returns a JSON-serializable nested dict:

```json
{
  "venue_period_1": {
    "waiter_A": {
      "score": 78.4,
      "confidence": 0.81,
      "components": { "efficiency": 82.0, "throughput": 71.0, "consistency": 75.0 },
      "metrics": { "n_orders": 42, "total_complexity": 210.0, "active_hours": 6.0 }
    }
  }
}
```

---

## Known Limitations

- Cycle time includes kitchen prep — waiters are not scored on absolute delivery speed
- No delivery timestamp or kitchen-complete timestamp is available
- Scores are relative: they have no meaning outside the peer group
- Item weights default to 1.0 unless custom weights are provided
- Order splitting across multiple waiters is not implemented in v1

---

## Data & Reproducibility

All tests and evaluation scripts use **programmatically generated synthetic data** (no real venue data).
The mock data generator (`src/data/mock_data.py`) produces realistic waiter profiles —
fast, slow, consistent, erratic, and low-sample — across multiple venue time periods.
All results in the thesis were generated with `seed=42`.

---

## CI/CD

Tests run automatically on every push via GitHub Actions (Python 3.9, 3.10, 3.11, 3.13).
See `.github/workflows/ci.yml` for the workflow configuration.
