"""Reproducible MES dataset for the Northstar Motion Systems portfolio case study."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
SEED = 42


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    lines = pd.DataFrame([
        ['L01', 'Assembly North', 2016, '2025-04-01', 1.04, 37],
        ['L02', 'Assembly South', 2018, '2025-07-01', 1.00, 34],
        ['L03', 'Assembly East', 2015, '', 1.08, 40],
        ['L04', 'Assembly West', 2020, '', .97, 31],
    ], columns=['line_id', 'line_name', 'commission_year', 'automation_date',
                'cycle_multiplier', 'base_power_kw'])
    products = pd.DataFrame([
        ['P100', 'Standard valve actuator', 20.0, 9.5],
        ['P200', 'Precision valve actuator', 28.0, 15.0],
        ['P300', 'Heavy duty valve actuator', 36.0, 22.0],
    ], columns=['product_id', 'product_name', 'base_ideal_cycle_sec', 'scrap_cost_usd'])
    rows, events = [], []
    # Latent wear persists across shifts and is reset by scheduled maintenance.
    wear = {line: .1 for line in lines.line_id}
    for day in pd.date_range('2024-01-01', '2025-12-31'):
        # Shutdowns and all Sundays are excluded from the production schedule.
        if day.weekday() == 6 or (day.month == 12 and day.day >= 24) or (day.month == 1 and day.day == 1):
            continue
        ambient = 23 + 7*np.sin(2*np.pi*(day.dayofyear-110)/365.25) + rng.normal(0, 1.8)
        demand = 1 + .14*np.sin(2*np.pi*(day.dayofyear-40)/365.25) + .08*(day.year-2024)
        if day.weekday() == 5 and rng.random() > .5 + .8*(demand-1):
            continue
        supply_shock = pd.Timestamp('2024-09-09') <= day <= pd.Timestamp('2024-09-27')
        for line in lines.itertuples(index=False):
            maintenance = day.day <= 7 and day.weekday() == 0
            wear[line.line_id] = .08 if maintenance else min(1.8, wear[line.line_id]+rng.uniform(.015, .035))
            upgrade_day = pd.Timestamp(line.automation_date) if line.automation_date else None
            age = (day-upgrade_day).days if upgrade_day is not None else -999
            # Commissioning disruption, followed by six-week learning curve.
            learning = float(np.clip((age-14)/42, 0, 1)) if age >= 0 else 0
            commissioning = 0 <= age < 14
            for shift in (1, 2, 3):
                if day.weekday() == 5 and shift == 3:
                    continue
                sid = f'{day:%Y%m%d}-{line.line_id}-{shift}'
                p_precision = .25 + .13*(day.year-2024)
                pid = rng.choice(products.product_id, p=[.8-p_precision, p_precision, .2])
                product = products.set_index('product_id').loc[pid]
                ideal = round(product.base_ideal_cycle_sec*line.cycle_multiplier, 3)
                planned = 450 - (90 if maintenance and shift == 1 else 0)
                stop_specs = [('Changeover', float(rng.gamma(3, 5)))]
                if rng.random() < .24 + .17*wear[line.line_id]:
                    stop_specs.append(('Mechanical', float(rng.lognormal(3.15, .7))))
                if rng.random() < .36*(1-.55*learning) + .3*commissioning:
                    stop_specs.append(('Sensor fault', float(rng.gamma(2, 7))))
                if rng.random() < (.48 if supply_shock else .09):
                    stop_specs.append(('Material shortage', float(rng.gamma(2, 14))))
                if commissioning:
                    stop_specs.append(('Commissioning', float(rng.gamma(3, 9))))
                if ambient > 29 and rng.random() < .23:
                    stop_specs.append(('Overheat', float(rng.gamma(2, 8))))
                scale = min(1., (planned-30)/sum(v for _, v in stop_specs))
                stop_specs = [(reason, round(value*scale, 2)) for reason, value in stop_specs]
                downtime = round(sum(value for _, value in stop_specs), 2)
                runtime = round(planned-downtime, 2)
                performance = float(np.clip(.87 + .045*learning - .018*(shift==3)
                    -.018*wear[line.line_id] -.025*commissioning + rng.normal(0, .027), .60, .98))
                total = int(runtime*60/ideal*performance)
                temperature = round(ambient+17+4*wear[line.line_id]+rng.normal(0, 1.8), 2)
                vibration = round(max(.2, 1.3+1.5*wear[line.line_id]+rng.normal(0, .35)), 3)
                reject_rate = float(np.clip(.013+.008*(pid=='P200')+.007*(shift==3)
                    +.0018*max(0, temperature-48)+.009*wear[line.line_id]
                    -.008*learning+.012*commissioning+rng.normal(0, .003), .002, .15))
                rejected = int(rng.binomial(total, reject_rate))
                # kWh = baseline while stopped plus load-dependent run energy.
                energy = round((runtime*line.base_power_kw*(1+.1*(pid=='P300'))
                    + downtime*line.base_power_kw*.24)/60*rng.uniform(.96, 1.04), 2)
                rows.append([sid, day.date().isoformat(), line.line_id, shift, pid,
                    '2025-12-31T23:00:00', planned, downtime, total, total-rejected,
                    rejected, temperature, vibration, energy, ideal])
                for seq, (reason, duration) in enumerate(stop_specs, 1):
                    events.append([f'{sid}-E{seq:02}', sid, reason, duration])
    cols = ['shift_id', 'production_date', 'line_id', 'shift', 'product_id', 'exported_at',
        'planned_minutes', 'downtime_minutes', 'total_units', 'good_units', 'reject_units',
        'temperature_c', 'vibration_mm_s', 'energy_kwh', 'ideal_cycle_sec']
    df = pd.DataFrame(rows, columns=cols)
    # Raw export imperfections are deterministic and isolated to non-overlapping rows.
    indices = rng.permutation(len(df))
    df.loc[indices[:120], 'line_id'] = df.loc[indices[:120], 'line_id'].str.lower().map(lambda x: f' {x} ')
    df.loc[indices[120:220], 'product_id'] = df.loc[indices[120:220], 'product_id'].str.lower()
    df.loc[indices[220:310], 'temperature_c'] = np.nan
    df.loc[indices[310:355], 'vibration_mm_s'] = np.nan
    df.loc[indices[355:367], 'total_units'] = -10
    df.loc[indices[367:375], 'downtime_minutes'] = 999
    df.loc[indices[375:381], 'production_date'] = '2025-02-30'
    # Late export is authoritative; stale copies have the same values except metadata.
    copies = df.loc[indices[400:470]].copy()
    copies['exported_at'] = '2025-12-30T23:00:00'
    raw = pd.concat([df, copies], ignore_index=True).sample(frac=1, random_state=SEED)
    raw.to_csv(RAW/'production_shifts.csv', index=False)
    pd.DataFrame(events, columns=['event_id', 'shift_id', 'reason', 'duration_minutes']).to_csv(RAW/'downtime_events.csv', index=False)
    lines.to_csv(RAW/'lines.csv', index=False)
    products.to_csv(RAW/'products.csv', index=False)
    manifest = {'seed': SEED, 'scheduled_shift_count': len(df), 'raw_shift_rows': len(raw),
        'event_rows': len(events), 'duplicate_rows': 70, 'invalid_unique_shifts': 26,
        'missing_temperature': 90, 'missing_vibration': 45,
        'period': ['2024-01-01', '2025-12-31']}
    (ROOT/'data'/'generation_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
