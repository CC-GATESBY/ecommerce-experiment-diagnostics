# T3.4 验收：历史资格基准与条件式试验设计

状态：**done（历史基准＋条件式实验设计；未上线，本人解释未代验）**。业务阅读入口为[挽回方案](../reports/next_experiment_design.md)。本轮没有线上分组、触达、发券或策略收益验证。

## 输入与执行顺序

实际根目录末尾U+0020保留；起点2432ffa09febdb3b46ce4b9e1bbe0f56fec88117，工作区干净，private/main与远程一致。使用唯一analysis_scope `rees46_oct_user5_analysis_v1`、scope `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`、事实`month-v101-01`。原范围配置、manifest、事实、指标、漏斗、Criteo membership与历史报告不改。

方案第1–3节在人工/真实查询前冻结，本机保存原稿与SHA；真实收据的design_before_run_sha256与其一致。实际结果只在第4–5节追加，未调整资格、等待时长、MDE或成本网格。资格SQL按整个10月每用户首次cart固定锚点，先标月末不完整，再排除完整窗口中的等待期购买；不删除unknown，不改变主口径重复重数。

成功真实run为`cart-baseline-02`：FactReader count/amount共用一个上下文，**物理加载1次**，31天用途检查通过；仅返回一行资格汇总，用户窗口Parquet只留本地且读回schema/行数核对。没有收回事实或用户清单，没有读取源/候选/工程CSV或Criteo明细。使用Python 3.11.15、JDK 17.0.19、PySpark 3.5.8、local[4]/Driver 4g/UTC；正常停止Spark、释放缓存，无依赖变动。

## 已知清单变更的限定兼容

首个真实尝试`cart-baseline-01`在FactReader核对登记证据时失败，尚未调用Parquet读取，失败收据保留。原因是旧registry绑定完整manifest，T0.4已完成Criteo后该文件发生合法追加。

独立比对Git中2b779bfd版本与当前文件：旧SHA为`f6fde65d4a8f2f8051456b5ed744233e08ea1881ee5ec50a539cd3d2772237ad`，新SHA为`39089916016724996b3b8c6f204aa35e4a5a9978b3729bdc1cf67276529667f3`。仅新增additional_sources.criteo_uplift_v2_1_corrected并更新task_status及subtasks.criteo_source_acceptance，REES46对象逐项不变。事实清单、收据、统计、日期门禁和其他证据均完全一致。

最小修复在FactReader增加显式选择的`allow_criteo_manifest_extension`：**仅接受这一对已审核SHA**，其余全部登记内容继续精确匹配；默认行为不变。没有改写旧registry、manifest或质量规则，没有新建真实registry。任意未来清单变化仍会拒绝，不能自动刷新证据；本轮入口明确选择该兼容，其他旧入口不会默默放宽。三项针对性拒绝/非修改测试及既有人工FactReader读取回归通过。

## expected / actual / pass

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 人工资格守恒（合成31条以内） | cart 14；完整12；右删失2；等待已购3；合格9；结果买家6 | 全部一致；相同时间/重复cart只一个锚点 | pass |
| 人工结果边界与金额 | (t0,end]；重复购买保留；known amount=50.00；坏金额用户仍算买家但均值为空 | 全部一致；非返回与unknown保留 | pass |
| 样本量独立字面值 | p0=.1、相对MDE=.2，每组3,841、总7,682 | 正态分位数实现与独立Decimal/固定分位数公式一致 | pass |
| 真实9个规划组合 | 每组向上取整且独立公式完全相同 | 9/9；本次均有效；非法概率人工测试拒绝、不截断 | pass |
| 成本条件 | k=.2平衡提升=.25；p0=.1→p1=.11、q=.5、d=.2、v=1时贡献=-.001 | 精确Decimal一致；9格符号全部符合字面预期 | pass |
| 真实全月cart用户 | 已提交behavior_coverage=16,751 | 16,751 | pass |
| 资格/结果守恒 | cart=完整+删失；完整=等待已购+合格；合格=购买+未购 | 16,751=16,209+542；16,209=8,353+7,856；7,856=255+7,601 | pass |
| 真实金额条件 | 未知不得补0；买家不因金额丢失 | 326购买事件；坏金额0；97,579.55 / 7,856=12.421022…，complete_observed | pass |
| 受控读取与保护 | 唯一run、31天count/amount允许、一次加载、原事实不改 | 全部通过；现有登记SHA不变 | pass |
| 兼容拒绝与旧接口回归 | 其他文件/收据/统计/manifest变更拒绝；旧规则不变 | 新17项测试、原9项日期测试通过；24条独立人工记录的53项FactReader读取/追加/阻断检查通过 | pass |
| 已有品类覆盖 | 三个汇总分母与unknown守恒、金额与旧品类表一致 | 事件/购买事件/金额已知覆盖68.3351% / 76.4445% / 89.5752% | pass |

真实资格统计由上述SQL一次计算，未做第二次全量事实重算；独立预期用于人工事件、规划公式与已有汇总对账，不把守恒检查冒充全量第二实现。p_hist=3.2459266802%是历史规划参考，不是新实验效果。

## 证据、规模与复跑

小型输出：[历史基准](../reports/cart_recovery_baseline.csv)1行、[样本量](../reports/sample_size_scenarios.csv)9行、[成本情景](../reports/coupon_economics_scenarios.csv)9行、[品类覆盖补充](../reports/category_coverage_context.csv)3行。后者仅复用T1.3已验收的month/unknown_dimensions汇总，与已有category_concentration金额及purchase_events核对；未新增品类查询。条件electronics占比边界75.4420%–85.8668%，假设已知归类正确、总金额不变，不是重新分类。

真实运行启动至正常结束20.946秒（worker 19.523秒），只作运行记录，不是性能对照。T34目录采样高水位含1 MiB预留为2,659,583 bytes；新增FactReader人工回归另外617,651 bytes采样高水位，代码与脱敏文档亦计入2 GiB总预算。最低观测磁盘空闲557,328,117,760 bytes，超过150 GiB。峰值内存not_measured，未为补数字重跑。磁盘可用空间变化还可能来自其他进程，不能把其净变化都算成本任务输出。

本机证据位于`.local/t34/`（冻结原稿、synthetic-01/02、失败cart-baseline-01、成功cart-baseline-02、清单追加审核）及`.local/t11/t34-reader-regression-01/`（仅人工数据）。本轮真实用户窗口16,751行包含资格状态，不是线上人群名单、不上传、不发消息；没有重生成旧事实、指标、漏斗或图片。

人工复跑（项目根目录，使用未占用run ID）：

```sh
.venv/bin/python scripts/run_cart_recovery.py --run-id synthetic-new --test
.venv/bin/python -m unittest tests.test_fact_access -v
```

真实复跑须另获授权；入口支持`--run-id`和`--synthetic-gate`，要求同代码哈希的人工通过收据，既有run不可覆盖。本轮不再真实运行。金额、p_hist与成本均保留相应精度；样本量为标准库正态近似而非精确二项计算，完整公式/方法来源见方案第3节。

工程未解决阻塞无。上线前仍需真实可触达/合规资格、券成本及贡献毛利、支付退款与发送/长期安全闭环。T3.3、T4、T5与总G0/G1没有提前执行或勾选；本人解释未代验。下一主线为T4指标诊断。
