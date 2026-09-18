"""One scoped retrospective case from two immutable aggregate tables; no Spark."""
import argparse
import csv
from datetime import date
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import yaml
from anomaly.diagnose import screen,select_case,decompose,validate_dimensions,attribute,coverage,serialized,rational,DIMENSIONS
from scripts.metric_snapshot import select_snapshot,digest,require
from scripts.validate_analysis_scope import validate_scope,verify_evidence,history_readiness
from etl.fact_registry import registered_batch_matches

TABLES=('agg_daily_metrics','agg_daily_dim')
CODE=('anomaly/diagnose.py','scripts/run_diagnosis.py','scripts/metric_snapshot.py','tests/test_diagnose.py','config/anomaly.yaml')


def csv_write(path,rows):
    require(bool(rows),'empty output requires explicit unavailable status')
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
        for r in rows:
            v=serialized(r)
            w.writerow({k:json.dumps(x,ensure_ascii=False) if isinstance(x,(dict,list)) else x for k,x in v.items()})


def json_write(path,value):
    with path.open('x') as f:json.dump(serialized(value),f,indent=2,ensure_ascii=False,allow_nan=False)


def render(output,flags,chosen,dec,contributions):
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.local/t4/render-cache'))
    try:
        import matplotlib
    except ModuleNotFoundError:
        return {'status':'not_rendered_no_existing_matplotlib_in_analysis_environment'}
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt,dates as mdates,font_manager,ticker
    fonts={f.name for f in font_manager.fontManager.ttflist}
    font=next((x for x in ('Arial Unicode MS','PingFang HK','Songti SC') if x in fonts),None)
    if not font:return {'status':'not_rendered_no_existing_font'}
    plt.rcParams.update({'font.family':font,'font.size':11,'axes.unicode_minus':False})
    folder=output/'figures';folder.mkdir();checks=[]
    def figure(title,note):
        fig,ax=plt.subplots(figsize=(11,6.2));fig.subplots_adjust(left=.16,right=.94,top=.80,bottom=.24)
        fig.suptitle(title,x=.08,ha='left',fontsize=17,y=.96)
        fig.text(.08,.87,'2019年10月UTC · 固定用户样本 · retrospective exploration',fontsize=10)
        fig.text(.08,.13,note,fontsize=9)
        fig.text(.08,.07,'范围 rees46_oct_user5_analysis_v1 ｜ 金额为日志观测，非财务收入；非因果诊断',fontsize=9)
        return fig,ax
    def save(fig,name,expected,actual,source):
        require(len(expected)==len(actual) and all(a==b for a,b in zip(expected,actual)),'chart/CSV data mismatch')
        path=folder/name;fig.savefig(path,dpi=150);plt.close(fig)
        checks.append(dict(figure=name,source=source,expected=expected,actual=actual,pass_=True,sha256=digest(path)))
    fig,ax=figure('观测金额与过去同星期检测中位数','来源 anomaly_flags.csv；中位数仅展示历史≥3且可比日期。阈值不是统计显著性。')
    xs=[date.fromisoformat(r['utc_date']) for r in flags];v=[float(r['current_amount']) for r in flags]
    line=ax.plot(xs,v,label='当日观测金额',color='#254e70',marker='.',linewidth=1.5)[0]
    valid=[r for r in flags if r['comparable']]
    med=[float(r['median_amount']) for r in valid]
    baseline=ax.plot([date.fromisoformat(r['utc_date']) for r in valid],med,label='检测历史中位数',color='#a65f00',marker='s')[0]
    ax.axvline(date.fromisoformat(chosen['utc_date']),color='#ad394b',linestyle=':',label='固定规则选中案例')
    ax.set_xlim(date(2019,10,1),date(2019,10,31));ax.set_xticks([date(2019,10,n) for n in (1,6,11,16,21,26,31)])
    ax.set_ylim(bottom=0);ax.set_ylabel('观测购买金额（原price单位）');ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.legend(fontsize=9);ax.grid(alpha=.2)
    save(fig,'t4_amount_baseline.png',v+med,list(line.get_ydata())+list(baseline.get_ydata()),'anomaly_flags.csv')
    fig,ax=figure('10月25日 U / R / M 相对历史基准的变化','来源 decomposition.csv；历史10月4/11/18日；R0=B0/U0，M0=V0/B0。此图为因子幅度，不是因果贡献。')
    rows=[r for r in dec['rows'] if r['factor'] in ('U','R','M')];values=[float(r['relative_change']) for r in rows]
    bars=ax.bar(['U 活跃用户','R 购买用户率','M 每位买家金额'],values,color=['#254e70' if x>=0 else '#ad394b' for x in values])
    ax.set_ylim(min(0,min(values))*1.25,max(0,max(values))*1.25 or .005)
    ax.axhline(0,color='black',linewidth=.8);ax.yaxis.set_major_formatter(ticker.PercentFormatter(1))
    for bar,vv in zip(bars,values):ax.annotate(f'{vv:+.2%}',(bar.get_x()+bar.get_width()/2,vv),xytext=(0,6 if vv>=0 else -15),textcoords='offset points',ha='center')
    save(fig,'t4_factors.png',values,[b.get_height() for b in bars],'decomposition.csv')
    # Category is the coverage-focused dimension; include every bucket, no hidden residual.
    rows=sorted([r for r in contributions if r['dim_name']=='category_l1'],key=lambda r:float(r['amount_difference']))
    fig,ax=figure('10月25日品类金额差：同向变化与抵消均保留','来源 dimension_contributions.csv；对比10月4/11/18日日均值。各维度不可相加，金额差不是原因。')
    values=[float(r['amount_difference']) for r in rows]
    bars=ax.barh([r['dim_value_label'] for r in rows],values,color=['#254e70' if x>=0 else '#ad394b' for x in values])
    ax.axvline(0,color='black',linewidth=.8);ax.set_xlabel('观测购买金额差（原price单位）');ax.tick_params(axis='y',labelsize=9)
    save(fig,'t4_category_changes.png',values,[b.get_width() for b in bars],'dimension_contributions.csv')
    return dict(status='rendered',checks=checks)


