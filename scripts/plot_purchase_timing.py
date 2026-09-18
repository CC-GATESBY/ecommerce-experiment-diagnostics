"""Two bounded hourly figures from reviewed aggregate CSV, never raw records."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.local/purchase_timing/plot-cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, dates as mdates, font_manager


def run():
    folder=ROOT/'reports/purchase_timing'; destination=folder/'figures';destination.mkdir(exist_ok=False)
    with (folder/'hourly.csv').open() as stream: rows=list(csv.DictReader(stream))
    font=next((name for name in ('Arial Unicode MS','PingFang HK','Songti SC') if name in {f.name for f in font_manager.fontManager.ttflist}),None)
    if not font:raise RuntimeError('Existing Chinese font required')
    plt.rcParams.update({'font.family':font,'font.size':10,'axes.unicode_minus':False})
    checks=[]
    for identity,label in [('full_source','公开源全部用户'),('fixed_user_sample','固定5%目标概率用户样本')]:
        selected=[r for r in rows if r['identity']==identity]
        assert len(selected)==120 and all(r['scan_status']=='complete' for r in selected)
        x=[datetime.fromisoformat(r['utc_hour'].replace('Z','+00:00')) for r in selected]
        fig,axes=plt.subplots(4,1,figsize=(11,9),sharex=True)
        fig.subplots_adjust(left=.14,right=.97,top=.86,bottom=.16,hspace=.18)
        fig.suptitle(label+'：5天购买与浏览、加购的时间形态',x=.08,y=.965,ha='left',fontsize=17)
        fig.text(.08,.915,'2019-11-14 至 11-18 UTC，每小时观测；各行纵轴独立，金额为日志price和',fontsize=10)
        for ax,field,title,color in zip(axes,('view','cart','purchase','purchase_amount'),('view事件数','cart事件数','purchase事件数','观测购买金额'),('#607d8b','#b8871b','#a93c45','#245b78')):
            y=[float(r[field]) for r in selected]
            line=ax.plot(x,y,color=color,linewidth=1.6)[0]
            assert list(line.get_ydata())==y
            checks.append(dict(identity=identity,field=field,points=len(y),pass_check=True))
            ax.axvspan(datetime(2019,11,15,tzinfo=timezone.utc),datetime(2019,11,16,tzinfo=timezone.utc),color='#cccccc',alpha=.23)
            ax.set_ylabel(title);ax.set_ylim(bottom=0);ax.grid(alpha=.2)
            ax.ticklabel_format(axis='y',style='plain',useOffset=False)
        axes[-1].xaxis.set_major_locator(mdates.DayLocator(tz=timezone.utc))
        axes[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=[12],tz=timezone.utc))
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d',tz=timezone.utc))
        axes[-1].set_xlabel('UTC日期（灰色区域为11月15日；不是当地作息）')
        fig.text(.08,.065,'来源：purchase_timing/hourly.csv；event_time不能证明入库/补发时间，未删除重复候选。',fontsize=9)
        fig.savefig(destination/(identity+'_hourly.png'),dpi=140);plt.close(fig)
    receipt=dict(status='passed',aggregate_sha256=hashlib.sha256((folder/'hourly.csv').read_bytes()).hexdigest(),checks=checks,
                 figures={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.glob('*.png')})
    with (ROOT/'.local/purchase_timing/plot_validation.json').open('x') as stream:json.dump(receipt,stream,indent=2)

if __name__=='__main__':run()
