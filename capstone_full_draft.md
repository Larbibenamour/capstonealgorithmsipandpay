# Sip&Pay Waiter Performance Scoring: Integrated Capstone Full Draft

Table of contents: 1. Executive Summary, 2. Problem and Motivation, 3. Prior Art and Research Question, 4. Main Contribution, 5. Methodology, 6. Technical Content and Key Results, 7. Limitations and Robustness, 8. Conclusions, Implications, and Application to the Real World, References.

## 1. Executive Summary
Nightlife venues run on time pressure, queue pressure, and constant operational noise. Sip&Pay already captures large volumes of transaction and workflow data through digital ordering and payment logs, yet managers still face a practical gap: how to evaluate waiter performance fairly when the most obvious timing variable, cycle time, is contaminated by factors outside waiter control. A raw ranking based on “shortest completion time” sounds simple, but it can punish waiters who handled harder orders, worked under thinner staffing, or served during heavier kitchen load.

This capstone addresses that gap by designing and implementing an interpretable waiter scoring algorithm that uses only fields currently available in operational logs. The score is expressed on a 0–100 scale and is built from three components: complexity-adjusted efficiency, throughput, and consistency. Scores are normalized inside comparable operating contexts and then adjusted through confidence-weighted shrinkage to reduce small-sample distortion. The implementation is modular, testable, and reproducible. It includes core scoring modules, evaluation scripts, and an automated unit-test suite.

The objective is explicit. Build a performance scoring function that is fair in relative peer comparison, transparent to non-technical managers, and grounded in measurable quantities instead of subjective ratings. This draft also tests whether the implementation behaves as intended through script-based analysis and formal tests. Where results are incomplete, that is stated directly.

Originality comes from the integration and constraint-aware design, not from packaging generic metrics. The contribution combines: (1) a formal fairness setup based on within-period comparison groups, (2) complexity and workload adjustment under real data limitations, (3) confidence modeling and shrinkage logic for reliability control, and (4) a full implementation path from data ingestion to exported score artifacts. The reader should expect clear formulas, traceable code evidence, concrete run outputs, and an honest boundary between what has been validated and what still needs redesign before field deployment.

## 2. Problem and Motivation
Performance management in nightlife service is rarely neutral. One bad metric can change incentives fast. If a venue tracks only raw speed, staff start optimizing for easy tickets and quick closures, not necessarily for accurate service or high-quality handoff. If management relies only on informal impressions, bias creeps in. Neither option is acceptable in a data-rich platform context.

The technical issue starts with observability. Sip&Pay logs order acceptance and order completion events, item-level quantities, and staffing snapshots. It does not log kitchen-complete timestamps, delivery-to-customer timestamps, or direct customer satisfaction markers linked to each order event. This means observed cycle time includes multiple latent processes. A waiter can look “slow” because the kitchen was saturated. Another can look “fast” because they handled low-complexity orders during high staffing coverage. In plain terms, raw cycle time is a mixed signal.

That mixed signal creates three direct risks in operations:
1. Unfair ranking and coaching decisions.
2. Misaligned incentives that reward low-complexity cherry-picking.
3. Low trust in analytics products when staff see obvious context errors.

The discipline link is straightforward. This is an algorithms-and-data-analysis problem under partial observability. The work sits at the intersection of performance measurement, applied statistics, data engineering, and software architecture. It is not a “dashboard cosmetics” project. The central challenge is to formalize comparison logic that controls confounding as much as possible with the fields that actually exist.

A second motivation is deployment realism. Venue managers need scores they can question and understand. Black-box models can produce high predictive fit in some contexts, but if managers cannot audit feature influence or explain score movement after a shift, adoption drops. A transparent formula-based pipeline with configuration controls is often more useful operationally than a hard-to-interpret predictive stack, especially during early rollout.

A third motivation is accountability. Performance scores can influence scheduling, bonuses, and professional development. That makes design details ethical details. The system needs explicit constraints, explicit uncertainty signaling, and explicit warnings about misuse. In this project, confidence is not decorative metadata; it is a core part of the score governance logic.

The practical target, then, is specific: produce a scoring system that can compare waiters fairly within shared conditions, reflect workload complexity, down-weight unstable small samples, and provide component-level interpretability for managers. If any one of those parts fails, the system becomes harder to defend in real operations. That is why the methodology, implementation, and evaluation are treated as one connected pipeline rather than isolated deliverables.

