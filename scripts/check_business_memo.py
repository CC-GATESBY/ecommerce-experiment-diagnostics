"""Standard-library-only evidence checks for the fixed T2.3 document."""
import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
FIELDS=['claim_id','claim_text','source_file','source_row_or_metric','value','grain','denominator','limitation']
SCOPE='rees46_oct_user5_analysis_v1'
FORBIDDEN=('GMV真值','订单收入','永久流失','高价格导致高转化','electronics异常已确认')


def read_csv(root,name):
    with (root/name).open(newline='') as f:return list(csv.DictReader(f))


def percent(value,places=4):
    return format((Decimal(value)*100).quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP),'f')+'%'


def evidence(root=ROOT):
    rows=[]
    def add(key,text,source,metric,value,grain,denominator,limit):
        rows.append(dict(zip(FIELDS,[key,text,source,metric,str(value),grain,denominator,limit])))
    metric_source='reports/metric_checks.csv'
    checks={r['check']:r for r in read_csv(root,metric_source)}
    month={}
    for key,label in [('active_users','用户'),('buyers','购买用户'),('purchase_events','购买事件'),('purchase_amount','观测购买金额')]:
        row=checks['month_'+key]
        assert row['metric_version']=='rees46-metrics-v1' and row['pass']=='True' and row['actual']==row['expected']
        month[key]=row['actual']
        add('month_'+key,'全月'+label,metric_source,'check=month_'+key+'; field=actual',row['actual'],'固定样本整月','同一scope的全部合格事件；人数月内去重','非全平台；不加总日人数；金额为日志price和')
    category_source='reports/category_concentration.csv';categories=read_csv(root,category_source)
    assert len(categories)==14 and any(r['category_key']=='bucket:unknown' for r in categories)
    assert sum(Decimal(r['purchase_amount']) for r in categories)==Decimal(month['purchase_amount'])
    assert sum(int(r['purchase_events']) for r in categories)==int(month['purchase_events'])
    for name,key in [('electronics','category:electronics'),('unknown','bucket:unknown')]:
        row=next(r for r in categories if r['category_key']==key)
        assert row['monthly_distinct_status']=='measured_from_fact_monthly_distinct'
        for field,label in [('purchase_amount','观测购买金额'),('amount_share','金额占比'),('users','月去重用户'),('buyers','月去重买家'),('purchase_events','购买事件')]:
            value=percent(row[field]) if field=='amount_share' else row[field]
            if field=='amount_share':assert value==percent(Decimal(row['purchase_amount'])/Decimal(month['purchase_amount']))
            add(name+'_'+field,name+label,category_source,'category_key='+key+'; field='+field+('; percent_dp=4' if field=='amount_share' else ''),value,'整月category_l1桶',month['purchase_amount']+'（含unknown）' if field=='amount_share' else '同一桶合格事件；用户月内去重','品类用户集合重叠；金额不外推总体')
    categories.sort(key=lambda r:int(r['amount_rank']))
    for rank in (5,10):
        row=categories[rank-1];value=percent(row['cumulative_amount_share'])
        assert value==percent(sum(Decimal(r['purchase_amount']) for r in categories[:rank])/Decimal(month['purchase_amount']))
        add('top'+str(rank)+'_share','Top'+str(rank)+'金额覆盖',category_source,'amount_rank='+str(rank)+'; field=cumulative_amount_share; percent_dp=4',value,'按原金额排名累计',month['purchase_amount']+'（含unknown）','含unknown；不代表用户覆盖或策略收益')
    funnel_source='reports/funnel_summary.csv';funnel=next(r for r in read_csv(root,funnel_source) if r['level']=='overall')
    add('view_only_share','view-only路径比例',funnel_source,'level=overall; view_only / n_view; percent_dp=2',percent(Decimal(funnel['view_only'])/Decimal(funnel['n_view']),2),'formal商品会话路径',funnel['n_view'],'受最早view、24小时窗口、顺序判定及排除规则限制')
    daily_source='reports/behavior_daily.csv';daily=read_csv(root,daily_source)
    assert [r['utc_date'] for r in daily]==[f'2019-10-{d:02d}' for d in range(1,32)]
    assert sum(Decimal(r['purchase_amount']) for r in daily)==Decimal(month['purchase_amount'])
    assert sum(int(r['purchase_events']) for r in daily)==int(month['purchase_events'])
    add('date_reference','尚未判定异常的日期',daily_source,'utc_date=2019-10-16; field=utc_date','2019-10-16','UTC日','not_applicable','存在该日不等于异常')
    add('observation_month','观察月份',daily_source,'utc_date min/max month','2019-10','UTC整月','2019-10-01至2019-10-31','仅当前固定样本窗口')
    scope_path='config/analysis_scope.yaml';scope=(root/scope_path).read_text()
    assert re.search(r'^analysis_scope_version: '+SCOPE+r'$',scope,re.M)
    probability=re.search(r'^  target_user_probability: ([0-9.]+)$',scope,re.M).group(1)
    add('sampling_probability','目标用户抽样概率',scope_path,'sampling.target_user_probability',percent(probability,0),'固定用户哈希抽样设计','设计概率；非实测事件或用户占比','配置定义；不把样本金钱乘20')
    return rows


