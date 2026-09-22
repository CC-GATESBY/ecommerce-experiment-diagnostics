# 项目经历草稿与证据映射

以下供本人审查、学习与改写，尚未代替独立理解验收。只表述个人公开数据项目已交付的分析，不代表公司、团队或线上经营成果。

## 中文项目经历草稿

**电商增长判断与实验分析｜个人公开数据项目**：围绕经营诊断、优惠券试验条件与有限覆盖策略，使用SQL/Python分析公开数据；十月Spark指标经DuckDB独立核验，十一月使用DuckDB增量结果，Criteo作为独立公开实验来源基准。

- 针对金额下降是否应调价，拆解购买记录数量与商品组合，识别computers主案例购买事件减少31.33%；另用固定商品价格对和条件毛利门槛核查调价依据，发现日期可比性与稀疏购买限制，建议先核对同规格报价及成交记录，暂不全面调价。
- 针对加购未购人群是否值得发券，建立7,856名历史资格用户基准，设计“相同提醒”与“提醒加券”的未上线试验；将全部兑券买家的成本与样本需求纳入投入判断，明确先核实可触达规模、贡献毛利和护栏。
- 针对有限覆盖下如何选人，在Criteo公开基准上比较同人数的随机与简单定向规则，冻结后完成test的30%覆盖评价；定向相对随机的容量标准化组间差额为+2.6064/万候选记录（成对95%区间[1.7130,3.4390]），支持保留为目标业务试验候选。

## 每条表述的证据与解释责任

| 简历表述 | 结果文件/位置 | run_id及登记 | 本人需要解释 | 不能说 |
|---|---|---|---|---|
| 经营诊断及价格/商品构成判断 | [computers报告§1–4](computers_product_mix_review.md)、[日比较](computers_mix/daily_comparison.csv)的2019-10-25、[拆解](computers_mix/decomposition.csv)的stable_common；[PRICE-01§2–4](price_margin_review.md)、[A价格对](price_analysis/product_comparisons.csv)及[条件门槛](price_analysis/margin_scenarios.csv) | computers-mix-01 / price-margin-03；COMP_N_CHANGE、COMP_COMMON_P、PRICE_A_*、PRICE_MARGIN_* | 记录数量与组合怎样区分？共同商品为什么有选择性？A两价没有共同日意味着什么？提高购买比例为何仍可能低于贡献门槛？ | 定位真实故障、所有价格稳定、识别价格因果或已盈利；PRICE别名A与computers的product_A不是同一对象 |
| 历史资格与未上线发券设计 | [方案§2–5](next_experiment_design.md)、[资格基准](cart_recovery_baseline.csv)、[样本](sample_size_scenarios.csv)、[成本情景](coupon_economics_scenarios.csv) | cart-baseline-02；CART_N/P、CART_PLAN_N、COST_K/THRESHOLD | 全部入组分母包含谁？为什么成本不是只向增量用户收取？样本需求与经济门槛分别回答什么？ | 已发券、挽回7,856人、取得真实ROI；历史率是未来提醒control率 |
| 有限覆盖规则比较及冻结后test评价 | [TARGET-01开发报告](targeting_coverage_review.md)、[冻结规则](targeting/frozen_rules.json)；[TARGET-02§1–3](targeting_holdout_review.md)、[test覆盖](targeting_test/coverage_comparison.csv)的30%三规则行、[主策略差](targeting_test/policy_differences.csv)的30% INCREMENTAL_minus_RANDOM行；[验收](../docs/targeting_holdout_validation.md) | targeting-valid-01 / targeting-test-01；TARGET_VALID_*、TARGET_TEST_*；原规则criteo-targeting-rules-v1 | G的候选分母与选中分母怎样区分？相同名单为何只算一种策略证据？同源随机留出与跨期迁移有何区别？同覆盖为何不等于同成本？ | 真实新增客户、75.68%转化提升、节约预算或ROI；两种定向独立成功；复杂模型已被证明无用；已通过完整E2模型评价 |

具体数值、分母、数据阶段、日期、来源行、原结果commit与限制统一见[结果登记](../docs/result_registry.csv)。TARGET-02每规则选中838,367条，随机G=3.443871736465878、定向G=6.050240707982031；主差直接取原策略差文件的2.6063689715161527，区间[1.713007888790414,3.4389972459362395]，不由展示用的四位小数相减。

RESPONSE与INCREMENTAL在本版是同一份名单，只支持保留已有简单规则；复杂模型未被比较，不能说已证明无用。test是同一公开来源的随机留出，不是跨时间或跨市场验证；公开非均匀抽样、处理前特征解释、真实干预与成本仍限制业务迁移。

[固定队列](cohort_definition.md)、[A/A](aa_validation.md)和[效应注入](effect_injection.md)保留作分母与统计解释的方法支撑，不另加第四条简历要点。它们不代表真实线上实验、实际新增买家或功效曲线。本轮只复读已提交汇总，不查用户级数据或Criteo raw/test，不重跑任何分析。

## 贡献与能力边界（准备材料，不必塞进简历正文）

用户在任务中提出业务问题、限定范围和验收要求，并逐步要求把解释从金额贡献收窄到覆盖、商品构成和实验分母；代码实现、统计计算、核验脚本及文档整理有Codex工具辅助。不能仅因仓库为个人所有就说全部代码均独立手写。本人能否解释方法、审查结果、现场改SQL和测试，仍待T7.3；本人补充具体判断和修改过程后再形成个人贡献口述。

已有产物可以支持SQL/Python口径处理、Spark本地指标建设、DuckDB独立核验、经营及价格关联判断、条件式实验设计和冻结简单规则留出比较的作品证据。它不能代替真实跨团队协作、利益相关方沟通、上线运营或生产维护经历；这些须另由实习或协作项目证明。Hadoop/YARN、CUPED、完整功效曲线、受控性能改善、复杂uplift模型及完整E2模型评价均未完成，不能放入已完成实践。

岗位能力维度可参照[原JD映射](../docs/jd_mapping.md)，它是T0.1依据规划整理的历史快照，本轮未重新核实招聘JD。

本人逐条确认：**pending**。没有外发简历或自动切换公开仓库；[阶段审查](project_release_checklist.md)与[练习材料](interview_notes.md)是使用本草稿前的检查入口。