## 3. Prior Art and Research Question
### 3.1 Introduction and Scope
Research in hospitality technology has converged around three major intervention types: digital ordering interfaces (especially QR-based), digital and prepaid payment systems, and real-time operational management with analytics layers. The evidence base is broad in restaurants and hotels, less direct in nightlife venues. The central question across studies is consistent: do these technologies improve speed, service consistency, and business outcomes, and under which tradeoffs?

The reviewed literature focuses on effects that transfer to bars, restaurants, and nightclub service contexts where throughput and transaction reliability are operational priorities. It also surfaces recurring limitations: context specificity, reliance on self-reported perceptions, and weak integration analysis across full digital service stacks.

### 3.2 Digital Menus and QR-Code Ordering
Digital menus and QR ordering have been widely studied since contactless service adoption accelerated. Operationally, the main observed gain is reduced friction at ordering entry points. Nilsson et al. (2021) report that self-service ordering can reduce delays associated with menu access and order placement, while reducing front-of-house transcription errors. Ru and Garg (2023), in a study of luxury restaurants in Xi’an, report positive customer acceptance linked to convenience and perceived efficiency, with implications for table turnover and labor burden.

Customer-experience findings are mixed but mostly favorable when implementation quality is high. Beldona et al. (2014) report stronger user perceptions of information quality and ordering satisfaction with electronic menu formats compared to paper menus. Şahin et al. (2025) report improved perceived service quality and customer satisfaction in QR-menu settings, including resilience of effects under perceived risk considerations.

The tradeoff appears where hospitality identity depends on personal interaction. Nilsson et al. (2021) and Xu et al. (2024) highlight that self-service systems can reduce human contact, which some guest segments interpret negatively. Usability barriers also remain for less tech-comfortable users and in poor connectivity settings. So the evidence does not support a simplistic “QR always improves service quality” claim. It supports a conditional claim: QR systems can improve speed and process quality when user design, assistance pathways, and service tone are managed actively.

### 3.3 Digital and Prepaid Payment Systems
Digital payment literature aligns with ordering literature on process compression. Kimes (2008) discusses technology’s role in shortening dining-cycle stages and improving operational throughput. Mobile wallets, app payments, and QR checkout paths reduce waiting at bill settlement and reduce manual handling overhead.

Behavioral adoption studies provide detail on why customers switch. Lew et al. (2020), using an extended TAM setup, find that perceived usefulness, ease of use, and enjoyment significantly increase intention to adopt mobile wallet payment in restaurant contexts. Their model explains around 61% of variance in intention, which signals strong explanatory power for adoption behavior in the studied sample.

Operational implications include lower cash-handling load, stronger transaction traceability, and better revenue capture. Yet the same literature points to implementation frictions: outage risk, setup and transaction costs, security concerns among some users, and staff training load (Kimes, 2008; Lew et al., 2020). In nightlife, where transaction peaks can be extreme, failure modes at payment points are operationally expensive. The value proposition is clear, but fallback design remains essential.

### 3.4 Real-Time Order Management and RMS Integration
The RMS and order-routing literature addresses a different layer: coordination and execution control once orders enter the system. Memiş Kocaman (2021), in survey-based analysis of restaurant staff, reports positive perceived effects of RMS adoption on operational coordination, error reduction, and sales support, with stronger impact in larger or chain settings. That scale effect matters for nightlife operations where load variability can be high and process complexity rises quickly with volume.

The mechanism is practical. Digitally routed orders reduce lost-ticket events, reduce manual communication overhead, and provide clearer state tracking between front and back of house. Kimes (2008) also links technology-enabled process control to service acceleration and labor efficiency gains. At the same time, technology does not remove physical bottlenecks such as kitchen or bar production capacity. RMS improves coordination; it does not create production headroom on its own.

Adoption barriers include software/hardware cost, workflow transition resistance, and uneven staff digital readiness (Memiş Kocaman, 2021). For smaller independent venues, ROI can be uncertain if transaction volume does not justify system overhead. So again, effectiveness is context-dependent rather than universal.

### 3.5 Analytics Dashboards and Data-Driven Decisions
The next step beyond transaction digitization is decision digitization. Analytics dashboards aggregate sales, feedback, and operational indicators into manager-facing views for staffing, inventory, and promotional decisions. Carneiro et al. (2023) report that stronger analytics adoption in hospitality settings is associated with stronger business outcomes, including financial and retention indicators. Fernandes et al. (2021) show how combined sales-plus-review dashboards can shorten managerial decision cycles in restaurant settings.

