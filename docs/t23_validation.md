# T2.3 一页业务决策备忘录验收

2026-09-17，`memo-electronics-unknown-v1`。状态：**done（工程验收，本人解释未代验）**。

当前决定是暂不调整electronics的价格、流量、商品或漏斗策略，优先核查unknown与electronics的category编码覆盖。没有执行这项未来核查，也没有启动T4、实验或因果分析。

## 范围与交付

实际项目根目录保留末尾U+0020空格。起点为参考提交 `990662f55972b48c7e8c44eb54504c1bf4d188a5`；开始时工作区干净、origin正确，远程private/main一致。唯一analysis_scope为 `rees46_oct_user5_analysis_v1`，沿用T2.2已验收口径和结果。

交付为[备忘录](../reports/business_decision_memo.md)、[20条证据登记](../reports/business_decision_memo_evidence.csv)和轻量标准库核验脚本/测试。正文851个汉字，Markdown去链接地址和排版符号后1346个非空可见字符；八个短节、三行比较表，按一页阅读长度控制，未制作PDF或宣称已验证固定纸张分页。证据区将要求的全部样本/品类事实归并为四组，正文重点保留集中度、unknown覆盖和决策条件，没有新增指标或切片。

## 来源和数值规则

| 引用 | 当前提交的来源 | 定位与核验 |
|---|---|---|
| 全月用户151121、买家17121、购买事件37019、金额11598630.22 | reports/metric_checks.csv | month_active_users/month_buyers/month_purchase_events/month_purchase_amount；rees46-metrics-v1；expected=actual且pass=True |
| electronics金额8750242.89、占比75.4420%、用户84077、买家9902、购买事件21184 | reports/category_concentration.csv | category_key=category:electronics；monthly_distinct_status已测 |
| unknown金额1209130.91、占比10.4248%、用户75652、买家5201、购买事件8720 | 同上 | category_key=bucket:unknown；未从分母删除 |
| Top5/Top10金额覆盖98.2874%/99.9710% | 同上 | 原amount_rank=5/10的cumulative_amount_share，另用Decimal金额核对 |
| 96.34% view-only | reports/funnel_summary.csv | level=overall，view_only/n_view；分母为formal路径 |
| 10月16日及观察月份 | reports/behavior_daily.csv | 只确认既有日期存在、观察月份与原范围一致，不判异常 |
| 5%目标概率 | config/analysis_scope.yaml | sampling.target_user_probability；属于设计参数，不是实测用户或事件比例 |

数值核验复读四份已提交脱敏CSV和一个范围配置；月去重人数直接取既有整月验收行，不加总每日或品类人数。金额始终Decimal字符串精确比较，无float转换；百分比由原比例复算到指定小数位，并用既有金额/总金额交叉检查，未修改原比例。所有引用数值在证据登记中有source_file、行/指标定位、grain、denominator和limitation；只登记实际引用项，没有复制整份报告。

## Expected / actual / pass

| 验收项 | expected | actual | 结果 |
|---|---|---|---|
| Memo与证据、来源一致 | 所有引用定位到当前已提交来源 | 20/20条，金额/人数/比例对应一致 | pass |
| 金额和百分比 | Decimal精确金额；原比例四位/两位百分比一致 | 全部一致，金额及比例改错均被测试拒绝 | pass |
| 人数口径 | 月人数不由日/品类人数相加 | 来源为month检查行，明确品类集合重叠 | pass |
| 当前决定 | 暂不调整，指定优先核查 | 第一节明确；没有收益、ROI或上线承诺 | pass |
| 替代解释 | 至少3个，分别列区分证据 | 4个，均为可能解释且写明所需证据 | pass |
| 行动完整性 | 对象、操作、所需证据、验证方式 | unknown+electronics；原code模式/来源/日期；字段规范/映射/覆盖；归类解释前后金额对账 | pass |
| 条件式后续诊断 | 新证据决定是否进入，不提前执行 | 无法归类则暂缓；覆盖解释后且T4定位变化才诊断；稳定结构则不因高占比行动 | pass |
| 优先级理由 | 解释为何不先针对极值、view-only或价格带行动 | 第七节逐项交代证据不足和口径限制 | pass |
| 证据边界 | 观察日志、非因果、event非order、非财务收入、非总体、缺失字段待采集 | 第八节完整保留 | pass |
| 精简文档 | 800–1200中文字符，一页阅读目标 | 851汉字，无新增图或长附录 | pass |
| 结构及数值检查 | 标准库脚本全部通过 | 60项通过 | pass |
| 回归测试 | 正常输入通过，篡改金额/比例/人数/建议/阈值/篇幅时失败 | 12/12项通过 | pass |

脚本用词项断言检查结构；备忘录的判断、替代解释、优先级及条件关系另经逐段审读，不把词项匹配等同于证明业务原因。本人一分钟解释能力没有代验。

## 运行、保护和状态

本轮只运行现有`.venv`的Python标准库脚本：

```sh
.venv/bin/python scripts/check_business_memo.py --write-evidence --output .local/t23/memo-checks.json
.venv/bin/python -m unittest tests.test_business_memo -v
```

证据文件排他创建，已有文件不能被生成命令覆盖。复查已有文件时去掉`--write-evidence`并使用新的本地收据名。源码导入检查仅允许标准库；没有启动Spark/DuckDB、安装依赖、打开事实Parquet或用户级数据，也没有读取原始/候选/工程事件CSV。只对已有安全汇总做引用一致性算术，不生成新业务切片。未改T2.2报告、CSV、图或历史验收结果；原跟踪输入指纹在本地preflight和交付审查中保留，机器路径与测试原日志只存被忽略的`.local/t23/`。

T2.3现为done（工程验收，本人解释未代验）。这份备忘录是首稿；未来T4.4若获准修订，须保留该稿及其提交版本并说明修订证据/原因，本轮不更新T4.4最终案例。T3、T4、T5均未执行，后续顺序需另行决定；Criteo/T0.4及全项目G0/G1保持原状态。
