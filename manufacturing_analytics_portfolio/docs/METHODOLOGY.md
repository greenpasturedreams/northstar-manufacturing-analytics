# Scenario, assumptions and project design

## Decision to support

Northstar Motion Systems' plant operations manager must decide which production losses to investigate and whether the initial automation rollout warrants a controlled expansion. The analyst delivers a clean SQL model, operating KPI trends, ranked downtime causes, product-adjusted comparisons and a reproducible report.

Questions:

1. How do availability, speed and first-pass quality change over time?
2. Which stop categories consume the most production time?
3. Do upgraded lines improve more than comparison lines after commissioning?
4. Does the night-shift reject gap remain when comparing the same product?
5. How do equipment temperature and product mix relate to quality and energy intensity?

## Data design and assumptions

The dataset design combines production scheduling, equipment condition, product mix and automation maturity. Numerical assumptions and distributions are documented below so the data can be reproduced and its analytical limits understood. KPI definitions follow [Vorne's OEE calculation guide](https://www.oee.com/calculating-oee/).

The generator is the complete source of truth. It uses seed 42 and a fixed 2024–2025 window. NumPy and pandas versions are pinned for repeatability. Each shift has one product: this is an explicit simplification of batch manufacturing.

| Mechanism | Implementation | Expected analytical signal |
|---|---|---|
| Operating calendar | Three eight-hour weekday shifts, 30 minutes of breaks; no Sundays, January 1 or December 24–31; probabilistic Saturday shifts 1–2 | Variable monthly capacity and seasonality in units |
| Demand proxy | Annual sine wave and +8% 2025 scheduling pressure affect Saturday opening probability | Capacity utilization changes, rather than an independent order table |
| Product mix | Precision product share rises from 25% to 38% in 2025; heavy duty remains 20% | Slower average cycles and higher rejects can mask efficiency gains |
| Maintenance | First Monday of each month: 90 minutes outside planned time for shift 1; latent wear reset | A repeating sawtooth in condition and loss risk |
| Serial dependence | Wear persists by line, grows daily and increases failure probability and reject risk | Nearby shifts are not statistically independent |
| Stop durations | Gamma-distributed changeovers/sensor/material/commissioning stops; lognormal mechanical stops | Right-skewed downtime with occasional large losses |
| Summer conditions | Ambient annual temperature cycle plus noise influences equipment temperature; heat stops above 29°C ambient | Seasonal temperature/quality association |
| Supply disruption | September 9–27, 2024: material-stop probability rises from 9% to 48% | Temporary plant-wide loss of availability |
| Automation | L01 April 1 and L02 July 1, 2025; 14 days of disruption and 42 further learning days | Initial OEE dip, then fewer sensor stops, better speed and yield |
| Night shift | 1.8 percentage point performance penalty and 0.7 percentage point higher reject probability | Product-stratified shift gap; no claim about real staff |
| Energy | Running load by line/product and stopped load at 24% of running power, plus noise | Energy intensity depends on cycle time, losses and mix |

At full maturity, the generator adds 4.5 percentage points to the *performance driver*, reduces the sensor-stop probability multiplier by 55%, and subtracts 0.8 percentage points from reject probability. These are data-generation parameters, not estimated treatment effects. Counts are obtained from available runtime and fixed ideal cycles, then binomial rejects are drawn. Good units plus rejects always equals total units in the latent data. Summed rounded stop durations define downtime; runtime plus downtime equals planned time. Stops are proportionally scaled only when their total would leave less than 30 minutes of runtime. Performance is bounded between 60% and 98% to avoid physically impossible output.

Wear and ambient temperature are latent generator variables, not extra observed columns. Vibration is an observable proxy for wear. Maintenance work orders, supplier batches, customer orders, labor hours, rework, price changes, detailed defect types, event timestamps and overlapping failures are outside scope. Commission year is metadata; line differences enter through cycle multipliers and power. No validated ROI can be computed without investment costs and incremental contribution margins.

## Deliberate raw data problems

Non-overlapping selections of unique shifts receive:

- 120 line labels with lowercase and surrounding spaces; 100 lowercase product labels.
- 90 missing temperatures and 45 missing vibration readings, selected randomly rather than as failure-driven outages.
- 12 negative total counts, 8 downtime values exceeding planned time, 6 impossible dates.
- 70 older re-export copies appended and the raw rows shuffled. The export timestamps are batch metadata for two snapshots, not realistic shift-level ingestion timestamps.

SQL normalizes labels, retains the latest export by shift ID, and quarantines 26 invalid unique shifts. Missing sensor readings remain null and receive flags; they do not invalidate production KPIs. No outliers are removed merely for being extreme. Events belonging to quarantined shifts are excluded from analytical events and counted in the audit. Because exclusions remove production time, comparisons use the valid-record population and disclose coverage.

The Python import boundary preserves strings and validates numeric syntax and integer-valued counts before SQLite casting. Malformed nonnumeric text aborts loading with a file/row error; known numeric business-rule violations go to SQL quarantine. This avoids SQLite silently casting arbitrary text to zero. SQL remains the owner of standardization, deduplication, business validation, joins and KPI calculations. Master dimensions are trusted generator outputs and checked for uniqueness. The pipeline is designed for the included files; it is not a general-purpose ingestion service.

## Comparison and uncertainty

The descriptive automation comparison uses January–March 2025 as baseline and September–November 2025 as follow-up. Both treated lines are mature in the follow-up window. Untreated L03/L04 use the same calendar windows. The reported difference-in-differences is `(treated post − treated pre) − (control post − control pre)` in OEE percentage points, using planned-time-weighted rates.

This is not causal evidence: assignment is not randomized, only four lines exist, product mix changes, heat is seasonal, and errors are serially dependent. Inspect pre-rollout line trends and compare line × product × shift strata before making an investment decision. Do not attach naive shift-level significance tests or confidence intervals as if thousands of shifts were independent experiments. A future real-world pilot should collect capital and operating costs, define comparable controls and dates in advance, and evaluate at the line or appropriately clustered time level.

The temperature association is also descriptive: wear affects both temperature and rejects, while night shift and product mix affect quality. A bar chart does not isolate heat's effect. Energy comparisons are shown within product, but remaining line and scheduling differences still matter.

## Suggested portfolio workflow

1. Define the manager's decision, grain, metrics and exclusions using this document.
2. Read the raw CSVs and data dictionary, then run the generator to reproduce the source files.
3. Inspect duplicate IDs and missing readings. Read and run the cleaning SQL through the loader.
4. Inspect `rejected_shifts` and `reports/validation.json`. Confirm time/count/event reconciliation.
5. Run the seven analytical queries and six charts. Investigate mix, denominator and calendar effects.
6. Read the generated README and connect each finding to its chart and suggested operational check.
7. Publish the repository with raw CSVs, SQL, scripts, documentation and figures. Retain the opening project description and connect each finding to its supporting evidence.

For an interview, explain why quarantining invalid production shifts is preferable to inventing missing output, why downtime joins can duplicate production totals, why mixed-cycle OEE needs time weighting, and why an improvement after automation is insufficient evidence of causation.
