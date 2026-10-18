-- 1. Plant trend. Aggregate numerators/denominators, never average shift percentages.
SELECT * FROM monthly_kpis ORDER BY month;

-- 2. Downtime Pareto with cumulative share (unrounded for downstream charts).
WITH causes AS (
 SELECT reason,SUM(duration_minutes) minutes FROM clean_events GROUP BY reason
)
SELECT reason,minutes,minutes/SUM(minutes) OVER() share,
 SUM(minutes) OVER(ORDER BY minutes DESC,reason ROWS UNBOUNDED PRECEDING)
 /SUM(minutes) OVER() cumulative_share FROM causes ORDER BY minutes DESC,reason;

-- 3. Shift quality within product; avoids raw comparisons across product mix.
SELECT product_id,shift,COUNT(*) shifts,SUM(total_units) units,
 SUM(reject_units)*1.0/SUM(total_units) reject_rate,
 SUM(ideal_good_minutes)/SUM(planned_minutes) oee
FROM clean_shifts GROUP BY product_id,shift ORDER BY product_id,shift;

-- 4. Automation comparison in common calendar windows, with both upgrades mature.
-- Jan-Mar 2025 baseline vs Sep-Nov 2025 follow-up. Controls never upgraded.
-- Descriptive difference-in-differences in OEE percentage points. Not a causal estimate.
WITH periods AS (
 SELECT *,CASE WHEN line_id IN ('L01','L02') THEN 'Treated' ELSE 'Control' END cohort,
 CASE WHEN production_date BETWEEN '2025-01-01' AND '2025-03-31' THEN 'Pre'
      WHEN production_date BETWEEN '2025-09-01' AND '2025-11-30' THEN 'Post' END period
 FROM clean_shifts
), rates AS (
 SELECT cohort,period,COUNT(*) shifts,
 SUM(ideal_good_minutes)/SUM(planned_minutes) oee
 FROM periods WHERE period IS NOT NULL GROUP BY cohort,period
), changes AS (
 SELECT cohort,MAX(CASE WHEN period='Pre' THEN oee END) pre_oee,
 MAX(CASE WHEN period='Post' THEN oee END) post_oee FROM rates GROUP BY cohort
)
SELECT *,100*(post_oee-pre_oee) change_pp,
 100*((SELECT post_oee-pre_oee FROM changes WHERE cohort='Treated')-
      (SELECT post_oee-pre_oee FROM changes WHERE cohort='Control')) descriptive_did_pp
FROM changes;

-- 5. Temperature association with rejects. Missing readings remain a separate group.
SELECT CASE WHEN temperature_c IS NULL THEN 'Missing'
 WHEN temperature_c<45 THEN '<45 C' WHEN temperature_c<50 THEN '45-49.9 C'
 WHEN temperature_c<55 THEN '50-54.9 C' ELSE '55+ C' END temperature_band,
 COUNT(*) shifts,SUM(total_units) units,
 SUM(reject_units)*1.0/SUM(total_units) reject_rate
FROM clean_shifts GROUP BY 1;

-- 6. Energy intensity by product and automation phase (product mix matters).
SELECT line_id,product_id,automation_phase,COUNT(*) shifts,
 SUM(energy_kwh)/SUM(good_units) kwh_per_good_unit
FROM clean_shifts GROUP BY 1,2,3 ORDER BY 1,2,3;

-- 7. Quarantine audit. Events excluded because their parent was invalid are counted separately.
SELECT rejection_reason,COUNT(*) rows FROM rejected_shifts GROUP BY 1;
