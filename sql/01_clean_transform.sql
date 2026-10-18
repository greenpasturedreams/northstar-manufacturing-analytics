-- SQLite 3.35+. Raw fields are loaded as TEXT so source representations survive.
-- Deduplicate BEFORE validation. Never substitute an older valid record for a bad latest export.
DROP TABLE IF EXISTS staged_shifts;
CREATE TABLE staged_shifts AS
WITH ranked AS (
 SELECT *, ROW_NUMBER() OVER (
   PARTITION BY TRIM(shift_id) ORDER BY exported_at DESC, source_row DESC
 ) AS export_rank FROM raw_production_shifts
)
SELECT TRIM(shift_id) AS shift_id, TRIM(production_date) AS production_date,
 UPPER(TRIM(line_id)) AS line_id, CAST(shift AS INTEGER) AS shift,
 UPPER(TRIM(product_id)) AS product_id, exported_at,
 CAST(planned_minutes AS REAL) AS planned_minutes,
 CAST(downtime_minutes AS REAL) AS downtime_minutes,
 CAST(total_units AS INTEGER) AS total_units,
 CAST(good_units AS INTEGER) AS good_units,
 CAST(reject_units AS INTEGER) AS reject_units,
 CAST(NULLIF(TRIM(temperature_c),'') AS REAL) AS temperature_c,
 CAST(NULLIF(TRIM(vibration_mm_s),'') AS REAL) AS vibration_mm_s,
 CAST(energy_kwh AS REAL) AS energy_kwh,
 CAST(ideal_cycle_sec AS REAL) AS ideal_cycle_sec
FROM ranked WHERE export_rank=1;

DROP TABLE IF EXISTS evaluated_shifts;
CREATE TABLE evaluated_shifts AS
SELECT s.*,
 CASE
 WHEN LENGTH(production_date)<>10 OR production_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
   OR DATE(production_date,'+0 days') IS NULL
   OR DATE(production_date,'+0 days')<>production_date
   OR production_date NOT BETWEEN '2024-01-01' AND '2025-12-31' THEN 'invalid_date'
 WHEN l.line_id IS NULL OR p.product_id IS NULL THEN 'unknown_dimension'
 WHEN shift NOT IN (1,2,3) OR shift IS NULL THEN 'invalid_shift'
 WHEN planned_minutes IS NULL OR planned_minutes<=0 OR planned_minutes>450
   OR downtime_minutes IS NULL OR downtime_minutes<0 OR downtime_minutes>=planned_minutes THEN 'invalid_time'
 WHEN total_units IS NULL OR good_units IS NULL OR reject_units IS NULL
   OR total_units<=0 OR good_units<0 OR reject_units<0
   OR total_units<>good_units+reject_units THEN 'invalid_counts'
 WHEN ideal_cycle_sec IS NULL OR ideal_cycle_sec<=0 OR energy_kwh IS NULL OR energy_kwh<=0 THEN 'invalid_measure'
 WHEN ABS(ideal_cycle_sec-p.base_ideal_cycle_sec*l.cycle_multiplier)>.001 THEN 'invalid_standard'
 WHEN total_units*ideal_cycle_sec/60.0>planned_minutes-downtime_minutes+.01 THEN 'performance_above_one'
 ELSE NULL END AS rejection_reason
FROM staged_shifts s LEFT JOIN lines l ON s.line_id=l.line_id
LEFT JOIN products p ON s.product_id=p.product_id;

DROP TABLE IF EXISTS rejected_shifts;
CREATE TABLE rejected_shifts AS SELECT * FROM evaluated_shifts WHERE rejection_reason IS NOT NULL;
DROP TABLE IF EXISTS clean_shifts;
CREATE TABLE clean_shifts AS
SELECT s.*, planned_minutes-downtime_minutes AS runtime_minutes,
 total_units*ideal_cycle_sec/60.0 AS ideal_total_minutes,
 good_units*ideal_cycle_sec/60.0 AS ideal_good_minutes,
 (planned_minutes-downtime_minutes)/planned_minutes AS availability,
 total_units*ideal_cycle_sec/60.0/(planned_minutes-downtime_minutes) AS performance,
 1.0*good_units/total_units AS quality,
 good_units*ideal_cycle_sec/60.0/planned_minutes AS oee,
 energy_kwh/good_units AS kwh_per_good_unit,
 reject_units*p.scrap_cost_usd AS scrap_cost_usd,
 CASE WHEN l.automation_date IS NULL THEN 'Control'
      WHEN s.production_date<l.automation_date THEN 'Before'
      WHEN s.production_date<DATE(l.automation_date,'+56 days') THEN 'Ramp-up'
      ELSE 'Mature' END AS automation_phase,
 CASE WHEN temperature_c IS NULL THEN 1 ELSE 0 END AS temperature_missing,
 CASE WHEN vibration_mm_s IS NULL THEN 1 ELSE 0 END AS vibration_missing
FROM evaluated_shifts s JOIN lines l USING(line_id) JOIN products p USING(product_id)
WHERE rejection_reason IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS clean_shift_pk ON clean_shifts(shift_id);
CREATE UNIQUE INDEX IF NOT EXISTS clean_shift_grain ON clean_shifts(production_date,line_id,shift);

-- Event cleaning is separate. Exclude children of quarantined shifts; do not join
-- one-to-many events directly onto production when summing units or OEE denominators.
DROP TABLE IF EXISTS clean_events;
CREATE TABLE clean_events AS
WITH ranked AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY TRIM(event_id) ORDER BY source_row DESC) rn
 FROM raw_downtime_events
)
SELECT TRIM(e.event_id) event_id, TRIM(e.shift_id) shift_id,
 TRIM(e.reason) reason, CAST(e.duration_minutes AS REAL) duration_minutes
FROM ranked e JOIN clean_shifts s ON TRIM(e.shift_id)=s.shift_id
WHERE rn=1 AND CAST(e.duration_minutes AS REAL)>0
 AND TRIM(e.reason) IN ('Changeover','Mechanical','Sensor fault','Material shortage','Commissioning','Overheat');
CREATE UNIQUE INDEX IF NOT EXISTS clean_event_pk ON clean_events(event_id);

DROP VIEW IF EXISTS monthly_kpis;
CREATE VIEW monthly_kpis AS
SELECT SUBSTR(production_date,1,7) month, COUNT(*) shifts,
 SUM(good_units) good_units, SUM(reject_units) reject_units,
 SUM(runtime_minutes)/SUM(planned_minutes) availability,
 SUM(ideal_total_minutes)/SUM(runtime_minutes) performance,
 1.0*SUM(good_units)/SUM(total_units) quality,
 SUM(ideal_good_minutes)/SUM(ideal_total_minutes) time_weighted_quality,
 SUM(ideal_good_minutes)/SUM(planned_minutes) oee,
 SUM(energy_kwh)/SUM(good_units) kwh_per_good_unit,
 SUM(scrap_cost_usd) scrap_cost_usd
FROM clean_shifts GROUP BY 1;

DROP VIEW IF EXISTS line_month_kpis;
CREATE VIEW line_month_kpis AS
SELECT SUBSTR(production_date,1,7) month,line_id,
 SUM(ideal_good_minutes)/SUM(planned_minutes) oee,
 SUM(reject_units)*1.0/SUM(total_units) reject_rate,
 SUM(energy_kwh)/SUM(good_units) kwh_per_good_unit
FROM clean_shifts GROUP BY 1,2;