The nightlife relevance is direct: dynamic demand, high variance by hour, and event-sensitive behavior make real-time decision support attractive. A manager who sees demand compression in near real-time can act on staffing or service routing while the shift is still recoverable.

The caution appears in outcome balance. Xu et al. (2024) report that digital ordering adoption can increase revenue through turnover effects while simultaneously correlating with lower customer satisfaction in some conditions. That result matters because it breaks the false equivalence between speed and service quality. Performance systems focused only on efficiency can drift away from hospitality outcomes if not bounded by interpretation rules.

### 3.6 Synthesis and Discussion
Table 1 consolidates the dominant findings across cited studies.

Table 1. Comparative Summary of Prior Studies

| Study | Context | Technology focus | Method | Reported benefit | Limitation pattern |
|---|---|---|---|---|---|
| Beldona et al. (2014) | Restaurant service | Electronic menus | Comparative user study | Better perceived information quality and ordering satisfaction | Context and interface dependence |
| Nilsson et al. (2021) | Casual dining | Self-service ordering | Empirical service analysis | Faster order flow, lower communication error | Human-interaction tradeoff |
| Ru & Garg (2023) | Luxury restaurants (Xi’an) | QR menu ordering | Survey + acceptance model | Convenience and turnover-related operational gains | Single-context scope |
| Şahin et al. (2025) | Casual dining | Sustainable QR menus | Empirical perception model | Higher perceived service quality and satisfaction | Still perception-centered |
| Kimes (2008) | Hospitality operations | Tech in revenue/service management | Conceptual + applied analysis | Faster service stages, labor efficiency | Requires cost-benefit discipline |
| Lew et al. (2020) | Restaurant consumers | Mobile wallet payment | Extended TAM | Strong adoption drivers, high explanatory power | Intention not always behavior |
| Memiş Kocaman (2021) | Restaurant operations | RMS usage | Staff survey | Better coordination and fewer errors, stronger in larger venues | Cross-sectional self-report |
| Fernandes et al. (2021) | Multi-restaurant case | Analytics dashboard | Data integration + manager evaluation | Faster decisions, clearer operational visibility | Small-scale case context |
| Xu et al. (2024) | Restaurant chain | Mobile app ordering/payment | Transaction + review analysis | Revenue gains with possible satisfaction decline | Generalizability constraints |

The synthesis supports four claims.

First, digital service technologies can improve speed and process control in many hospitality contexts.
Second, customer and staff acceptance depends on usability and local workflow fit.
Third, efficiency gains do not automatically imply better perceived service quality.
Fourth, literature still under-covers integrated, nightlife-specific, operationally grounded evaluation.

### 3.7 Gaps in the Literature and Research Objective
Two gaps remain central.

Gap 1: Nightlife-specific empirical evidence is thin compared with general restaurant and hotel contexts, despite clear differences in crowd density, ambient conditions, and purchase timing.

Gap 2: Most studies isolate one intervention (ordering, payment, or analytics) instead of testing end-to-end integrated workflows over time. This leaves open questions about system-level interactions and sustained effects.

The project objective follows directly:

Design and implement an integrated, interpretable waiter performance scoring algorithm for nightlife operational logs that controls for workload complexity and staffing context, quantifies reliability, and supports reproducible evaluation.

The guiding research question is:

Given observable operational variables only, how can a waiter scoring function be constructed so that scores are fair in peer comparison, transparent in composition, and reliable enough for practical operational interpretation?

## 4. Main Contribution
I designed and implemented a full scoring pipeline that converts Sip&Pay operational logs into complexity-adjusted waiter performance scores with confidence-weighted shrinkage, inside comparison groups built for fairness under shared service conditions. The added value is a deployable, auditable architecture that links formal scoring logic to testable code, with explicit reliability signaling and explicit boundaries on what the score can and cannot claim.

## 5. Methodology
### 5.1 Formal Problem Statement
Let:
- `W` be the set of waiter work sessions evaluated for performance.
- `V` be the observed platform variables, including order timestamps, assigned waiter IDs, item quantities, shift/session identifiers, and staffing counts by time bucket.

Define a scoring function:
`f: W -> [0,100]`

