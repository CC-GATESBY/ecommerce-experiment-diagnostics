# 项目经历草稿与证据映射

以下供本人审查、学习与改写，尚未代替独立理解验收。只表述个人公开数据项目已交付的分析，不代表公司、团队或线上经营成果。

## 中文项目经历草稿

**电商增长判断与实验分析｜个人公开数据项目**：围绕经营变化、优惠券试验条件与结果可信性，用SQL/Python分析公开日志；十月Spark指标经DuckDB独立核验，十一月复用DuckDB增量结果。

- 针对computers金额下降，通过总体指标拆解、品类对照及商品级互斥分解，发现主案例购买事件减少31.33%、单条观测金额降低14.97%；将核查收窄到有比较支持的商品记录与构成，提出暂不据品类均值整体调价。
- 针对加购未购人群是否值得发券，建立7,856名历史资格用户基准，设计“相同提醒”与“提醒加券”的未上线比较；将全部兑券买家的成本与样本需求纳入条件判断，提出先核实可触达流量、贡献毛利和护栏。
- 针对正差异能否支持行动，评估独立公开RCT来源样本的绝对效果与区间，并用固定队列、离线A/A及已知效应模拟核验分母和估计；展示无处理仍可显著、已知正效应单次仍可不显著，区分统计检出与商业投入条件。

## 每条表述的证据与解释责任

| 简历表述 | 结果文件/位置 | run_id及登记 | 本人需要解释 | 不能说 |
|---|---|---|---|---|
| 经营变化与商品构成核查 | [computers报告§1–4](computers_product_mix_review.md)、[日比较](computers_mix/daily_comparison.csv)的2019-10-25、[拆解](computers_mix/decomposition.csv)的stable_common | computers-mix-01；COMP_N_CHANGE、COMP_AVG_CHANGE、COMP_COMMON_P；上游metrics-month-01及nov-metrics-02 | 为什么先从数量/组合调查？共同商品为什么是有选择性的子集？负向总和与净差为什么不同？ | 定位真实业务事故；所有商品价格稳定；已创造利润或已执行调价 |
| 历史资格与未上线发券设计 | [方案§2–5](next_experiment_design.md)、[资格基准](cart_recovery_baseline.csv)、[样本](sample_size_scenarios.csv)、[成本情景](coupon_economics_scenarios.csv) | cart-baseline-02；CART_N/P、CART_PLAN_N、COST_K/THRESHOLD | 全部入组分母包含谁？为什么成本不是只向增量用户收取？样本需求与经济门槛分别回答什么？ | 已发券、挽回7,856人、取得真实ROI；历史率是未来提醒control率 |
| 公开RCT与离线方法验证 | [Criteo摘要](criteo_business_summary.md)、[固定队列](cohort_definition.md)、[AA](aa_validation.md)、[注入](effect_injection.md) | criteo-itt-v1-02 / cohort-oct-01 / aa-oct-01 / injected-oct-01；CRIT_*、COHORT_*、AA_*、SIM_* | 相对与绝对差如何换算？为什么保留未返回者？生成真值与估计为何不同？ | 本人发券实现59.45%提升、创造488名真实新增买家；300次线上实验或已验证功效 |

具体数值、分母、日期、来源行、原结果commit与限制统一见[结果登记](../docs/result_registry.csv)。本轮复读原脱敏结果，不重算真实事实、队列或模拟，不用新的分析替换历史证据。

## 贡献与能力边界（准备材料，不必塞进简历正文）

用户在任务中提出业务问题、限定范围和验收要求，并逐步要求把解释从金额贡献收窄到覆盖、商品构成和实验分母；代码实现、统计计算、核验脚本及文档整理有Codex工具辅助。不能仅因仓库为个人所有就说全部代码均独立手写。本人能否解释方法、审查结果、现场改SQL和测试，仍待T7.3；本人补充具体判断和修改过程后再形成个人贡献口述。

已有产物可以支持SQL/Python口径处理、Spark本地指标建设、DuckDB独立核验、经营诊断与条件式实验设计的作品证据。它不能代替真实跨团队协作、利益相关方沟通、上线运营或生产维护经历；这些须另由实习或协作项目证明。Hadoop/YARN、CUPED、完整功效曲线、受控性能改善、uplift模型均未完成，不能放入已完成实践。

岗位能力维度可参照[原JD映射](../docs/jd_mapping.md)，它是T0.1依据规划整理的历史快照，本轮未重新核实招聘JD。

本人逐条确认：**pending**。没有外发简历或自动切换公开仓库；[阶段审查](project_release_checklist.md)与[练习材料](interview_notes.md)是使用本草稿前的检查入口。