def plain(text):
    return re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',text)


def validate(memo,registered,root=ROOT):
    expected=evidence(root);checks=[]
    def check(name,want,actual):
        checks.append(dict(check=name,expected=want,actual=actual,passed=want==actual))
        if want!=actual:raise AssertionError(name+': '+str(actual))
    check('evidence_exact',expected,registered)
    claims={r['claim_id']:r['value'] for r in expected}
    # Re-read canonical source values, independent of authored Markdown literals.
    for label,prefix in [('全样本','month'),('electronics','electronics'),('unknown','unknown')]:
        line=next(s for s in memo.splitlines() if s.startswith('| '+label+' '))
        numbers=re.findall(r'\d[\d,]*(?:\.\d+)?%?',plain(line))
        numbers=[s.replace(',','') for s in numbers]
        keys=([prefix+'_purchase_amount']+([] if prefix=='month' else [prefix+'_amount_share'])+
              [prefix+('_active_users' if prefix=='month' else '_users'),prefix+'_buyers',prefix+'_purchase_events'])
        check('table_values_'+label,[claims[k] for k in keys],numbers)
    for key in ('top5_share','top10_share','view_only_share','sampling_probability'):
        check('quoted_'+key,True,claims[key] in memo)
    check('top_coverage_binding',True,'Top5/Top10金额覆盖：**'+claims['top5_share']+' / '+claims['top10_share']+'**' in memo)
    visible=plain(memo)
    # All remaining numeric tokens are either quoted evidence or explicit scope/date/heading syntax.
    numeric_text=re.sub(r'^## \d+\. ', '',visible,flags=re.M)
    allowed={r['value'].replace(',','') for r in expected}|{'2019','10','16'}
    tokens=re.findall(r'(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?%?',numeric_text)
    check('no_unsupported_numeric_token',[],sorted(set(s.replace(',','') for s in tokens)-allowed))
    for phrase in FORBIDDEN:check('forbidden_'+phrase,False,phrase in memo)
    check('title',True,memo.startswith('# 业务决策备忘录\n'))
    headings=re.findall(r'^## (\d+)\. ',memo,re.M);check('eight_sections',[str(i) for i in range(1,9)],headings)
    sections={int(n):body for n,body in re.findall(r'^## (\d+)\.[^\n]*\n(.*?)(?=^## |\Z)',memo,re.M|re.S)}
    alternatives=[r for r in sections[4].splitlines() if r.startswith('- ')]
    check('at_least_three_alternatives',True,len(alternatives)>=3)
    check('alternatives_need_discriminating_evidence',True,all('可能' in r and '需' in r for r in alternatives))
    check('one_priority_action',1,sections[5].count('**先核查'))
    for term in ('unknown','electronics','category_code','字段规范','来源映射','原编码模式','日期稳定性','对账','不执行查询'):
        check('action_'+term,True,term in sections[5])
    for term in ('若unknown仍无法可靠归类','继续暂缓品类策略','若unknown获解释后集中仍在','T4','具体日期','SKU','流量','库存','履约','核对变化与替代解释','若集中来自稳定历史结构'):
        check('decision_condition_'+term,True,term in sections[6])
    check('current_no_strategy_change',True,'暂不调整策略' in sections[1])
    check('no_category_user_sum',True,'各品类用户集合重叠，不能相加' in sections[2])
    for term in ('10月16日','96.34% view-only','价格带差异','描述性关联'):
        check('priority_rationale_'+term,True,term in sections[7])
    for term in ('观察性日志','不是因果结果','purchase event不是order','金额不是财务收入','不能直接外推全平台','待采集'):
        check('boundary_'+term,True,term in sections[8])
    han=len(re.findall(r'[\u4e00-\u9fff]',visible));check('800_to_1200_Chinese_characters',True,800<=han<=1200)
    for target in re.findall(r'\]\(([^)]+)\)',memo):check('link_'+target,True,(root/'reports'/target).exists())
    return dict(status='passed',checks=checks,Chinese_characters=han,visible_nonspace_characters=len(re.sub(r'[\s#*|`]', '',visible)),evidence_rows=len(expected),source_sha256={r['source_file']:hashlib.sha256((root/r['source_file']).read_bytes()).hexdigest() for r in expected})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write-evidence',action='store_true');parser.add_argument('--output');args=parser.parse_args()
    target=ROOT/'reports/business_decision_memo_evidence.csv'
    if args.write_evidence:
        with target.open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');writer.writeheader();writer.writerows(evidence())
    result=validate((ROOT/'reports/business_decision_memo_v1_t23.md').read_text(),read_csv(ROOT,'reports/business_decision_memo_evidence.csv'))
    if args.output:
        with Path(args.output).open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','source_sha256')},ensure_ascii=False))
    print('Checks passed:',len(result['checks']))


if __name__=='__main__':main()