such that, for each waiter session, the score:
1. reflects relative performance under comparable operating conditions,
2. adjusts for order complexity and workload context,
3. remains interpretable through explicit components and weights,
4. carries a reliability estimate that can dampen unstable small-sample outcomes.

Because kitchen-complete and delivery timestamps are not recorded, `f` is a relative performance estimator, not an absolute waiter-speed estimator.

### 5.2 Methodological Overview
The project uses a quantitative algorithm-design approach with empirical evaluation scripts. Quantitative means all inputs are measured operational variables from platform logs, not interviews or subjective ratings. Algorithm-design means the core contribution is an explicit, formula-defined scoring procedure with configurable parameters and reproducible execution steps.

The measurement constraint drives the entire design. Observed cycle time (`order_completed_ts - order_accepted_ts`) mixes kitchen and waiter effects. To reduce confounding, comparisons are localized to waiter peer groups who worked in overlapping venue-time windows. This “within-period” normalization is the fairness anchor.

### 5.3 Data Sources and Constraints
The dataset consists of operational log structures:
- `order_accepted_ts`
- `order_completed_ts`
- `assigned_waiter_id`
- item-level order content (`item_id`, `quantity`, optional category)
- `waiter_shift_id`
- staff clock logs / staffing interval counts
- `venue_time_period_id` when available, or generated from overlap clustering

Missing variables include:
- kitchen-complete timestamp
- delivery-to-customer timestamp
- direct customer satisfaction marker tied to each order
- actor identity for completion click events

Methodological implication: absolute delivery speed attribution is not possible from current fields. The score must be interpreted as relative performance under shared operating context, not as a causal measure of waiter-only speed.

### 5.4 Comparison Unit Construction
Waiters do not necessarily share identical shift IDs even when they serve together. Fair comparison therefore uses venue-time overlap groups. If `venue_time_period_id` is not supplied, shifts are clustered when overlap exceeds a minimum threshold (configured at two hours). Orders inherit this grouping via waiter-shift linkage.

This is essential. A waiter should not be ranked against someone from a different operating window with different kitchen pressure and staffing density.

### 5.5 Data Cleaning and Validation Rules
All transformations are implemented in Python with Pydantic schema checks. Core cleaning rules are:
- Remove or flag orders with non-positive cycle time.
- Exclude records missing required timestamps.
- Handle missing item lists via exclusion or epsilon fallback based on configuration.
- Enforce epsilon floor for complexity to avoid undefined division.

The goal is deterministic behavior under noisy operational inputs.

### 5.6 Feature Engineering
The pipeline computes:
1. **Cycle time**
   `cycle_time_seconds = completed_ts - accepted_ts`
2. **Order complexity**
   `complexity = sum(quantity_i * weight_i)`
   Default item weight is `1.0`.
3. **Raw efficiency**
   `eff_raw = cycle_time_seconds / max(complexity, epsilon)`
4. **Workload intensity adjustment**
   Using staffing buckets and period median staffing:
   `adjustment_factor = active_waiters / median_staffing`
   `eff_raw_adjusted = eff_raw * adjustment_factor`
5. **Waiter-level aggregation**
   - median adjusted efficiency
   - throughput (`total_complexity / active_hours`)
   - dispersion (`IQR` and related normalized variant)
6. **Consistency proxy**
   `consistency_raw = 1 / (1 + normalized_dispersion)`

These features balance speed, volume, and stability instead of over-focusing on any one dimension.

### 5.7 Scoring Algorithm
Within each comparison group, metrics are converted to percentile-based component scores:
- Efficiency: lower adjusted raw values score higher.
- Throughput: higher values score higher.
- Consistency: higher values score higher.

Composite score:
`Score_raw = 0.50*S_eff + 0.30*S_thr + 0.20*S_cons`

Efficiency is weighted highest because it most directly approximates operational effectiveness under the available data structure. Throughput captures handled volume. Consistency penalizes volatility.

### 5.8 Confidence and Shrinkage
Confidence has three parts:
- sample-size confidence (`C_sample`)
- complexity-volume confidence (`C_complexity`)
- stability confidence (`C_stability`)

Corrected overall confidence (weights sum to 1):
`C = 0.4*C_sample + 0.3*C_complexity + 0.3*C_stability`

This correction removes a previous weighting inconsistency and ensures mathematically valid confidence blending.

