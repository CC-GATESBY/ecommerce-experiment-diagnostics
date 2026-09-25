# 电商实验分析与指标异动诊断平台

**公开数据上的电商增长判断、经营诊断与实验分析。**

这是个人公开数据项目，不是拼多多/Temu内部项目，也不是已上线实验平台。项目重点是判断何时值得试验、先核查什么，以及证据不足时为何暂不行动。仓库：[CC-GATESBY/ecommerce-experiment-diagnostics](https://github.com/CC-GATESBY/ecommerce-experiment-diagnostics)，当前为 **public / main**，由用户主动公开（2026-09-23确认）。公开内容仅限已审核代码、文档和脱敏汇总；真实数据、membership、本机实际配置、凭据与日志不随仓库提供。

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

[购买时间形态与敏感性](reports/purchase_timing_review.md) · [固定分母](reports/cohort_definition.md) · [A/A误判风险](reports/aa_validation.md) · [已知效应单次评估](reports/effect_injection.md) · [未调整购买率的功效与漏检](reports/power_raw_report.md)

POWER-01进一步给出固定历史队列、人工效果生成与重新分组下的检出曲线及Monte Carlo区间。它帮助解释一次未显著的局限，保留原单次结果；不验证购物车资格人群的功效、优惠券盈利门槛或跨业务迁移。

## 三类证据，三种结论边界

| 证据线 | 用来回答什么 | 不支持什么 |
|---|---|---|
| A · REES46观察性日志 | 行为描述、金额拆解、覆盖核查；据此提出条件式购物车试验设计 | 平台总体收入、事故根因、价格因果、已经创造的业务收益 |
| B · Criteo独立公开随机实验来源基准 | [公开样本组间差异](reports/criteo_business_summary.md)及[冻结简单规则的test比较](reports/targeting_holdout_review.md)，强调绝对量级、分母和区间 | 恢复原广告主ROI，迁移为优惠券效果；不与REES46连接用户 |
| C · 离线A/A与人工效应注入 | 固定队列下的分流、估计、未调整购买率功效及边界验证 | 线上实验次数、真实新增买家、raw/CUPED完整比较或投入收益 |

## 证据、实现与最小复现

核心数值按来源行、范围、分母、run_id与结果commit登记在[结果索引](docs/result_registry.csv)。正式指标口径见[指标契约](docs/metric_contract.md)，数据使用条件见[日期质量规则](docs/date_quality_policy.md)。

- **范围：** 十月与十一月是同一冻结用户哈希规则、目标用户概率5%的样本；十月原scope保持独立，双月复核另有范围。事件可按不重叠日期相加，月用户数不能相加当双月去重人数。原始全源扫描是接入证据，不冒充正式全用户分析规模；精确规模见结果索引与[运行手册](docs/runbook.md)。
- **方法：** SQL/Python负责指标、拆解与统计；十月使用本地Spark建设指标、DuckDB独立核验；十一月为DuckDB增量解析与必要指标，未把整条双月流程描述为Spark作业。
- **环境：** Python 3.11、JDK 17、PySpark 3.5.8；DuckDB、NumPy/SciPy实际版本见[依赖锁](requirements.lock.txt)。Spark仅有本地模式证据；历史耗时不是受控加速实验。
- **最小复现：** [runbook](docs/runbook.md)提供已实际通过的隔离venv命令。只运行`scripts/demo_synthetic.py`中的自造案例，无需真实数据、私有收据或Spark。它验证固定分母与一个稀疏统计边界，不等于重验全量项目。

目录入口：业务报告在`reports/`；契约、验收与手册在`docs/`；SQL在`sql/`；接入/解析在`ingest/`、`etl/`；统计在`abtest/`；运行入口在`scripts/`。真实数据、用户键、membership、模拟数组、机器配置与日志仅留本地，不随仓库提供。

## 同商品价格关联与条件门槛（新增专题）

[PRICE-01业务判断](reports/price_margin_review.md)比较既有十月正式路径中的固定价格对：先按支持度选商品，再看关联与日期限制。当前优先核对price_product_A的同规格浏览价与成交价对应，尚不支持直接调价；假设贡献毛利门槛与观察结果分开，不作为真实ROI或价格因果。见[脱敏比较](reports/price_analysis/product_comparisons.csv)、[条件情景](reports/price_analysis/margin_scenarios.csv)与[验收](docs/price_margin_validation.md)。不改变上述computers调查结论。

## 同覆盖人数，是否值得定向？（新增专题）

[TARGET-01开发评价](reports/targeting_coverage_review.md)：30%容量下，固定简单规则相对随机覆盖的每万候选记录差额为+3.0217，成对区间[2.1421, 3.8292]；RESPONSE与INCREMENTAL选中了完全相同的记录。该阶段只使用train/valid，原结果保留，见[同容量比较](reports/targeting/coverage_comparison.csv)、[直接策略差](reports/targeting/policy_differences.csv)与[验收](docs/targeting_validation.md)。

[TARGET-02冻结规则留出评价](reports/targeting_holdout_review.md)：test的30%容量每规则覆盖838,367条，简单定向相对随机的差额为+2.6064/万候选记录，成对区间[1.7130, 3.4390]，支持保留简单规则作目标业务试验候选；两种定向名单仍相同，没有额外增量排序价值。下一步最需要目标业务的处理前特征、随机干预及真实成本证据，不直接部署或迁移成优惠券名单。见[test结果](reports/targeting_test/coverage_comparison.csv)、[test策略差](reports/targeting_test/policy_differences.csv)、[事前协议](docs/targeting_holdout_protocol.md)与[验收](docs/targeting_holdout_validation.md)。这份历史证据只评价固定简单规则，不是模型test结果。

这里RESPONSE与INCREMENTAL是本版同一份名单，不是两套独立成功证据；原结果不能证明复杂模型无用。test是同一公开来源的随机留出，不是跨时间、跨市场验证。上述G差是容量标准化组间差额，不是真实新增客户、转化率相对提升或预算节省；登记使用原策略差文件的完整精度，不以展示值相减。

[E1有限模型开发](reports/uplift_model_card.md)已完成响应、S-learner、T-learner三种方法结构的有限训练与valid比较；T分两臂建模，共四个分类器。30%同容量下响应模型相对简单规则的G差为+3.8462，成对区间[2.7614, 4.8114]，保留为唯一新增开发候选。S点估计略高且与响应名单高度重合，不据此宣称S胜出或等价。只用原train内部早停；E1当轮未进行模型test评价，原test此前已用于TARGET-02。见[五策结果](reports/uplift_valid_policy_comparison.csv)、[预测诊断](reports/uplift_development_metrics.csv)、[事前协议](docs/uplift_baselines_protocol.md)与[验收](docs/uplift_baselines_validation.md)。

[MODEL-EVAL-01旧test追加比较](reports/uplift_additional_evaluation.md)已完成冻结模型评价。30%同覆盖下响应模型相对简单规则的G差为 **+4.3145，成对区间[3.3044, 5.2780]**，与valid开发比较方向保持；响应候选继续保留，简单规则继续作基准，S/T辅助结果不用于重新选赢家。test已用过且建模在其先前结果已知后开展，因此这不是全新独立确认，也不批准部署。Qini只作辅助排序摘要；真实迁移需要不同于当前公开广告基准、未参与方案选择的目标业务随机干预、处理前特征和实际成本证据。见[容量结果](reports/model_evaluation/coverage_comparison.csv)、[策略差](reports/model_evaluation/policy_differences.csv)、[协议](docs/model_evaluation_protocol.md)与[验收](docs/model_evaluation_validation.md)。模型专题到此收尾，不自动调参或训练更多模型。

## 当前可展示范围

附录 [COST-01：固定进口成本与篮子选择](reports/cross_border_cost_review.md)只使用27个人工篮子，比较商家承担、提价与增购在双参照下的需求门槛。它是政策启发的成本情景，不是REES46/Criteo实证、真实利润或税务核定；见[人工结果](reports/cost_analysis/strategy_comparison.csv)与[验收/复跑](docs/cost_scenarios_validation.md)。不并入简历三条主项目。

已有工程及分析证据覆盖数据接入/指标核验、行为与经营判断、价格关联及条件门槛、公开实验总体评估、有限覆盖规则的valid/test比较、未上线购物车设计、固定队列、离线A/A、已知效应模拟及POWER-01未调整购买率功效。[POWER-01合同与复跑入口](docs/power_raw_contract.md)、[验收](docs/power_raw_validation.md)独立登记，旧AA/单次注入结果不改。T7.1文档/最小复现与T7.2证据映射/阶段审查完成；**T7.3仅备好练习，本人独立理解与现场修改仍待验，G2尚未通过。**

E1完成有限模型训练与valid开发比较；MODEL-EVAL-01完成E2的旧test追加比较子项及本轮E3条件式说明，尚无全新独立模型确认或真实业务迁移。Hadoop/YARN、CUPED、T5.7完整raw/CUPED功效比较、故障注入及受控性能对照仍未完成，不写入已完成实践成果；POWER-01仅完成T5.7的raw先行子项。见[逐项阶段审查](reports/project_release_checklist.md)（保留当轮审查状态）、[简历草稿与证据](reports/resume_evidence.md)、[本人练习材料](reports/interview_notes.md)。

历史以[TASKS](TASKS_v4.md)、各阶段验收和[原README快照](https://github.com/CC-GATESBY/ecommerce-experiment-diagnostics/blob/8be3b17175e5a52d99dcb895f177bb026746ab7b/README.md)为准；历史报告中的“当轮未执行”是当时状态，不批量改写。项目没有自动公开、外部发布或策略上线。
