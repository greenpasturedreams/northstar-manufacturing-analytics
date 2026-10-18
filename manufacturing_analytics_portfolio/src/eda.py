"""Build six publication-ready EDA figures from SQL outputs; no hidden calculations."""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd
import numpy as np

OUT = ROOT/'reports'/'figures'
COLORS = ['#167D9A','#D78D24','#7355A6','#498457']


def save(fig, name):
    fig.text(.01,.008,'Northstar Motion Systems • Production performance • 2024–2025',fontsize=8,color='#53616E')
    fig.tight_layout(rect=[0,.035,1,.96])
    fig.savefig(OUT/name,dpi=160,facecolor='white')
    plt.close(fig)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'axes.titleweight':'bold','axes.labelcolor':'#334155',
        'axes.grid':True,'grid.alpha':.16,'figure.titlesize':16})
    source=ROOT/'data'/'processed'
    monthly=pd.read_csv(source/'monthly_kpis.csv')
    monthly['month']=pd.to_datetime(monthly.month)
    clean=pd.read_csv(source/'clean_shifts.csv')
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
    fig.suptitle('Plant performance improves, with visible operating disruptions')
    for metric,color in zip(['availability','performance','quality','oee'],COLORS):
        label={'quality':'First-pass yield','oee':'OEE'}.get(metric,metric.title())
        axes[0].plot(monthly.month,monthly[metric],label=label,color=color,marker='o',ms=3)
    axes[0].yaxis.set_major_formatter(PercentFormatter(1)); axes[0].set_ylabel('Aggregated operating rate')
    axes[0].legend(ncol=4,loc='center',bbox_to_anchor=(.5,-.11),fontsize=9,frameon=False)
    axes[1].bar(monthly.month,monthly.good_units/1e6,width=21,color=COLORS[0])
    axes[1].set_ylabel('Good units (millions)')
    axes[1].set_xlabel('Production month')
    for ax in axes:
        ax.axvspan(pd.Timestamp('2024-09-01'),pd.Timestamp('2024-09-30'),color=COLORS[1],alpha=.14)
    axes[0].set_title('Shaded month: September 2024 material supply disruption',fontsize=10,loc='left')
    save(fig,'01_monthly_performance.png')

    pareto=pd.read_csv(source/'analysis_02.csv')
    fig,ax=plt.subplots(figsize=(10,5.8))
    ax.bar(pareto.reason,pareto.minutes/60,color=COLORS[0]); ax.set_ylabel('Downtime (hours)')
    ax.tick_params(axis='x',rotation=18)
    right=ax.twinx(); right.plot(pareto.reason,pareto.cumulative_share,color=COLORS[1],marker='o')
    right.set_ylim(0,1.08); right.yaxis.set_major_formatter(PercentFormatter(1));right.set_ylabel('Cumulative share')
    right.grid(False);ax.set_title('Prioritize the largest sources of lost production time',pad=15)
    save(fig,'02_downtime_pareto.png')

    lm=pd.read_csv(source/'line_month_kpis.csv')
    fig,ax=plt.subplots(figsize=(11,5.5))
    for (line,group),color in zip(lm.groupby('line_id'),COLORS):
        ax.plot(pd.to_datetime(group.month),group.oee,label=line,color=color,marker='o',ms=3)
    for date,label,color,y in [('2025-04-01','L01 rollout',COLORS[0],.72),('2025-07-01','L02 rollout',COLORS[1],.715)]:
        ax.axvline(pd.Timestamp(date),ls='--',color=color,alpha=.7)
        ax.text(pd.Timestamp(date),y,label,color=color,ha='left',fontsize=9)
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylim(.71,.88)
    ax.set_ylabel('Time-weighted OEE');ax.legend(ncol=4,loc='upper left')
    ax.set_title('Automation rollout: short ramp-up, then sustained improvement',pad=15)
    save(fig,'03_automation_trend.png')

    quality=pd.read_csv(source/'analysis_03.csv')
    fig,ax=plt.subplots(figsize=(9,5.2))
    x=np.arange(3);width=.24
    for j,(shift,g) in enumerate(quality.groupby('shift')):
        g=g.set_index('product_id').reindex(['P100','P200','P300'])
        ax.bar(x+(j-1)*width,g.reject_rate,width,color=COLORS[j],label=f'Shift {shift}')
    ax.set_xticks(x,['P100 Standard','P200 Precision','P300 Heavy duty'])
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylabel('Rejected units / total units')
    ax.set_title('Night-shift quality gap persists within each product',pad=15);ax.legend()
    save(fig,'04_quality_by_shift.png')

    temp=pd.read_csv(source/'analysis_05.csv').set_index('temperature_band').reindex(['<45 C','45-49.9 C','50-54.9 C','55+ C','Missing'])
    fig,ax=plt.subplots(figsize=(9,5.2))
    bars=ax.bar(temp.index,temp.reject_rate,color=COLORS[0]);ax.set_ylim(0,temp.reject_rate.max()*1.27)
    for bar,n in zip(bars,temp.shifts):
        ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.001,f'{int(n):,} shifts',ha='center',fontsize=9)
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylabel('Rejected units / total units')
    ax.set_title('Higher operating temperatures coincide with more rejects',pad=15)
    save(fig,'05_temperature_quality.png')

    clean['year']=pd.to_datetime(clean.production_date).dt.year
    energy=clean.groupby(['product_id','year'])[['energy_kwh','good_units']].sum()
    energy['intensity']=energy.energy_kwh/energy.good_units
    fig,ax=plt.subplots(figsize=(9,5.2))
    for j,year in enumerate([2024,2025]):
        g=energy.xs(year,level='year').reindex(['P100','P200','P300'])
        ax.bar(x+(j-.5)*.32,g.intensity,.32,label=str(year),color=COLORS[j])
    ax.set_xticks(x,['P100 Standard','P200 Precision','P300 Heavy duty'])
    ax.set_ylabel('kWh per good unit');ax.legend()
    ax.set_title('Compare energy intensity within products before judging progress',pad=15)
    save(fig,'06_energy_intensity.png')
    print('Saved six figures to reports/figures')


if __name__=='__main__':
    main()