Shrinkage then adjusts low-confidence scores toward the group median:
`Score_final = C_eff*Score_raw + (1 - C_eff)*Median_group`
where `C_eff` is derived from confidence and shrinkage strength.

High-confidence scores move little. Low-confidence outliers are pulled back.

### 5.9 Temporal Aggregation
Period-level reporting (weekly/monthly) uses complexity-weighted averaging:
`Score_period = sum(Score_shift * Complexity_shift) / sum(Complexity_shift)`

Outlier capping is applied by winsorization. Low-confidence periods (`confidence < 0.3`) are excluded from aggregation.

This avoids letting one noisy shift dominate multi-period summaries.

### 5.10 Implementation Architecture
The codebase is organized into:
- `src/scoring/` for schema, feature extraction, normalization, confidence, orchestration, and aggregation
- `src/data/mock_data.py` for synthetic generation
- `src/evaluation/` for EDA, comparisons, sensitivity, stability
- `tests/` for unit-test coverage of core scoring logic

Primary interface (cleaned signature):
```python
def compute_scores(
    orders_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    staffing_df: pd.DataFrame,
    config: dict
) -> dict[str | int, dict[str | int, dict]]:
    ...
```

Output shape:
`{group_id: {waiter_id: {score, confidence, components, metrics}}}`

### 5.11 Evaluation Framework and Formal Metric Definitions
Evaluation framework includes:
1. Exploratory data analysis.
2. Naive-vs-adjusted ranking comparison.
3. Ablation checks.
4. Parameter sensitivity sweeps.
5. Temporal stability analysis.
6. Confidence monotonicity tests.

Formal definitions used in evaluation:
- Pearson correlation:
  `r = cov(X, Y) / (std(X)*std(Y))`
- Coefficient of variation per waiter:
  `CV = std(weekly_scores) / mean(weekly_scores)`
- Rank inversion rate:
  `R_inv = |{w : |rank_adj(w) - rank_naive(w)| >= 2}| / |W|`

These formulas are used to define success criteria and diagnose behavior.

### 5.12 Real Data vs Synthetic Data Plan
Development, testing, and executed analyses in this draft are synthetic-data based. Synthetic generation uses fixed random seeds for reproducibility. Real operational log evaluation is planned but not executed in the reported runs here. Because of that, all performance conclusions in this draft refer to algorithm behavior under synthetic conditions.

### 5.13 Dataflow and Logic Diagrams
[FIGURE 1 — Dataflow diagram from raw orders, shifts, and staffing logs through cleaning, feature extraction, normalization, confidence scoring, shrinkage, and JSON export.]
[Source: figures/dataflow_pipeline.png — ADD THIS IMAGE]

Figure 1 should be read as the execution map of the system. It clarifies sequencing and module boundaries.

[FIGURE 2 — Scoring logic flowchart showing branch points for workload adjustment mode, low-confidence handling, and temporal aggregation filtering.]
[Source: figures/scoring_logic_flowchart.png — ADD THIS IMAGE]

Figure 2 should make decision logic explicit for reviewers who need algorithm transparency without reading full source files.

### 5.14 Implementation Timeline
**Table 2. Implementation Timeline**

| Phase | Activity | Intended period | Status |
|---|---|---|---|
| Phase 1 | Core schema + complexity + feature modules | Early build cycle | Completed |
| Phase 2 | Normalization, confidence, shrinkage, aggregation modules | Mid build cycle | Completed |
| Phase 3 | Unit tests and CI workflow setup | Mid build cycle | Completed |
| Phase 4 | Evaluation scripts (EDA, comparison, sensitivity, stability) | Late build cycle | Completed with analytical gaps |
| Phase 5 | Real-log integration and end-to-end aggregation validation | Next cycle | In progress |

Table 2 is interpreted as a progression from core algorithm correctness to evaluation maturity. The current gap is not missing code volume. It is consistency between scoring outputs and downstream analysis assumptions.

## 6. Technical Content and Key Results
### 6.1 Repository-Traceable Implementation Evidence
The implementation in `src/scoring/score_shift.py` orchestrates the full scoring path from parsed input records to final nested outputs. It computes per-order efficiency, applies staffing adjustment, aggregates waiter metrics, normalizes components within groups, builds composite scores, computes confidence, applies shrinkage, and exports structured results.

