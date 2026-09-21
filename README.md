# 电商实验分析与指标异动诊断平台

**公开数据上的电商增长判断、经营诊断与实验分析。**

这是个人公开数据项目，不是拼多多/Temu内部项目，也不是已上线实验平台。项目重点是判断何时值得试验、先核查什么，以及证据不足时为何暂不行动。仓库：[CC-GATESBY/ecommerce-experiment-diagnostics](https://github.com/CC-GATESBY/ecommerce-experiment-diagnostics)，保持 **private / main**。

## 优惠券是否值得进入试验？

**值得进入有条件的方案准备，尚不足以批准发券。** 比较的是“相同提醒”与“相同提醒加券”，不能把存在未购买用户直接当成补贴机会。

| 最关键的证据 | 对决策的意义 |
|---|---|
| 历史资格用户 **7,856人**，后续购买参考率 **3.2459%** | 有可追溯的规划基准，但不是未来仅提醒组的购买率 |
| 以该基准规划相对MDE **10%**，约需 **98,096人** | 按原双侧检验与功效假设计算，须另核实可触达规模；不能把历史样本直接放大 |

券成本须覆盖全部兑券买家，而非只算增量买家；即使购买率提高，也未必覆盖成本。真实可触达资格、券成本/贡献毛利、支付退款及安全护栏齐备后，才能决定是否上线试验。**本方案未上线，历史日志金额不是利润。**

[完整方案与投入条件](reports/next_experiment_design.md) · [资格基准](reports/cart_recovery_baseline.csv) · [样本需求](reports/sample_size_scenarios.csv) · [券成本情景](reports/coupon_economics_scenarios.csv) · [验收](docs/t34_validation.md)

## 金额下降是否应该直接调价？

**先查购买记录和商品组合，当前证据不支持对computers整体调价。** 调查从总体金额拆解进入品类，再收窄到有比较支持的商品，而非把金额贡献排名当成根因排名。

| 主案例：10月25日 vs 同星期历史日均 | 观察 |
|---|---|
| computers购买事件数 **−31.33%** | 主要先表现为记录减少；purchase不是订单或销量件数 |
| 每条购买平均观测金额 **−14.97%** | 商品组合与同商品金额需分开，不能直接称为降价 |

共同购买商品的金额项较小，但这一子集有选择性，不能外推所有商品价格稳定。当前优先核对匿名product_B的同规格购买记录，以product_A的历史单日集中作对照；没有真实SKU、报价或库存证据，不作广泛策略调整。

[商品构成判断](reports/computers_product_mix_review.md) · [六日与历史对照](reports/computers_mix/daily_comparison.csv) · [互斥拆解](reports/computers_mix/decomposition.csv) · [最初总体案例](reports/case_observed_change.md) · [验收](docs/computers_product_mix_validation.md)

## 看到报表增长或实验正差，能否直接行动？

**不能只凭增长方向或一次正差行动：先辨明覆盖、分母和不确定性。**

| 最关键的比较 | 能说与不能说 |
|---|---|
| 完整十一月日均较十月 **+23.64%**；暂不纳入11月15–17日的事后分支为 **−2.58%** | 源文件已有零购买/峰值，排除了所查范围的本地对账差异；分支不替代主结果，日期构成也不同 |
| 同一批购买用户，全队列购买率 **5.7173%**，返回者条件比例 **14.3891%** | 回答不同问题，差来自分母选择，不是策略收益 |

离线A/A在无处理时也出现显著正差；已知正效应模拟在固定单次分组中仍未显著。它们帮助检验方法和解释误判风险，不能证明真实优惠券有效。公开源零购买也不等于现实零交易，仍需交易侧发生时间与入库记录才能区分原因。

[购买时间形态与敏感性](reports/purchase_timing_review.md) · [固定分母](reports/cohort_definition.md) · [A/A误判风险](reports/aa_validation.md) · [已知效应单次评估](reports/effect_injection.md)

## 三类证据，三种结论边界

| 证据线 | 用来回答什么 | 不支持什么 |
|---|---|---|
| A · REES46观察性日志 | 行为描述、金额拆解、覆盖核查；据此提出条件式购物车试验设计 | 平台总体收入、事故根因、价格因果、已经创造的业务收益 |
| B · Criteo独立公开随机实验来源基准 | [公开样本组间差异](reports/criteo_business_summary.md)，强调绝对量级和区间 | 恢复原广告主ROI，迁移为优惠券效果；不与REES46连接用户 |
| C · 离线A/A与人工效应注入 | 固定队列下的分流、估计与边界验证 | 线上实验次数、真实新增买家、完整功效曲线或投入收益 |

## 证据、实现与最小复现

核心数值按来源行、范围、分母、run_id与结果commit登记在[结果索引](docs/result_registry.csv)。正式指标口径见[指标契约](docs/metric_contract.md)，数据使用条件见[日期质量规则](docs/date_quality_policy.md)。

- **范围：** 十月与十一月是同一冻结用户哈希规则、目标用户概率5%的样本；十月原scope保持独立，双月复核另有范围。事件可按不重叠日期相加，月用户数不能相加当双月去重人数。原始全源扫描是接入证据，不冒充正式全用户分析规模；精确规模见结果索引与[运行手册](docs/runbook.md)。
- **方法：** SQL/Python负责指标、拆解与统计；十月使用本地Spark建设指标、DuckDB独立核验；十一月为DuckDB增量解析与必要指标，未把整条双月流程描述为Spark作业。
- **环境：** Python 3.11、JDK 17、PySpark 3.5.8；DuckDB、NumPy/SciPy实际版本见[依赖锁](requirements.lock.txt)。Spark仅有本地模式证据；历史耗时不是受控加速实验。
- **最小复现：** [runbook](docs/runbook.md)提供已实际通过的隔离venv命令。只运行`scripts/demo_synthetic.py`中的自造案例，无需真实数据、私有收据或Spark。它验证固定分母与一个稀疏统计边界，不等于重验全量项目。

目录入口：业务报告在`reports/`；契约、验收与手册在`docs/`；SQL在`sql/`；接入/解析在`ingest/`、`etl/`；统计在`abtest/`；运行入口在`scripts/`。真实数据、用户键、membership、模拟数组、机器配置与日志仅留本地，不随仓库提供。

## 当前可展示范围

已有工程及分析证据覆盖数据接入/指标核验、行为与经营判断、公开实验总体评估、未上线购物车设计、固定队列、离线A/A及已知效应模拟。T7.1文档/最小复现与T7.2证据映射/阶段审查完成；**T7.3仅备好练习，本人独立理解与现场修改仍待验，G2尚未通过。**

Hadoop/YARN、CUPED、完整功效曲线、有限异质性、故障注入、受控性能对照及uplift模型均未完成，不写入已完成实践成果。见[逐项阶段审查](reports/project_release_checklist.md)、[简历草稿与证据](reports/resume_evidence.md)、[本人练习材料](reports/interview_notes.md)。

历史以[TASKS](TASKS_v4.md)、各阶段验收和[原README快照](https://github.com/CC-GATESBY/ecommerce-experiment-diagnostics/blob/8be3b17175e5a52d99dcb895f177bb026746ab7b/README.md)为准；历史报告中的“当轮未执行”是当时状态，不批量改写。项目没有自动公开、外部发布或策略上线。