def main(args):
    import duckdb
    require(re.fullmatch('[A-Za-z0-9_-]+',args.run_id) is not None,'invalid run id')
    folder=ROOT/'.local/t4';run=folder/args.run_id;run.mkdir(exist_ok=False)
    stage=run/'staging';stage.mkdir();started=time.monotonic();proof={'status':'failed'};connection=None
    protected={};queries=[]
    def budget():
        used=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        free=shutil.disk_usage(ROOT).free
        require(used+1024**2<=1024**3 and free>=150*1024**3,'T4 budget exceeded')
        return dict(local_t4_bytes=used,free_bytes=free,peak_memory='not_measured')
    def local(value):
        p=(ROOT/value).resolve();require(p.is_relative_to(ROOT),'outside project');return p
    def load(path):
        path=local(path);protected[str(path)]=digest(path);return json.loads(path.read_text())
    try:
        budget()
        log=io.StringIO()
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromName(name) for name in
                                  ('tests.test_diagnose','tests.test_idempotency.IdempotencyUnitTests')])
        test=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        (run/'tests.log').write_text(log.getvalue());require(test.wasSuccessful(),'synthetic/selector tests failed')
        policy=yaml.safe_load((ROOT/'config/anomaly.yaml').read_text())
        require(digest(ROOT/'config/anomaly.yaml')==digest(folder/'anomaly.yaml'),'pre-query policy changed')
        cfg=yaml.safe_load((ROOT/'config/analysis_scope.yaml').read_text());days=validate_scope(cfg);binding=cfg['binding']
        lc=load('config/analysis_scope.local.json');mc=load(lc['metrics_config']);cc=load(lc['crosscheck_config'])
        require(Path(cc['metrics_run']).name==binding['metric_run']=='metrics-month-01','canonical metric run required')
        require(mc['registry_path']==cc['registry_path'] and mc['scope_id']==cc['scope_id']==binding['scope_id'],'local binding mismatch')
        cross_path=local(lc['crosscheck_receipt'])
        require(cross_path.parts[-3:]==('crosscheck-month-01','complete','validation.json'),'canonical crosscheck required')
        cross=load(cross_path);registry=load(mc['registry_path']);require(len(registry['batches'])==1,'ambiguous registry')
        batch=registry['batches'][0];desc=batch['descriptor'];fr=local(desc['run_path'])
        fact_launch=load(fr/'launch.json');fact=load(fr/'complete/validation.json')
        snap=select_snapshot(ROOT,cc['metrics_run'],scope_id=binding['scope_id'],source_run=binding['fact_run'],tables=TABLES)
        metric=load(snap['run']/'complete/validation.json');load(snap['run']/'launch.json')
        verify_evidence(cfg,desc,fact_launch,fact,metric,cross)
        current_evidence={p:digest(local(p)) for p in batch['evidence']}
        require(registered_batch_matches({'evidence':current_evidence},{'evidence':batch['evidence']},
                                        allow_criteo_manifest_extension=True),'bound receipt changed')
        protected.update({str(local(p)):sha for p,sha in current_evidence.items()})
        for p,meta in snap['inventory'].items():
            require(cross['protected_hashes'].get(p)==meta['sha256'],'selected metric changed since independent check')
            protected[p]=meta['sha256']
        protected[str(ROOT/'config/analysis_scope.yaml')]=digest(ROOT/'config/analysis_scope.yaml')
        connection=duckdb.connect(':memory:');connection.execute("SET threads=2; SET memory_limit='512MB'; SET TimeZone='UTC'; SET max_temp_directory_size='128MB'")
        connection.execute('SET temp_directory=?',[str(stage/'temp')])
        def read_table(table,n):
            sql=f'SELECT * FROM read_parquet(?) LIMIT {n+1}'
            queries.append(dict(table=table,sql=sql,files=snap['files'][table],max_rows=n))
            cursor=connection.execute(sql,[snap['files'][table]])
            rows=[dict(zip([v[0] for v in cursor.description],row)) for row in cursor.fetchall()]
            require(len(rows)==n,'row count mismatch '+table)
            for r in rows:
                r['utc_date']=r['utc_date'].isoformat()
                require(r['scope_id']==binding['scope_id'],'row scope mismatch')
                for k,v in metric['lineage'].items():require(r.get(k)==v,'row lineage mismatch '+k)
            return rows
        daily=read_table(TABLES[0],metric['tables'][TABLES[0]]['rows'])
        dims=read_table(TABLES[1],metric['tables'][TABLES[1]]['rows'])
        require(len(daily)==31 and len(dims)==6879,'authorized aggregate sizes differ')
        daily.sort(key=lambda r:r['utc_date']);require([r['utc_date'] for r in daily]==days,'date coverage mismatch')
        for r in daily:
            expected=next(x for x in cross['daily'] if x['utc_date']==r['utc_date'])
            for k in ('scope_id','event_records','active_users','buyers','purchase_events','purchase_amount','count_allowed','amount_allowed'):
                require(str(r[k])==str(expected[k]),'daily crosscheck mismatch '+k)
            gate=batch['gates'][r['utc_date']]
            require(all(r[k]==gate[k] for k in ('count_allowed','amount_allowed','amount_status')),'date gate mismatch')
        groups=validate_dimensions(daily,dims)
        readiness=history_readiness(cfg,daily)
        with (ROOT/'reports/history_readiness.csv').open() as f:old=list(csv.DictReader(f))
        for r in readiness:
            prior=next(x for x in old if x['utc_date']==r['utc_date'] and x['purpose']==r['purpose'])
            require(r['history_dates']==json.loads(prior['history_dates']) and r['history_count']==int(prior['history_count'])
                    and str(r['meets_min3'])==prior['meets_min3'] and r['status']==prior['status'],'history readiness changed')
        flags=screen(daily,days,policy);chosen,selection=select_case(flags)
        csv_write(stage/'anomaly_flags.csv',flags)
        require(chosen is not None,'no comparable date: retain screening and stop case explanation')
        current=next(r for r in daily if r['utc_date']==chosen['utc_date']);history=[next(r for r in daily if r['utc_date']==d) for d in chosen['history_dates']]
        dec=decompose(current,history);require(bool(dec['rows']),'selected case decomposition unavailable')
        contributions=[];dimension_summary=[]
        for dim in DIMENSIONS:
            rows,summary=attribute(groups,chosen['utc_date'],chosen['history_dates'],dim,policy)
            require(summary['total_difference']==dec['total_amount_difference'],'dimension/global difference mismatch')
            contributions.extend(rows);dimension_summary.append(summary)
        cov=coverage(groups,daily,chosen['utc_date'],chosen['history_dates'])
        for name,rows in [('decomposition.csv',dec['rows']),('dimension_contributions.csv',contributions),
                          ('dimension_change_summary.csv',dimension_summary),('case_category_coverage.csv',cov)]:csv_write(stage/name,rows)
        json_write(stage/'case_summary.json',dict(selection=selection,chosen=chosen,current=current,history=history,decomposition=dec,dimensions=dimension_summary,coverage=cov))
        budget();charts=render(stage,flags,chosen,dec,contributions)
        require(all(digest(p)==sha for p,sha in protected.items()),'input changed')
        require(digest(ROOT/'config/anomaly.yaml')==digest(folder/'anomaly.yaml'),'policy changed during run')
        proof=dict(status='passed',run_id=args.run_id,tests=test.testsRun,selection=selection,chosen=chosen,read_rows={TABLES[0]:len(daily),TABLES[1]:len(dims)},
                   aggregate_only=True,protected_hashes=protected,queries=queries,code_sha256={p:digest(ROOT/p) for p in CODE},
                   charts=charts,dimensions_conserved=True,history_readiness_matched=True,log_identity_residual=dec['log_identity_residual'],
                   versions=dict(python=sys.version.split()[0],duckdb=duckdb.__version__),resources=budget())
    except BaseException as e:
        proof.update(error=type(e).__name__+': '+str(e));raise
    finally:
        if connection:connection.close()
        proof['elapsed_seconds']=round(time.monotonic()-started,3);json_write(stage/'validation.json',proof)
    stage.rename(run/'complete');print(json.dumps(serialized({k:proof[k] for k in ('status','run_id','selection','chosen','elapsed_seconds')}),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--run-id');choice.add_argument('--render-summary')
    args=parser.parse_args()
    if args.render_summary:
        output=(ROOT/args.render_summary).resolve()
        require(output.is_relative_to(ROOT/'.local/t4') and output.name=='complete','only new T4 aggregate summary rendering')
        proof=json.loads((output/'validation.json').read_text());require(proof['status']=='passed','analysis not complete')
        def rows(name):
            with (output/name).open() as f:return list(csv.DictReader(f))
        flags=rows('anomaly_flags.csv')
        for row in flags:row['comparable']=row['comparable']=='True'
        summary=json.loads((output/'case_summary.json').read_text())
        result=render(output,flags,summary['chosen'],summary['decomposition'],rows('dimension_contributions.csv'))
        import matplotlib
        result['versions']={'python':sys.version.split()[0],'matplotlib':matplotlib.__version__}
        json_write(output/'render_validation.json',result)
        print(json.dumps({'status':result['status'],'figures':len(result.get('checks',[]))}))
    else:main(args)