A key fragment from `score_shift.py`:
```python
scores_df["composite_score"] = scores_df.apply(
    lambda row: normalize.compute_composite_score(
        row["efficiency_score"], row["throughput_score"], row["consistency_score"], config.weights
    ),
    axis=1,
)

scores_df["confidence"] = scores_df.apply(
    lambda row: conf_module.compute_overall_confidence(
        n_orders=int(row["n_orders"]),
        total_complexity=float(row["total_complexity"]),
        normalized_dispersion=float(row.get("normalized_dispersion", 0.0)),
        config=config.dict() if hasattr(config, "dict") else config,
    ),
    axis=1,
)
```

This fragment matters because it links scored components and confidence in one deterministic table before shrinkage. The final score is not produced by one opaque function; it is assembled in visible stages.

A core complexity function from `src/scoring/complexity.py`:
```python
def compute_order_complexity(order, item_weights, default_weight=1.0):
    complexity = 0.0
    for item in order.items:
        weight = item_weights.get(item.item_id, default_weight)
        complexity += item.quantity * weight
    return max(complexity, 0.0)
```

This keeps workload accounting explicit. Every order’s complexity can be reconstructed from item quantities and configured weights.

A confidence fragment from `src/scoring/confidence.py`:
```python
if weights is None:
    weights = {"sample_size": 0.4, "complexity": 0.3, "stability": 0.3}
weight_sum = sum(weights.values())
if not (0.99 <= weight_sum <= 1.01):
    raise ValueError(...)
```

This enforces valid confidence blending and prevents silent misuse.

### 6.2 Input Generation and Run Configuration
The executable demonstration script `scripts/example_usage.py` generated:
- `989` orders
- `20` shifts
- fixed seed `42`
- default weights `0.50/0.30/0.20`
- workload mode `"multiplicative"`
- shrinkage strength `0.3`

This script exports `shift_scores.json` and attempts weekly aggregation.

Interpretation: the pipeline is operational from input generation to score export, and run settings are explicit and reproducible.

### 6.3 Unit Test Results
`pytest tests/` execution produced:
- `47 passed`, `0 failed`
- warnings related to Pydantic `.dict()` deprecation in one call path
- statement coverage total `48%`

Coverage highlights:
- strong coverage in core scoring modules (`complexity`, `normalize`, major parts of `aggregate`, `score_shift`)
- `0%` coverage in evaluation scripts (`src/evaluation/*`)
- `0%` coverage in `venue_periods.py`

Interpretation: the scoring core is exercised by formal tests, but script-level analytics and group-construction utilities need direct test coverage before claiming full analytical reliability.

### 6.4 EDA Output Results
Running `src/evaluation/eda.py` produced:
- dataset size: 473 orders, 10 shifts, 320 staffing buckets
- cycle time mean: 1310.9s (21.8 min)
- cycle time median: 1191.3s (19.9 min)
- cycle time range: 369.4s to 3292.9s
- complexity mean: 4.86 units
- complexity median: 5.00 units
- complexity–cycle-time Pearson correlation: 0.599

Interpretation: the synthetic generator produces realistic spread and a positive complexity-time relationship. That is useful for stressing complexity adjustment logic. It does not validate field behavior by itself.

### 6.5 Naive vs Adjusted Comparison Results
Running `src/evaluation/comparisons.py` produced:
- total comparisons: 158
- rank inversions (threshold >=2 positions): 0 (0.0%)
- mean absolute rank change: NaN
- largest improvement/decline: NaN

Interpretation: NaN values indicate alignment failure in the comparison DataFrame, not a trustworthy “no difference” finding. The script currently does not produce usable inversion statistics for this run configuration.

### 6.6 Sensitivity Analysis Results
Running `src/evaluation/sensitivity.py` produced:
- efficiency weight sweep mean score range: 40.00
- throughput weight sweep mean score range: 28.00
- consistency weight sweep mean score range: 12.50
- shrinkage impact low/high-confidence std: both 0.00 in this run
- workload method comparison mean absolute difference: 0.00, correlation: NaN
- NumPy runtime warning during correlation computation

Interpretation: score sensitivity to component weights is visible and large, especially through efficiency weighting. At the same time, NaN correlation and zero-difference patterns suggest degenerate downstream score structure in this run, so interpretation must stay conservative.

### 6.7 Temporal Stability Results
Running `src/evaluation/stability.py` produced:
- “No data available for temporal analysis.”

Interpretation: weekly aggregation output is empty under this output key structure, so week-to-week stability metrics are currently unavailable.

