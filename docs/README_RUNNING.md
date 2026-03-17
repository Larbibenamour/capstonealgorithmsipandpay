# Sip & Pay — How to Run the Algorithm & Tests

## Prerequisites

- Python 3.9+
- A virtual environment (already set up as `venv/`)

---

## 1. Activate the Virtual Environment

```bash
source venv/bin/activate
```

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
# or if using pyproject.toml:
pip install -e .
```

---

## 3. Run the Algorithm — Demo Scripts

All runnable scripts are in the `scripts/` folder.

### Full Algorithm Walkthrough (recommended starting point)
Walks through all 5 scoring steps with printed output for each stage.
```bash
python scripts/demo_algorithm.py
```

### Example Usage
Shows how to call `compute_scores()` with a minimal setup and inspect the JSON output.
```bash
python scripts/example_usage.py
```

### Randomized 3-Waiter Test
Generates a random set of 3 waiters and scores them. Output is different every run.
```bash
python scripts/test_random.py
```

---

## 4. Run the Unit Test Suite

All unit tests live in the `tests/` folder and are run with `pytest`.

### Run all tests:
```bash
pytest tests/
```

### Run with verbose output (recommended for debugging):
```bash
pytest tests/ -v
```

### Run a specific test file:
```bash
pytest tests/test_components.py -v
pytest tests/test_algorithm.py -v
```

### Run with coverage report:
```bash
pytest tests/ --cov=src --cov-report=term-missing
```

---

## 5. What Each Test File Covers

| File | What It Tests |
|---|---|
| `tests/test_algorithm.py` | End-to-end scoring pipeline with synthetic data |
| `tests/test_components.py` | Each individual component: complexity, normalization, confidence, shrinkage, aggregation |
| `tests/test_complexity.py` | Order complexity calculation and credit allocation |
| `tests/test_normalize.py` | Percentile ranking and composite score calculation |
| `tests/test_confidence.py` | Confidence scoring and shrinkage monotonicity |
| `tests/test_aggregate.py` | Weekly/monthly aggregation and winsorization |

---

## 6. Run Evaluation Scripts

Evaluation scripts are in `src/evaluation/` and are used for validating algorithm behavior.

```bash
# Exploratory data analysis on synthetic data
python src/evaluation/eda.py

# Compare naive ranking vs complexity-adjusted ranking
python src/evaluation/comparisons.py

# Sensitivity analysis: vary weights and measure score variance
python src/evaluation/sensitivity.py

# Temporal stability: week-to-week score correlation
python src/evaluation/stability.py
```

---

## 8. CI/CD

Tests run automatically on every push via GitHub Actions.
See `.github/workflows/` for the workflow configuration.


