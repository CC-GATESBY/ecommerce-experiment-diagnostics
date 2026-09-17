"""Write the requested Markdown narrative from checked small report CSVs."""
import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(name):
    with (ROOT/'reports'/name).open(newline='') as f:return list(csv.DictReader(f))
def n(value):return f'{int(value):,}'
def money(value):return f'{Decimal(str(value)):,.2f}'
def pct(value,digits=2):return 'NA' if value in ('',None) else f'{float(value)*100:.{digits}f}%'
def table(headers,rows):return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in rows)
def picture(name,caption):return f'\n![{caption}](figures/{name}.png)\n\n{caption}\n\n'


def build(prepared,input_dir=None,output_dir=None):
    source=Path(input_dir) if input_dir else ROOT/'reports'
    destination=Path(output_dir) if output_dir else ROOT/'reports'
    destination.mkdir(parents=True,exist_ok=True)
    def read(name):
        with (source/name).open(newline='') as f:return list(csv.DictReader(f))
    prep=json.loads(Path(prepared).read_text());daily=read('behavior_daily.csv');stats=read('behavior_daily_stats.csv');categories=read('category_concentration.csv');hours=read('hourly_purchase.csv');funnel=read('funnel_summary.csv')
    if not daily or not categories:
        text='# 描述性报告：暂无足够数据\n\n当前输入没有日指标或品类汇总，无法形成完整月结论。金额/占比为NA，不补造类别或用户。\n'
        for name in ('behavior.md','period_summary.md'):
            with (destination/name).open('x') as f:f.write(text)
        return dict(status='no_data',reports=2)
    overall=next(r for r in funnel if r['level']=='overall');price={r['segment']:r for r in funnel if r['level']=='price_band'};s={r['metric']:r for r in stats}
    measured=all(r['monthly_distinct_status']=='measured_from_fact_monthly_distinct' for r in categories)
    peak=max(daily,key=lambda r:Decimal(r['purchase_amount']));low=min(daily,key=lambda r:Decimal(r['purchase_amount']));top=categories[:10];total=sum((Decimal(r['purchase_amount']) for r in categories),Decimal(0))
    shares={k:sum((Decimal(r['purchase_amount']) for r in categories[:k]),Decimal(0))/total for k in (1,5,10)}
    unknown=next((r for r in categories if r['is_unknown']=='True'),dict(purchase_amount='0.00',purchase_events='0',amount_share='0'));high_hour=max(hours,key=lambda r:int(r['purchase_events']));low_hour=min(hours,key=lambda r:int(r['purchase_events']))
    view_only=int(overall['view_only'])/int(overall['n_view']);month=prep['month']
    md=f'''# 10月样本：观测金额集中在electronics，多数路径仅观察到浏览

本期观测购买金额共 **{money(total)}**（原 price 单位），来自2019年10月固定用户样本日志。月内日金额最高为 **{money(peak['purchase_amount'])}（{peak['utc_date']}）**，最低为 **{money(low['purchase_amount'])}（{low['utc_date']}）**。这份报告描述当前样本发生了什么，并列出值得核查的结构；不判断原因、异常或策略收益。

- 日金额高点与购买用户占比高点同在10月16日，但活跃用户最高在15日、购买用户平均观测金额最高在14日。多个量的极值并不同步，不能只用流量或购买用户均额代替金额表现。
- 正式可判定路径中，{pct(view_only)}只有view；view→purchase为{pct(overall['view_to_purchase'],4)}。这描述24小时、固定复合键内的日志路径，不等于永久流失或用户从未加购。
- electronics占观测金额{pct(categories[0]['amount_share'])}，unknown另占{pct(unknown['amount_share'])}。金额集中与编码覆盖缺口需要一起看，不能把未知部分从分母删除。

## 本期范围和阅读口径

`analysis_scope=rees46_oct_user5_analysis_v1`；2019-10-01至10-31 UTC，固定用户目标抽样概率5%，主口径baseline_keep_all。样本月去重用户{n(month['active_users'])}、购买用户{n(month['buyers'])}、购买事件{n(month['purchase_events'])}。月人数引用已核验T1.3整月结果，不相加日人数；样本不代表全平台，金额不能乘20外推。所有金额仅为合格日志price之和，不是财务收入、GMV真值或订单收入。

U=当日活跃用户，B=当日购买用户，R=B/U，M=观测购买金额/B，V=观测购买金额。M不是客单价或订单均价。first_seen是观察窗口内首次出现，不是注册或新获客。31天金额状态均为complete_observed，但不能据此证明上游日志绝对无遗漏。

来源分别为已完成的metrics-month-01日/维度表、funnel-month-01脱敏结果，以及从唯一month-v101-01受控读取所得的24行小时汇总。报告未重新计算漏斗或重建指标。定义和固定选数规则见[本轮分析规格](behavior_analysis_contract.md)；技术核验见[验收记录](../docs/t22_validation.md)。

## 1. 金额高点不是所有分量同时到达高点

'''
    labels={'active_users':'U：活跃用户','buyers':'B：购买用户','purchase_events':'购买事件','purchase_amount':'V：观测购买金额','buyer_rate':'R：购买用户/活跃用户','amount_per_buyer':'M：观测金额/购买用户','first_seen_ratio':'观察期首次出现用户比例'}
    def value(k,v):return pct(v,4) if k in ('buyer_rate','first_seen_ratio') else money(v) if k in ('purchase_amount','amount_per_buyer') else n(v)
    md+=table(['日指标','最小值（UTC日）','最大值（UTC日）','31日中位数'],[(labels[r['metric']],value(r['metric'],r['min'])+'（'+r['min_dates']+'）',value(r['metric'],r['max'])+'（'+r['max_dates']+'）',value(r['metric'],r['median'])) for r in stats])
    md+='\n以上为全月固定摘要，极值不标作异常。金额与U/R/M各自使用独立坐标轴、相同UTC日期范围和零基线，避免用双轴制造同步感。精确日值及全部统计见[behavior_daily.csv](behavior_daily.csv)和[behavior_daily_stats.csv](behavior_daily_stats.csv)。\n\n'
    md+=table(['金额极值日','V','U','B','R=B/U','M=V/B'],[(r['utc_date'],money(r['purchase_amount']),n(r['active_users']),n(r['buyers']),pct(r['buyer_rate'],4),money(r['amount_per_buyer'])) for r in [peak,low]])
    md+='\nV=U×R×M在31天均通过既有容差的一致性检查；这只是口径恒等式，不证明任何分量导致了金额变化。本轮不计算贡献百分比，不推定促销、节日或系统故障。10月1日first_seen比例100%来自窗口左边界，不能解释为当日全部是新客户。\n'
    md+=picture('daily_purchase_amount',f"日观测购买金额的范围为{money(low['purchase_amount'])}–{money(peak['purchase_amount'])}。来源behavior_daily.csv；UTC日；单位为原price单位；固定用户样本，极值不等于异常。")
    md+=picture('daily_active_users',f"日活跃用户范围为{n(s['active_users']['min'])}–{n(s['active_users']['max'])}。来源behavior_daily.csv；UTC日内去重；不可相加为月用户。")
    md+=picture('daily_buyer_rate',f"日购买用户占比范围为{pct(s['buyer_rate']['min'],4)}–{pct(s['buyer_rate']['max'],4)}。来源behavior_daily.csv；分母为同日活跃用户；不是路径漏斗。")
    md+=picture('daily_amount_per_buyer',f"日购买用户平均观测金额范围为{money(s['amount_per_buyer']['min'])}–{money(s['amount_per_buyer']['max'])}。来源behavior_daily.csv；分母为同日购买用户；不是订单均价。")
    md+='## 2. 行为覆盖和有序路径回答不同的问题\n\n'
    coverage=[r for r in read('behavior_coverage.csv') if r['level']=='month']
    md+=table(['行为','事件记录数','发生该行为的整月去重用户'],[(r['event_type'],n(r['event_records']),n(r['behavior_users'])) for r in coverage])
    md+='\n覆盖表回答“是否发生过某行为”，没有验证行为先后；其人数比不能称顺序转化率。本样本未观察到remove_from_cart，没有补造记录。\n\n路径一行是(scope_id,user_id,user_session,product_id)在全月的最早view起点，不是一个人或一个session。正式起点为10月1–30日，所有后续步骤共享24小时截止点；31日事件继续作观察结果。全部1,382,516路径中，40,426条右截尾、92条同秒不确定被单列，剩余1,341,998条formal。两类排除不是流失；缺失路径键的合格事件本次为0，同键无view的192条事件保留在行为覆盖中。\n\n'
    md+=table(['独立路径标记','数量'],[(k,n(overall[k])) for k in ('n_view','n_cart','n_purchase','n_three_step')])
    md+='\n'
    ratio_labels=[('view→cart','n_cart','n_view','view_to_cart'),('cart→purchase（三步）','n_three_step','n_cart','cart_to_purchase_three_step'),('view→purchase','n_purchase','n_view','view_to_purchase'),('完整三步比例','n_three_step','n_view','three_step_ratio')]
    md+=table(['定义','分子/分母','比例'],[(label,n(overall[num])+' / '+n(overall[den]),pct(overall[field],4)) for label,num,den,field in ratio_labels])
    md+='\n'
    md+=table(['互斥严格类别','formal路径数'],[(k,n(overall[k])) for k in ('view_cart_purchase','view_purchase_no_confirmed_intermediate_cart','view_cart_no_observed_purchase','view_only')])
    md+='\n购买后才cart且没有后续purchase的路径，会计入N_cart和N_purchase而不计入三步。本次这类有55条，所以不能通过四个互斥类别简单相加推算所有阶段标记；另有无确认中间cart的购买路径。因此view→purchase可以高于view→cart，图采用四条独立比例而非逐层收窄的传统漏斗。严格类别只描述已观察证据，“无确认中间cart”不等于真实没有加购。\n'
    md+=picture('funnel_overall','来源funnel_summary.csv整体行；粒度formal商品会话路径；每条柱各自标明分子/分母；UTC起点1–30日，不外推全部访问机会。')
    md+='### 首次浏览价格带的差异保持描述性解释\n\n'
    md+=table(['首次view价格带','N_view','N_purchase','view→purchase'],[(k,n(price[k]['n_view']),n(price[k]['n_purchase']),pct(price[k]['view_to_purchase'],4)) for k in ['[0,20)','[20,50)','[50,200)','[200,+inf)','unknown']])
    md+='\n在当前样本中观察到随首次view价格带变化的描述性差异。尚未控制品类、品牌、商品结构和用户构成，因此不能解释为价格造成转化差异，更不能据此确定调价方案。价格使用最早view时刻，不用购买价；unknown为零分母，显示NA而非0%。\n'
    md+=picture('funnel_by_first_view_price_band','来源funnel_summary.csv价格带行；分母为各桶formal路径数，分子为严格后续购买路径数；UTC，描述性关联，零分母NA。')
    md+='购买事件审计仍为37,019：无效键0、同键无view 68、早于或同秒于首次view 64、起点不在正式范围928、超过24小时2、符合路径窗口35,957。购买事件保留重复重数，不等于路径或买家；详见[purchase_path_coverage.csv](purchase_path_coverage.csv)。\n\n## 3. 金额集中在electronics，未知品类仍占一成\n\n'
    md+=f"category_l1共{len(categories)}个桶，金额分母为整月{money(total)}，包含unknown。Top1 / Top5 / Top10累计金额占比分别为**{pct(shares[1])} / {pct(shares[5])} / {pct(shares[10],4)}**。Top10指按金额排序的类别桶，含unknown，并非十个完整识别的业务品类。\n\n"
    md+=table(['金额排名','一级品类/桶','观测购买金额','购买事件','金额占比'],[(r['amount_rank'],r['category_label']+('（缺失/非法编码）' if r['is_unknown']=='True' else ''),money(r['purchase_amount']),n(r['purchase_events']),pct(r['amount_share'],4)) for r in top])
    md+=f"\nunknown的观测金额为{money(unknown['purchase_amount'])}（{pct(unknown['amount_share'],4)}），对应{n(unknown['purchase_events'])}条购买事件；这一金额没有删除或重分配。electronics占比说明本样本的日志金额结构集中，尚不能判断集中风险已经发生，也不能认为某品类有问题。\n\n用户可能跨日、跨品类出现。当前日维度表只能加总为user_days和buyer_user_days；[全类别CSV](category_concentration.csv)明确保留这两项，整月去重users/buyers为未测，未通过相加制造月人数。金额与事件可以加总，人数份额不能跨品类相加。\n"
    if measured:
        old='用户可能跨日、跨品类出现。当前日维度表只能加总为user_days和buyer_user_days；[全类别CSV](category_concentration.csv)明确保留这两项，整月去重users/buyers为未测，未通过相加制造月人数。金额与事件可以加总，人数份额不能跨品类相加。'
        new=f'收尾授权后，已直接从合格事实按整月重新去重；users/buyers为月内去重用户/购买用户，原user_days/buyer_user_days仍保留。各品类用户集合相互重叠，不能把品类users相加当全月{n(month["active_users"])}名用户，也不能把每日用户相加当月人数。金额与事件可加总，人数的粒度必须单独说明。'
        md=md.replace(old,new)
        md+='\n'+table(['金额排名','品类/桶','月去重users','月去重buyers','用户日user_days','购买用户日buyer_user_days'],[(r['amount_rank'],r['category_label'],n(r['users']),n(r['buyers']),n(r['user_days']),n(r['buyer_user_days'])) for r in top])
        if unknown.get('users') is not None:
            md+=f"\nunknown月去重用户{n(unknown['users'])}、月去重购买用户{n(unknown['buyers'])}，与其他品类一样参与去重。"
        example=next((r for r in top if int(r['users'])<int(r['user_days']) and int(r['buyers'])<int(r['buyer_user_days'])),None)
        if example:
            md+=f"{example['category_label']}的月用户{n(example['users'])}与逐日用户相加{n(example['user_days'])}不同，月买家{n(example['buyers'])}与逐日买家相加{n(example['buyer_user_days'])}也不同；差异体现跨日重叠，不是用户异常。"
        md+='完整14桶见[全类别CSV](category_concentration.csv)，金额排名及Top1/5/10份额保持原值。\n'
    md+=picture('category_purchase_amount_top10','来源category_concentration.csv；整月category_l1金额；占比分母包含unknown；UTC固定样本。unknown排名第二，未移出Top10。')
    md+='## 4. 购买事件峰值在UTC 9时，不能解释为本地作息\n\n'
    md+=table(['UTC小时极值','购买事件','占37,019购买事件','小时内去重购买用户','观测购买金额'],[(r['utc_hour'],n(r['purchase_events']),pct(r['purchase_events_share'],4),n(r['purchase_users']),money(r['purchase_amount'])) for r in [high_hour,low_hour]])
    md+=f"\n小时0–23完整分布的事件合计{n(month['purchase_events'])}、金额合计{money(total)}，与月主口径一致。小时购买用户只在各自小时内去重，不能相加为月买家。最高/最低仅描述UTC桶，没有站点业务时区，不能把峰值直接解释为当地上午/晚上，也不足以提出营销投放时间建议。完整小时表见[hourly_purchase.csv](hourly_purchase.csv)。\n"
    md+=picture('purchase_events_by_hour_utc','来源hourly_purchase.csv；分母为全月37,019条购买事件（份额在CSV）；横轴UTC小时；行为事件不是订单，未知业务时区。')
    md+='''## 证据与尚未回答的问题

本轮固定日、首次view价格带、category_l1、UTC小时四种切片，没有继续搜索品牌/商品排行、用户聚类或星期几来凑故事。八张图直接读取提交CSV；日/品类/小时对账、独立标准库算术及逐图检查见[验收记录](../docs/t22_validation.md)。旧事实、指标、漏斗和历史报告未改写。

值得进一步核查的问题限于：日金额极值在质量与历史基准下是否值得继续诊断；只观察到view及无确认中间cart的路径是否与商品/用户构成或记录覆盖有关；electronics金额集中和unknown覆盖分别会怎样影响后续解释。这些是待核查问题，不是已确认原因或业务方案。简短业务阅读版见[阶段总结](period_summary.md)。本轮不执行T2.3、正式异动检测、贡献拆解或实验。
'''
    short=f'''# 10月固定用户样本阶段总结

## A. 本期范围

本期为2019年10月固定用户目标抽样概率5%的日志样本，全部时间为UTC。样本有{n(month['active_users'])}名观察用户、{n(month['buyers'])}名购买用户和{n(month['purchase_events'])}条购买行为。观测购买金额{money(total)}仅为合格日志price之和，不是全平台总体、财务收入或订单收入。主口径保留合格事件及重复候选。

## B. 三个可验证的观察

**1. 金额高点与购买用户占比高点同日，但各分量并不同步。** 日观测购买金额从{money(low['purchase_amount'])}（10月31日）到{money(peak['purchase_amount'])}（16日），中位数{money(s['purchase_amount']['median'])}。16日U={n(peak['active_users'])}，R={pct(peak['buyer_rate'],4)}，M={money(peak['amount_per_buyer'])}；活跃用户最高却在15日，M最高在14日。来源[日指标与统计](behavior_daily.csv)、[极值/中位数](behavior_daily_stats.csv)，粒度为UTC日；R的分母是当日活跃用户，M的分母是购买用户。这说明不能把某一个分量当作金额变化的替代指标；没有证明哪个分量造成变化，也没有把极值判成异常。

**2. 在可判定路径中，更多路径只记录到浏览，购买与加购也不是严格嵌套。** {n(overall['n_view'])}条formal商品会话路径中，{n(overall['view_only'])}条仅观察到view（{pct(view_only)}）；view→purchase为{pct(overall['view_to_purchase'],4)}，view→cart为{pct(overall['view_to_cart'],4)}，严格三步为{pct(overall['three_step_ratio'],4)}。来源[T2.1漏斗汇总](funnel_summary.csv)，分母是10月1–30日最早view、24小时观察完整且顺序可判的路径；40,426条右截尾与92条同秒不确定单列。该结构值得核查路径对应的商品/用户构成与记录覆盖，不能把仅view叫作永久流失，或把无确认cart解释为用户从未加购。首次view价格带的描述性差异也未控制混杂，不能直接支持调价。

**3. 观测金额高度集中在electronics，但未知品类覆盖不能忽略。** electronics为{money(categories[0]['purchase_amount'])}，占全月观测金额{pct(categories[0]['amount_share'])}；含unknown的Top5/Top10分别覆盖{pct(shares[5])}/{pct(shares[10],4)}。unknown仍有{money(unknown['purchase_amount'])}（{pct(unknown['amount_share'])}）和{n(unknown['purchase_events'])}条购买行为。来源[品类集中度](category_concentration.csv)，粒度为整月category_l1桶，分母含unknown；用户跨品类不能相加。它说明本样本金额结构及编码盲区，未证明业务集中风险已发生或某品类表现有问题。

时段补充：[完整24小时分布](hourly_purchase.csv)中UTC {high_hour['utc_hour']}时最多，{n(high_hour['purchase_events'])}条（{pct(high_hour['purchase_events_share'])}）；UTC {low_hour['utc_hour']}时最少，{n(low_hour['purchase_events'])}条（{pct(low_hour['purchase_events_share'])}）。缺少业务时区，不能解释为当地作息或直接决定投放时间。

## C. 值得下一步核查的问题

- 16日金额与购买用户占比高点，在既有质量状态及足够历史基准下是否仍值得进一步诊断？正式检测留待T4授权。
- 仅view或无确认中间cart的路径，是否与商品/用户构成或日志覆盖有关？当前比例本身不能回答原因。
- electronics的金额集中与unknown覆盖，是否会改变后续业务解释？需要先明确编码覆盖和可比较范围，不能直接提出品类调整方案。

本轮仅完成描述性总结。品类整月去重人数无法从每日汇总还原，当前仅保留用户日与购买用户日，月去重未测。完整定义、八张图和证据见[行为分析](behavior.md)。下一项仅建议T2.3一页业务决策备忘录，尚未执行。
'''
    if measured:
        short=short.replace('品类整月去重人数无法从每日汇总还原，当前仅保留用户日与购买用户日，月去重未测。',f'收尾已从合格事实补齐{len(categories)}个品类的月去重用户/买家，并保留用户日对照；不同品类用户不可相加。')
    for name,text in [('behavior.md',md),('period_summary.md',short)]:
        with (destination/name).open('x') as f:f.write(text)
    result=dict(reports=2,period_summary_characters=len(short),behavior_characters=len(md));print(json.dumps(result));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',required=True);a=p.parse_args();build(a.prepared)