### 6.8 Exported Score Artifact Diagnostics
The exported `shift_scores.json` (after example script run) contains:
- 160 records keyed by waiter-shift style IDs
- score min/max/mean/median: 50.0 / 50.0 / 50.0 / 50.0
- confidence min/max/mean/median: 0.372 / 0.770 / 0.593 / 0.597
- order-count range per record: 1 to 15
- total complexity range: 3.0 to 80.0
- 17 records with confidence below 0.5

Interpretation: confidence varies with evidence as designed, but score collapse at 50.0 means peer-comparison structure is not producing discriminative outcomes in this execution path. This is the central technical issue in current results.

### 6.9 Why the 50.0 Collapse Happens in Current Runs
The scoring logic normalizes metrics within each group. In current outputs, each record often behaves like a one-waiter group, which creates neutralized composite behavior through percentile mechanics. Efficiency inversion and throughput/consistency ranks collapse into a fixed weighted combination that resolves to 50.0 in this setup.

This is not an abstract warning. It appears in exported artifacts and in script outputs.

### 6.10 Missing Visual Outputs and Required Placeholders
No charts are currently stored in a project `figures/` or `outputs/` directory. The report includes placeholders to enforce visual integration and interpretation requirements.

[FIGURE 3 — Distribution of confidence values from `shift_scores.json` with bins and low-confidence threshold marker at 0.5.]
[Source: outputs/confidence_distribution.png — ADD THIS IMAGE]

Figure 3 should confirm that reliability estimates are not flat even when final scores are flat.

[FIGURE 4 — Rank-change histogram from naive vs adjusted comparison, including missing-data/NaN handling indicator.]
[Source: outputs/rank_change_histogram.png — ADD THIS IMAGE]

Figure 4 should make the analytical failure visible instead of hiding it behind a single summary line.

[FIGURE 5 — Weekly aggregation diagnostic plot showing zero generated waiter-week combinations.]
[Source: outputs/weekly_aggregation_diagnostic.png — ADD THIS IMAGE]

Figure 5 should directly show where temporal analysis currently breaks.

### 6.11 Technical Section Summary
The repository shows clear algorithm design, modular implementation, and passing core tests. It also shows present analytical fragility in end-to-end reporting due to grouping and key consistency issues. Both are part of the technical result set and are reported here with direct output evidence.

## 7. Limitations and Robustness
The first limitation is structural: key consistency across scoring, comparison, and aggregation layers is not stable in current runs. Scoring outputs are generated, but downstream scripts expecting specific shift alignment produce NaN metrics or empty aggregations. This is the main reason temporal and inversion claims are currently weak.

The second limitation is data regime. All executed analyses in this draft are synthetic. Synthetic runs are useful for deterministic testing and edge-case injection, but they cannot replace validation on actual operational logs with real staffing variation, real shift overlap complexity, and real completion behavior noise.

The third limitation is observability boundary. Missing kitchen-complete and delivery timestamps prevent direct waiter-only speed attribution. The score is relative and context-controlled, not causal proof of individual service speed or customer experience quality.

The fourth limitation is analytical test coverage. Evaluation scripts and period-construction utilities are not currently covered by automated tests. Core component tests pass, but report-level metrics still need script-level correctness safeguards.

The fifth limitation is credit assignment granularity. The codebase includes an interface for split-order credit in future versions, but MVP behavior still assigns 100% order credit to one waiter. In real team-service patterns, this can distort attribution.

Robustness mechanisms that are already in place include:
- strict schema and timestamp validation,
- weight-sum validation in configuration and confidence blending,
- bounded score clipping to [0,100],
- winsorization in aggregation logic,
- confidence thresholding for long-term summaries,
- monotonic confidence checks in tests.

These protections are meaningful. Still, they do not compensate for key-alignment faults in report-level aggregation. The boundaries of this study are clear: algorithm core mechanics are implemented and tested; end-to-end managerial reporting requires one more hardening cycle before practical rollout.

## 8. Conclusions, Implications, and Application to the Real World
The project set two main goals: build a fair and interpretable waiter scoring algorithm under real logging constraints, and demonstrate that implementation behavior can be validated with reproducible evidence. The first goal is substantially achieved at the design and module level. The second is only partially achieved in end-to-end analysis outputs.

