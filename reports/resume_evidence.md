# 项目经历草稿与证据映射

以下供本人审查、学习与改写，尚未代替独立理解验收。只表述个人公开数据项目已交付的分析，不代表公司、团队或线上经营成果。

## 中文项目经历草稿

**电商增长判断与实验分析｜个人公开数据项目**：围绕经营诊断、优惠券试验条件与有限覆盖策略，使用SQL/Python分析公开数据；十月Spark指标经DuckDB独立核验，十一月使用DuckDB增量结果，Criteo作为独立公开实验来源基准。

- 针对金额下降是否应调价，拆解购买记录数量与商品组合，识别computers主案例购买事件减少31.33%；另用固定商品价格对和条件毛利门槛核查调价依据，发现日期可比性与稀疏购买限制，建议先核对同规格报价及成交记录，暂不全面调价。
- 针对加购未购人群是否值得发券，建立7,856名历史资格用户基准，设计“相同提醒”与“提醒加券”的未上线试验；将全部兑券买家的成本与样本需求纳入投入判断，明确先核实可触达规模、贡献毛利和护栏。
- 针对有限覆盖下如何选人，用Python训练响应及S/T基线，在Criteo公开基准按30%同容量比较；valid中响应模型相对简单规则的容量标准化组间差额为+3.85/万候选记录，保留响应模型作开发候选。

## 每条表述的证据与解释责任

| 简历表述 | 结果文件/位置 | run_id及登记 | 本人需要解释 | 不能说 |
|---|---|---|---|---|
| 经营诊断及价格/商品构成判断 | [computers报告§1–4](computers_product_mix_review.md)、[日比较](computers_mix/daily_comparison.csv)的2019-10-25、[拆解](computers_mix/decomposition.csv)的stable_common；[PRICE-01§2–4](price_margin_review.md)、[A价格对](price_analysis/product_comparisons.csv)及[条件门槛](price_analysis/margin_scenarios.csv) | computers-mix-01 / price-margin-03；COMP_N_CHANGE、COMP_COMMON_P、PRICE_A_*、PRICE_MARGIN_* | 记录数量与组合怎样区分？共同商品为什么有选择性？A两价没有共同日意味着什么？提高购买比例为何仍可能低于贡献门槛？ | 定位真实故障、所有价格稳定、识别价格因果或已盈利；PRICE别名A与computers的product_A不是同一对象 |
| 历史资格与未上线发券设计 | [方案§2–5](next_experiment_design.md)、[资格基准](cart_recovery_baseline.csv)、[样本](sample_size_scenarios.csv)、[成本情景](coupon_economics_scenarios.csv) | cart-baseline-02；CART_N/P、CART_PLAN_N、COST_K/THRESHOLD | 全部入组分母包含谁？为什么成本不是只向增量用户收取？样本需求与经济门槛分别回答什么？ | 已发券、挽回7,856人、取得真实ROI；历史率是未来提醒control率 |
| 模型与简单规则的同容量策略评价 | [E1模型报告](uplift_model_card.md)、[valid原表](uplift_valid_policy_comparison.csv)的30% RESPONSE_MODEL行：开发差+3.85；[旧test追加报告](uplift_additional_evaluation.md)、[原策略差表](model_evaluation/policy_differences.csv)的30% RESPONSE_MODEL_minus_FROZEN_SIMPLE行：+4.31，成对95%区间[3.3044,5.2780]；[E1验收](../docs/uplift_baselines_validation.md)、[追加验收](../docs/model_evaluation_validation.md) | uplift-valid-01 / model-eval-test-01；MODEL_VALID_*、MODEL_TEST_ADDITIONAL_*；简单基准沿用criteo-targeting-rules-v1 | logloss与增量排序为何不同？结果接近为何不等价？旧test已使用怎样限制正区间解释？同容量为何仍缺成本与迁移证据？ | 首次独立test确认、提升真实转化、创造客户或节约预算；响应模型已证明优于S/T；真实部署或ROI已验证 |

具体数值、分母、数据阶段、日期、来源行、原结果commit与限制统一见[结果登记](../docs/result_registry.csv)。valid原主差为3.8461713615909128，成对95%区间[2.7613791912669727,4.811402261117518]；旧test追加主差为4.314543590400747，区间[3.304386470944037,5.278031310791594]。两者均按30%容量，各选839,328与838,367条，G按各阶段候选池标准化。差与区间直接取原CSV完整精度，不由展示用10.3648−6.0502计算。

简单基准来自[TARGET-01](targeting_coverage_review.md)与[TARGET-02](targeting_holdout_review.md)，其中RESPONSE与INCREMENTAL仍是一份名单。后续E1已完成响应、S-learner、T-learner三种方法结构的有限训练；T分两臂建模，所以共有四个分类器，不是四套独立业务策略。valid用于开发选择；旧test此前已用于TARGET-02，且建模发生在其先前结果已知之后，MODEL-EVAL-01只能作为追加公开基准证据，E2首次独立确认条件未满足。两个阶段方向保持，继续保留响应候选及简单基准；没有S−响应直接区间，不宣称最佳或等价。E3条件式迁移说明已在[主报告末节](uplift_additional_evaluation.md#条件式迁移决定)提供，没有另建报告或批准投放。

[固定队列](cohort_definition.md)、[A/A](aa_validation.md)、[单次效应注入](effect_injection.md)与[POWER-01](power_raw_report.md)作为方法支撑，不另加简历要点。POWER-01已完成固定历史队列下的未调整购买率功效模拟；单次注入不等于功效估计，raw/CUPED对照仍未做。[COST-01](cross_border_cost_review.md)保留为人工成本情景附录，不并入三条主项目。本次仅复读已提交汇总，没有读取raw、用户级缓存、模型、预测或membership，没有运行训练、评分、bootstrap或功效模拟。

## 贡献与能力边界（准备材料，不必塞进简历正文）

用户在任务中提出业务问题、限定范围和验收要求，并逐步要求把解释从金额贡献收窄到覆盖、商品构成和实验分母；代码实现、统计计算、核验脚本及文档整理有Codex工具辅助。不能仅因仓库为个人所有就说全部代码均独立手写。本人能否解释方法、审查结果、现场改SQL和测试，仍待T7.3；本人补充具体判断和修改过程后再形成个人贡献口述。

已有产物支持SQL/Python口径处理、Spark本地指标建设、DuckDB独立核验、经营及价格关联判断、条件式实验设计、有限模型训练与同容量开发/追加基准评价，以及未调整购买率功效的作品证据。它不能代替本人独立维护能力、真实协作、上线运营或生产维护经历。Hadoop/YARN、CUPED、T5.7完整raw/CUPED比较、受控性能改善及E2首次独立确认仍未完成；真实策略成本、收益与ROI未验证，T7.3/G2及本人解释仍待验。

岗位能力维度可参照[原JD映射](../docs/jd_mapping.md)，它是T0.1依据规划整理的历史快照，本轮未重新核实招聘JD。

本人逐条确认：**pending**。没有外发简历或自动切换公开仓库；[阶段审查](project_release_checklist.md)与[练习材料](interview_notes.md)是使用本草稿前的检查入口。
