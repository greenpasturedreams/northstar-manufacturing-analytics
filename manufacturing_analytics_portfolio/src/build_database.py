"""Load preserved CSV strings, run SQL, validate and export analysis-ready data."""
from pathlib import Path
import csv
import json
import math
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_text(conn, filename, table):
    with (ROOT/'data'/'raw'/filename).open(newline='', encoding='utf-8') as handle:
        reader = csv.reader(handle)
        cols = next(reader)
        # Headers are controlled by this repository, never arbitrary SQL input.
        conn.execute(f'DROP TABLE IF EXISTS {table}')
        conn.execute(f'CREATE TABLE {table} (source_row INTEGER, '+', '.join(f'"{c}" TEXT' for c in cols)+')')
        records = list(reader)
        numeric = {'shift','planned_minutes','downtime_minutes','total_units','good_units',
                   'reject_units','temperature_c','vibration_mm_s','energy_kwh','ideal_cycle_sec','duration_minutes'}
        integers = {'shift','total_units','good_units','reject_units'}
        for i,row in enumerate(records,1):
            if len(row)!=len(cols):
                raise ValueError(f'{filename}:{i+1}: wrong column count')
            for col,value in zip(cols,row):
                if col in numeric and value.strip():
                    number=float(value)
                    if not math.isfinite(number) or (col in integers and not number.is_integer()):
                        raise ValueError(f'{filename}:{i+1}: invalid numeric value in {col}')
        conn.executemany(f'INSERT INTO {table} VALUES ('+','.join('?' for _ in range(len(cols)+1))+')',
                         ((i, *row) for i, row in enumerate(records, 1)))


def main():
    out = ROOT/'data'/'processed'
    out.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ROOT/'data'/'manufacturing.db') as conn:
        for name, table in [('production_shifts.csv', 'raw_production_shifts'),
                            ('downtime_events.csv', 'raw_downtime_events')]:
            load_text(conn, name, table)
        # Dimensions are generated as clean master data, with unique primary keys checked below.
        for name in ('lines', 'products'):
            pd.read_csv(ROOT/'data'/'raw'/f'{name}.csv').to_sql(name, conn, if_exists='replace', index=False)
        conn.executescript((ROOT/'sql'/'01_clean_transform.sql').read_text())
        def scalar(sql):
            return conn.execute(sql).fetchone()[0]
        manifest = json.loads((ROOT/'data'/'generation_manifest.json').read_text())
        counts = {t: scalar(f'SELECT COUNT(*) FROM {t}') for t in
                  ['raw_production_shifts','staged_shifts','clean_shifts','rejected_shifts','raw_downtime_events','clean_events']}
        assert counts['raw_production_shifts']-counts['staged_shifts']==manifest['duplicate_rows']
        assert counts['rejected_shifts']==manifest['invalid_unique_shifts']
        assert counts['clean_shifts']+counts['rejected_shifts']==manifest['scheduled_shift_count']
        assert scalar('SELECT COUNT(*) FROM lines')==scalar('SELECT COUNT(DISTINCT line_id) FROM lines')==4
        assert scalar('SELECT COUNT(*) FROM products')==scalar('SELECT COUNT(DISTINCT product_id) FROM products')==3
        assert scalar('SELECT COUNT(*) FROM clean_shifts WHERE good_units+reject_units<>total_units')==0
        assert scalar('SELECT COUNT(*) FROM clean_shifts WHERE oee NOT BETWEEN 0 AND 1 OR performance NOT BETWEEN 0 AND 1 OR quality NOT BETWEEN 0 AND 1')==0
        assert scalar('SELECT COUNT(*) FROM clean_shifts WHERE ABS(oee-availability*performance*quality)>1e-10')==0
        assert scalar('SELECT COUNT(*) FROM clean_shifts WHERE ABS(runtime_minutes+downtime_minutes-planned_minutes)>1e-8')==0
        assert scalar('SELECT COUNT(*) FROM clean_shifts WHERE temperature_c IS NULL')==manifest['missing_temperature']
        assert scalar('SELECT COUNT(*) FROM clean_shifts WHERE vibration_mm_s IS NULL')==manifest['missing_vibration']
        assert scalar('''SELECT COUNT(*) FROM clean_shifts s LEFT JOIN
          (SELECT shift_id,SUM(duration_minutes) duration FROM clean_events GROUP BY 1) e USING(shift_id)
          WHERE e.duration IS NULL OR ABS(e.duration-s.downtime_minutes)>.011''')==0
        assert scalar('SELECT COUNT(*) FROM clean_events e LEFT JOIN clean_shifts s USING(shift_id) WHERE s.shift_id IS NULL')==0
        # Validate direct OEE independently, including heterogeneous product cycle times.
        clean = pd.read_sql_query('SELECT * FROM clean_shifts',conn)
        direct = (clean.good_units*clean.ideal_cycle_sec).sum()/60/clean.planned_minutes.sum()
        monthly = pd.read_sql_query('SELECT * FROM monthly_kpis', conn)
        assert abs(direct-clean.ideal_good_minutes.sum()/clean.planned_minutes.sum())<1e-12
        assert ((monthly.availability*monthly.performance*monthly.time_weighted_quality-monthly.oee).abs()<1e-12).all()
        # Execute every analysis query and save results by number.
        query=''
        i=0
        for line in (ROOT/'sql'/'02_analysis.sql').read_text().splitlines(keepends=True):
            query+=line
            if sqlite3.complete_statement(query):
                i+=1
                pd.read_sql_query(query,conn).to_csv(out/f'analysis_{i:02}.csv',index=False)
                query=''
        assert i==7
        for table in ('clean_shifts','clean_events','rejected_shifts','monthly_kpis','line_month_kpis'):
            pd.read_sql_query(f'SELECT * FROM {table}',conn).to_csv(out/f'{table}.csv',index=False)
        counts['events_excluded_with_invalid_parent'] = scalar('''SELECT COUNT(*) FROM raw_downtime_events e
            JOIN rejected_shifts s ON e.shift_id=s.shift_id''')
        counts['temperature_missing'] = int(clean.temperature_c.isna().sum())
        counts['vibration_missing'] = int(clean.vibration_mm_s.isna().sum())
        counts['checks_passed'] = True
        counts['plant_oee'] = direct
        (ROOT/'reports'/'validation.json').parent.mkdir(exist_ok=True)
        (ROOT/'reports'/'validation.json').write_text(json.dumps(counts,indent=2)+'\n')
        print(json.dumps(counts,indent=2))


if __name__=='__main__':
    main()