What is working today:
- a complete scoring architecture exists in code,
- component computations are explicit and test-backed,
- confidence modeling and shrinkage are integrated,
- synthetic evaluation scripts run reproducibly.

What is not yet working at the same maturity level:
- discriminative final scoring in current exported run artifacts,
- stable naive-vs-adjusted rank analysis,
- temporal aggregation outputs for week-level stability analysis.

Real-world applicability is still strong if interpreted correctly. The system is close to being useful for operational coaching, peer-context interpretation, and reliability-aware performance monitoring. But deployment should wait until key harmonization is fixed across scoring outputs and evaluation pipelines. Rolling this into managerial decisions before that fix would risk false neutrality and low trust.

If I started this project again, I would redesign one thing first: enforce a single canonical comparison key contract from ingestion through export (`venue_time_period_id` plus explicit waiter identifier), then make script execution fail hard when that contract is broken. That would have prevented the current mismatch where component logic is fine but reporting outputs degenerate.

Tradeoffs I would revisit:
1. I would accept slower early prototyping in exchange for stricter data-contract validation between modules.
2. I would prioritize test coverage for evaluation scripts earlier, not only core scoring functions.
3. I would separate “demonstration scripts” from “evaluation scripts” more aggressively to avoid accidental mixing of assumptions.

One principle I am taking forward is concrete: in applied analytics, fairness formulas and software interfaces must be designed together. A mathematically clean scoring equation can still produce poor decisions if IDs, grouping, and aggregation semantics drift across modules. The reliability of the whole pipeline is set by that integration discipline.

## References
Beldona, S., Buchanan, N., & Miller, B. (2014). Exploring the promise of e-tablet restaurant menus. *International Journal of Contemporary Hospitality Management, 26*(3), 367-382. https://doi.org/10.1108/IJCHM-01-2013-0039

Carneiro, T., Picoto, W. N., & Pinto, I. (2023). Big data analytics and firm performance in the hotel sector. *Tourism and Hospitality, 4*(2), 244-256. https://doi.org/10.3390/tourhosp4020015

Fernandes, E., Moro, S., Cortez, P., Batista, F., & Ribeiro, R. (2021). A data-driven approach to measure restaurant performance by combining online reviews with historical sales data. *International Journal of Hospitality Management, 94*, 102830. https://doi.org/10.1016/j.ijhm.2020.102830

Iskender, A., Sirakaya-Turk, E., & Cardenas, D. (2023). Restaurant menus and COVID-19: Implications for technology adoption in the post-pandemic era. *Consumer Behavior in Tourism and Hospitality, 18*(4), 587-605. https://doi.org/10.1108/CBTH-11-2022-0194

Kimes, S. E. (2008). The role of technology in restaurant revenue management. *Cornell Hospitality Quarterly, 49*(3), 297-309. https://doi.org/10.1177/1938965508322768

Lew, S., Tan, G. W.-H., Loh, X.-M., Hew, J. J., & Ooi, K.-B. (2020). The disruptive mobile wallet in the hospitality industry: An extended mobile technology acceptance model. *Technology in Society, 63*, 101430. https://doi.org/10.1016/j.techsoc.2020.101430

Memiş Kocaman, E. (2021). Operational effects of using restaurant management system: An assessment according to business features. *International Journal of Gastronomy and Food Science, 25*, 100408. https://doi.org/10.1016/j.ijgfs.2021.100408

Nilsson, E., Pers, J., & Grubbström, L. (2021). Self-service technology in casual dining restaurants. *Services Marketing Quarterly, 42*(1-2), 57-73. https://doi.org/10.1080/15332969.2021.1947085

Ru, X., & Garg, A. (2023). Customer acceptance of QR menu ordering system in luxury restaurants: A study of Xi’an, China. *Asia-Pacific Journal of Innovation in Hospitality and Tourism, 12*(2), 77-96. https://doi.org/10.7603/s40930-023-0021-5

Şahin, E., Güneri, B., & Demir, M. Ö. (2025). The impact of sustainable QR menus on service quality and customer satisfaction: The moderating role of perceived risk. *Sustainability, 17*(5), 2323. https://doi.org/10.3390/su17052323

Xu, Y., Liu, X., Mao, Z., & Zhou, J. (2024). Mobile food ordering apps, restaurant performance, and customer satisfaction. *Cornell Hospitality Quarterly, 65*(1), 345-367. https://doi.org/10.1177/19389655231223376
