# Data dictionary

All records describe Northstar Motion Systems' valve actuator production. Dates are production dates in local plant time; shift 3 belongs to the date its shift begins. No personal information is included. All costs are assumed USD costs, not market quotes.

## Raw tables and joins

`production_shifts.csv`: one export version of one date × line × shift. A shift runs one product only. `shift_id` is the business key; `exported_at` distinguishes re-exports. The canonical dataset contains 6,516 scheduled shifts; raw data adds 70 older copies. There are no rows for unscheduled shifts.

| Column | Type / unit | Meaning |
|---|---|---|
| shift_id | text | `YYYYMMDD-Lxx-shift`; unique after latest-export selection |
| production_date | ISO date | Scheduled production day, 2024–2025 |
| line_id | text FK | L01–L04; trim and uppercase before joining |
| shift | integer | 1: 06:00–14:00; 2: 14:00–22:00; 3: 22:00–06:00 next day |
| product_id | text FK | P100, P200 or P300 |
| exported_at | ISO timestamp | Export batch timestamp; not event/ingestion time |
| planned_minutes | minutes | 480 minus 30 minutes of breaks; minus 90 scheduled maintenance minutes on applicable shifts |
| downtime_minutes | minutes | Sum of all recorded stops during planned production time, including changeover |
| total_units | integer units | First-pass processed units, including rejects |
| good_units | integer units | First-pass accepted units; no rework recovery included |
| reject_units | integer units | Rejected units; all treated as scrapped in this model |
| temperature_c | degrees C | Shift mean equipment temperature; not ambient temperature |
| vibration_mm_s | mm/s | Shift mean vibration indicator; not a certified diagnostic measurement |
| energy_kwh | kWh | Shift electricity use during planned production time; includes stopped idle consumption |
| ideal_cycle_sec | seconds/unit | Product base cycle × line multiplier; does not change after automation |

`downtime_events.csv`: one non-overlapping stop episode within a shift. Join many events to one shift through `shift_id`. Events contain no timestamps; duration can be reconciled but sequencing cannot be analyzed.

| Column | Type / unit | Meaning |
|---|---|---|
| event_id | text PK | Shift ID plus event sequence |
| shift_id | text FK | Parent scheduled production shift |
| reason | category | Changeover, Mechanical, Sensor fault, Material shortage, Commissioning, Overheat |
| duration_minutes | minutes | Stop duration, rounded to 0.01 minutes |

`lines.csv`: one line; primary key `line_id`.

| Column | Meaning |
|---|---|
| line_id / line_name | Stable identifier / assembly line label |
| commission_year | Installation year; descriptive metadata, not an independent causal driver |
| automation_date | Upgrade start: L01 April 1, 2025; L02 July 1, 2025; blank for L03/L04 |
| cycle_multiplier | Fixed ideal-cycle adjustment: 1.04, 1.00, 1.08, 0.97 for L01–L04 |
| base_power_kw | Baseline running power assumption: 37, 34, 40, 31 kW |

`products.csv`: one product; primary key `product_id`.

| Column | Meaning |
|---|---|
| product_id / product_name | P100 Standard, P200 Precision, P300 Heavy duty valve actuators |
| base_ideal_cycle_sec | Best attainable cycle assumption: 20, 28, 36 seconds respectively |
| scrap_cost_usd | Assumed loss per rejected unit: $9.50, $15.00, $22.00 respectively; excludes downtime and overhead |

## SQL outputs

`clean_shifts` retains standardized source fields, a null `rejection_reason`, and these derived fields:

| Column | Definition |
|---|---|
| runtime_minutes | planned_minutes − downtime_minutes |
| ideal_total_minutes | total_units × ideal_cycle_sec / 60 |
| ideal_good_minutes | good_units × ideal_cycle_sec / 60 |
| availability | runtime_minutes / planned_minutes |
| performance | ideal_total_minutes / runtime_minutes |
| quality | good_units / total_units (first-pass yield) |
| oee | ideal_good_minutes / planned_minutes; equals availability × performance × quality at this grain |
| kwh_per_good_unit | energy_kwh / good_units |
| scrap_cost_usd | reject_units × product scrap cost |
| automation_phase | Control (never upgraded), Before, Ramp-up (first 56 days), Mature |
| temperature_missing / vibration_missing | 1 if the original reading is absent, otherwise 0 |

`monthly_kpis`: one plant month. Rates use sums of their numerators and denominators. `time_weighted_quality` = sum(ideal_good_minutes) / sum(ideal_total_minutes). With mixed cycle times, availability × performance × **time_weighted_quality** reconciles to aggregate OEE; multiplying by ordinary unit yield generally does not. Unit yield is still reported as `quality` for operational interpretation. `shifts` counts valid records, not all scheduled shifts.

`line_month_kpis`: one line × month; OEE, reject rate, energy intensity. `clean_events`: valid stop episodes attached to valid shifts. `rejected_shifts`: latest exports that fail validation, including a rejection reason; no imputation. `staged_shifts` and `evaluated_shifts` remain queryable in SQLite for auditing. `source_row` is the loader's 1-based raw row number and breaks tied export timestamps deterministically.

## Aggregation cautions

- Never sum production units after a raw join to downtime events: this multiplies production by the number of stops. Aggregate events by shift first or analyze events separately.
- Never average shift OEE, shift reject percentages or shift energy intensity when denominators differ.
- Good-unit totals reflect scheduled hours and product mix as well as efficiency. They are not a demand forecast.
- These are shift averages. They cannot identify individual failure precursors, operator behavior or within-shift temperature spikes.
