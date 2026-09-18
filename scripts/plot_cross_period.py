"""Three review figures from safe aggregate CSVs only; no dataset reads."""
import csv
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.local/t4_cross_period/plot-cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,dates as mdates,font_manager,ticker


def run():
    folder=ROOT/'reports/cross_period';dest=folder/'figures';dest.mkdir(exist_ok=False)
    def read(name):
        with (folder/name).open() as f:return list(csv.DictReader(f))
    daily=read('daily_metrics.csv');flags=read('anomaly_flags.csv');fridays=read('friday_comparisons.csv');coverage=read('category_coverage.csv')
    font=next((x for x in ('Arial Unicode MS','PingFang HK','Songti SC') if x in {f.name for f in font_manager.fontManager.ttflist}),None)
    if not font:raise RuntimeError('No existing Chinese font')
    plt.rcParams.update({'font.family':font,'font.size':10,'axes.unicode_minus':False})
    checks=[]
    def base(title,axes=1):
        fig,ax=plt.subplots(axes,1,figsize=(12,7),squeeze=False);fig.subplots_adjust(left=.11,right=.96,top=.83,bottom=.17,hspace=.43)
        fig.suptitle(title,x=.075,y=.96,ha='left',fontsize=17)
        fig.text(.075,.90,'2019年10–11月 UTC ｜ 同一5%目标概率用户哈希规则，含11月新出现的合格ID',fontsize=10)
        fig.text(.075,.065,'日志观测金额，非平台财务收入；回顾性比较不确认业务故障或原因。',fontsize=9)
        return fig,ax[:,0]
    def line(ax,x,y,**kwargs):
        artist=ax.plot(x,y,**kwargs)[0]
        actual=list(artist.get_ydata());assert len(actual)==len(y) and all(a==b or math.isnan(a) and math.isnan(b) for a,b in zip(actual,y))
        checks.append({'label':kwargs.get('label'),'points':len(y),'pass':True})
        return artist
    def save(fig,name):fig.savefig(dest/name,dpi=150);plt.close(fig)
    fig,axs=base('10月25日后：恢复与重复下降须放在完整日趋势中判断');ax=axs[0]
    x=[date.fromisoformat(r['utc_date']) for r in daily]
    line(ax,x,[float(r['purchase_amount']) if r['purchase_amount'] else float('nan') for r in daily],label='每日观测金额',color='#245b78')
    usable=[r for r in flags if r['median_amount']]
    line(ax,[date.fromisoformat(r['utc_date']) for r in usable],[float(r['median_amount']) for r in usable],label='当日之前同星期检测中位数',color='#b46f14',linestyle='--')
    hits=[r for r in flags if r['candidate']=='True'];ax.scatter([date.fromisoformat(r['utc_date']) for r in hits],[float(r['current_amount']) for r in hits],color='#ae384b',label='固定规则候选',zorder=5)
    ax.axvline(date(2019,10,25),color='#888',linestyle=':');ax.set_ylim(bottom=0);ax.set_ylabel('观测金额（原price单位）');ax.legend(fontsize=9);ax.grid(alpha=.2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'));fig.text(.075,.115,'来源：daily_metrics.csv / anomaly_flags.csv；21天历史不足，缺失不补零。',fontsize=9)
    save(fig,'amount_trend.png')
    fig,axs=base('全部周五：品类自身变化与大盘差异分开看',2)
    values={key:[r for r in fridays if r['category_key']==key] for key in ('category:electronics','category:computers')}
    friday_days=[r['utc_date'] for r in values['category:electronics']]
    lookup={r['utc_date']:r for r in daily};xs=[date.fromisoformat(d) for d in friday_days]
    line(axs[0],xs,[float(lookup[d]['purchase_amount']) for d in friday_days],label='总体',color='#666',marker='o')
    for key,color in [('category:electronics','#245b78'),('category:computers','#ae384b')]:
        rows=values[key]
        line(axs[0],xs,[float(r['current_amount']) for r in rows],label=key.split(':')[1],color=color,marker='o')
        comparable=[r for r in rows if r['excess_change_pp']]
        line(axs[1],[date.fromisoformat(r['utc_date']) for r in comparable],[float(r['excess_change_pp']) for r in comparable],label=key.split(':')[1],color=color,marker='o')
    axs[0].set_ylabel('观测金额（原price单位）');axs[1].axhline(0,color='#aaa',linestyle=':');axs[1].set_ylabel('相对大盘变化差（百分点）')
    for ax in axs:
        ax.legend(fontsize=9);ax.grid(alpha=.2);ax.set_xticks(xs);ax.set_xlim(xs[0],xs[-1]);ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    fig.text(.075,.115,'下图：各品类变化减总体变化；均用各当日前同组历史日均。不是因果或价格弹性。',fontsize=9)
    save(fig,'friday_categories.png')
    fig,axs=base('unknown：金额和份额分别展示，避免将分母变化误判成编码问题',2)
    line(axs[0],x,[float(r['unknown_purchase_amount']) for r in coverage],label='unknown金额',color='#b46f14');axs[0].set_ylabel('观测金额');axs[0].set_ylim(bottom=0)
    line(axs[1],x,[1-float(r['known_purchase_amount_coverage']) if r['known_purchase_amount_coverage'] else float('nan') for r in coverage],label='unknown金额份额',color='#b46f14');axs[1].set_ylabel('占当日总观测金额');axs[1].yaxis.set_major_formatter(ticker.PercentFormatter(1));axs[1].set_ylim(bottom=0)
    for ax in axs:ax.grid(alpha=.2);ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    fig.text(.075,.115,'来源：category_coverage.csv；11/15分母为0，份额留空；份额变化不单独证明编码丢失。',fontsize=9)
    save(fig,'unknown_coverage.png')
    receipt={'status':'passed','checks':checks,'matplotlib':matplotlib.__version__,
             'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.glob('*.png')}}
    with (ROOT/'.local/t4_cross_period/plot_validation.json').open('x') as f:json.dump(receipt,f,indent=2)

if __name__=='__main__':run()
