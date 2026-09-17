"""Render eight independent figures directly from reviewed aggregate CSV files."""
import argparse
import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.local/t22/render-cache'))
os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'.local/t22/render-cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,dates as mdates,ticker,font_manager

SCOPE='rees46_oct_user5_analysis_v1'
PRICE_ORDER=['[0,20)','[20,50)','[50,200)','[200,+inf)','unknown']
RATIOS=[('view_to_cart','n_cart','n_view','view → cart'),('cart_to_purchase_three_step','n_three_step','n_cart','cart → purchase（三步）'),('view_to_purchase','n_purchase','n_view','view → purchase'),('three_step_ratio','n_three_step','n_view','完整三步 / view')]


def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def num(value):return None if value in ('',None) else float(value)


def render(input_dir,funnel_dir,output_dir):
    inputs=Path(input_dir);funnel=Path(funnel_dir);output=Path(output_dir);output.mkdir(parents=True,exist_ok=False)
    known={f.name for f in font_manager.fontManager.ttflist}
    font=next((f for f in ('Arial Unicode MS','PingFang HK','Songti SC') if f in known),None)
    if font is None:raise RuntimeError('No existing Chinese font; do not install silently')
    plt.rcParams.update({'font.family':font,'font.size':11,'axes.unicode_minus':False})
    daily_path=inputs/'behavior_daily.csv';cat_path=inputs/'category_concentration.csv';hour_path=inputs/'hourly_purchase.csv';funnel_path=funnel/'funnel_summary.csv'
    daily=read(daily_path);categories=read(cat_path);hours=read(hour_path);funnels=read(funnel_path)
    records=[]
    def begin(title,source,grain,unit,limit):
        fig=plt.figure(figsize=(12,6.8));ax=fig.add_axes([.12,.28,.83,.55])
        fig.suptitle(title,x=.12,y=.95,ha='left',fontsize=18)
        fig.text(.12,.885,'2019年10月 UTC · 固定用户样本',fontsize=11)
        footer=[f'analysis_scope: {SCOPE}',f'来源：{source.name} ｜ 粒度：{grain} ｜ {unit}',f'限制：{limit}']
        for i,line in enumerate(footer):fig.text(.04,.16-i*.05,line,fontsize=9)
        return fig,ax
    def finish(fig,name,source,kind,keys,expected,actual):
        if len(expected)!=len(actual) or any((a is None)!=(b is None) or a is not None and a!=b for a,b in zip(expected,actual)):
            raise AssertionError('Artist differs from CSV: '+name)
        path=output/name;fig.savefig(path,dpi=180);plt.close(fig)
        records.append(dict(figure=name,source_csv=source.name,source_sha256=sha(source),kind=kind,keys=keys,expected_values=expected,artist_values=actual,pass_check=True,image_sha256=sha(path)))
    specs=[('purchase_amount','daily_purchase_amount.png','每日观测购买金额','观测购买金额（原 price 单位）',False),
           ('active_users','daily_active_users.png','每日活跃用户','当日去重活跃用户数',False),
           ('buyer_rate','daily_buyer_rate.png','每日购买用户占比','购买用户 / 活跃用户',True),
           ('amount_per_buyer','daily_amount_per_buyer.png','每日购买用户平均观测金额','观测购买金额 / 购买用户（原 price 单位）',False)]
    for field,name,title,unit,is_rate in specs:
        fig,ax=begin(title,daily_path,'UTC日',unit,'仅样本日志，非平台总体；极值不自动视为异常。')
        x=[datetime.fromisoformat(r['utc_date']) for r in daily];values=[num(r[field]) for r in daily]
        plotted=ax.plot(x,[float('nan') if v is None else v for v in values],marker='.',linewidth=1.5)[0]
        if not x:ax.text(.5,.5,'无数据 / NA',transform=ax.transAxes,ha='center')
        ax.set_xlim(datetime(2019,10,1),datetime(2019,10,31));ax.set_ylim(bottom=0)
        ax.set_xticks([datetime(2019,10,d) for d in (1,6,11,16,21,26,31)]);ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.set_xlabel('UTC日期');ax.set_ylabel(unit);ax.yaxis.set_major_formatter(ticker.PercentFormatter(1) if is_rate else ticker.StrMethodFormatter('{x:,.0f}'))
        actual=[None if math.isnan(float(v)) else float(v) for v in plotted.get_ydata()]
        finish(fig,name,daily_path,'daily_line',[r['utc_date'] for r in daily],values,actual)
    overall=next(r for r in funnels if r['level']=='overall')
    fig,ax=begin('四个路径比例各自有明确分母',funnel_path,'formal商品会话路径','比例；括号内为分子 / 分母','首次view起点10月1–30日；cart与purchase非嵌套，排除同秒不确定和右截尾。')
    ax.set_position([.28,.29,.34,.53]);values=[num(overall[r[0]]) for r in RATIOS]
    positions=[i for i,v in enumerate(values) if v is not None];bars=ax.barh(positions,[values[i] for i in positions]);actual=[None]*4
    for b,i in zip(bars,positions):actual[i]=float(b.get_width())
    for i,(field,n,d,label) in enumerate(RATIOS):
        v=values[i];text='NA（零分母）' if v is None else f'{v:.4%}  ({int(overall[n]):,} / {int(overall[d]):,})'
        ax.text(1.02,i,text,transform=ax.get_yaxis_transform(),va='center',fontsize=10)
    ax.set_yticks(range(4),[r[3] for r in RATIOS]);ax.invert_yaxis();ax.set_xlim(0,max([v for v in values if v is not None]+[.01])*1.12);ax.xaxis.set_major_formatter(ticker.PercentFormatter(1));ax.set_xlabel('各自定义的路径比例')
    finish(fig,'funnel_overall.png',funnel_path,'ratio_bar',[r[0] for r in RATIOS],values,actual)
    price={r['segment']:r for r in funnels if r['level']=='price_band'}
    if set(price)!=set(PRICE_ORDER):raise ValueError('Five frozen price bands required')
    fig,ax=begin('首次浏览价格带与已观察到的购买路径',funnel_path,'formal路径×首次view价格带','分母为各价格带N_view；分子N_purchase','描述性关联；未控制品类、品牌、商品和用户构成。unknown零分母显示NA。')
    values=[num(price[k]['view_to_purchase']) for k in PRICE_ORDER];positions=[i for i,v in enumerate(values) if v is not None]
    bars=ax.bar(positions,[values[i] for i in positions]);actual=[None]*5
    for b,i in zip(bars,positions):actual[i]=float(b.get_height())
    upper=max([v for v in values if v is not None]+[.01])*1.4
    for i,k in enumerate(PRICE_ORDER):
        r=price[k];v=values[i];text='NA\n零分母' if v is None else f'{v:.4%}\n{int(r["n_purchase"]):,} / {int(r["n_view"]):,}'
        ax.text(i,(upper*.06 if v is None else v+upper*.025),text,ha='center',fontsize=10)
    ax.set_xticks(range(5),PRICE_ORDER);ax.set_xlim(-.6,4.6);ax.set_ylim(0,upper);ax.set_ylabel('view → purchase 路径比例');ax.yaxis.set_major_formatter(ticker.PercentFormatter(1));ax.set_xlabel('最早view时刻价格（原 price 单位）')
    finish(fig,'funnel_by_first_view_price_band.png',funnel_path,'price_ratio_bar',PRICE_ORDER,values,actual)
    top=sorted(categories,key=lambda r:int(r['amount_rank']))[:10]
    fig,ax=begin('观测购买金额按一级品类集中分布',cat_path,'整月category_l1','观测购买金额；标签份额分母含unknown','品类未知值保留；用户可跨品类重叠，金额份额不是用户份额。')
    ax.set_position([.22,.28,.68,.55]);values=[num(r['purchase_amount']) for r in top];bars=ax.barh(range(len(top)),values)
    labels=[r['category_label']+('（未知编码）' if r['is_unknown']=='True' else '') for r in top]
    ax.set_yticks(range(len(top)),labels);ax.invert_yaxis();ax.set_xlim(0,max(values+[1])*1.32);ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'));ax.set_xlabel('观测购买金额（原 price 单位）')
    for i,r in enumerate(top):
        share=num(r['amount_share']);ax.text(values[i]+max(values+[1])*.01,i,'NA' if share is None else f'{share:.2%}',va='center',fontsize=10)
    if not top:ax.text(.5,.5,'无品类数据 / NA',transform=ax.transAxes,ha='center')
    finish(fig,'category_purchase_amount_top10.png',cat_path,'category_bar',[r['category_key'] for r in top],values,[float(b.get_width()) for b in bars])
    if [int(r['utc_hour']) for r in hours]!=list(range(24)):raise ValueError('24 ordered UTC hour buckets required')
    fig,ax=begin('购买事件在UTC小时中的分布',hour_path,'整月UTC小时桶','购买事件数，不是订单数','未知商店业务时区，不能解释为当地作息或直接选择营销投放时段。')
    values=[num(r['purchase_events']) for r in hours];bars=ax.bar(range(24),values);ax.set_xticks(range(24));ax.set_xlim(-.7,23.7);ax.set_ylim(bottom=0);ax.set_xlabel('UTC小时（0–23）');ax.set_ylabel('购买事件数');ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    finish(fig,'purchase_events_by_hour_utc.png',hour_path,'hour_bar',list(range(24)),values,[float(b.get_height()) for b in bars])
    result=dict(status='passed',python=sys.version.split()[0],matplotlib=matplotlib.__version__,font=font,figures=records)
    with (output/'render_validation.json').open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps(dict(status='passed',figures=len(records),python=result['python'],matplotlib=result['matplotlib'])))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-dir',required=True);p.add_argument('--funnel-dir',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args();render(a.input_dir,a.funnel_dir,a.output_dir)
