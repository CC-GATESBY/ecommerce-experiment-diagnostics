"""One business figure from the reviewed, anonymized decomposition only."""
import csv
import hashlib
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.local/computers_mix/plot-cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager


def run():
    source=ROOT/'reports/computers_mix/decomposition.csv'
    with source.open() as f:rows=[r for r in csv.DictReader(f) if r['target_date']=='2019-10-25']
    expected=['stable_common','stable_history_only','stable_current_only','classification_unstable']
    assert [r['part'] for r in rows]==expected
    values=[float(r['amount_difference']) for r in rows]
    names=['共同购买商品（12个）','仅历史观察到购买（93个）','仅目标日观察到购买（19个）','观察分类不稳定（0个）']
    font=next(n for n in ('Arial Unicode MS','PingFang HK','Songti SC') if n in {f.name for f in font_manager.fontManager.ttflist})
    plt.rcParams.update({'font.family':font,'font.size':11,'axes.unicode_minus':False})
    fig,ax=plt.subplots(figsize=(11,5.5));fig.subplots_adjust(left=.31,right=.96,top=.77,bottom=.23)
    fig.suptitle('computers：金额差主要落在两期购买商品组合的不同',x=.04,y=.95,ha='left',fontsize=16)
    fig.text(.04,.865,'10月25日 vs 10月4/11/18日日均；固定用户样本，全部购买记录保留',fontsize=10)
    bars=ax.barh(names,values,color=['#247a69' if x>=0 else '#b55257' for x in values]);ax.invert_yaxis()
    assert [b.get_width() for b in bars]==values
    ax.axvline(0,color='#777',linewidth=.8);ax.grid(axis='x',alpha=.2);ax.set_xlim(-23000,10500)
    for i,v in enumerate(values):ax.text(v+400 if v>=0 else v-400,i,f'{v:+,.2f}',ha='left' if v<0 else 'left',va='center',fontsize=10)
    ax.set_xlabel('观测金额差（原price单位；四项净差 −10,213.70）')
    fig.text(.04,.085,'未观察到购买不等于下架/缺货；共同商品净增加不能外推全部商品的同商品金额稳定。',fontsize=9)
    out=ROOT/'reports/computers_mix/composition_change.png'
    if out.exists():raise FileExistsError('Figure already exists')
    fig.savefig(out,dpi=150);plt.close(fig)
    with (ROOT/'.local/computers_mix/plot_validation.json').open('x') as f:
        json.dump(dict(status='passed',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),values=values,
                       png_sha256=hashlib.sha256(out.read_bytes()).hexdigest()),f,indent=2)

if __name__=='__main__':run()
