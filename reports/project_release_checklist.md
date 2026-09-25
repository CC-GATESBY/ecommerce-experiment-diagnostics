# 首版成果阶段审查

历史T7审查：2026-09-21，证据起点`8be3b17175e5a52d99dcb895f177bb026746ab7b`，run_id=`t7-evidence-review-01`。当时重组证据并完成一次人工隔离环境最小复现，下文保留其验收事实。

历史材料收尾：2026-09-22，起点`76a4e9406091389fe30e7553bdbaab17ffd5c012`。仅复读已提交报告、脱敏CSV及验收摘要，将PRICE-01、TARGET-01/02纳入求职材料；没有查询用户级数据、读取Criteo raw/test或重跑bootstrap、历史测试、演示及真实任务。当轮远程同步要求为private/main，未外发简历或发布站点。当前可见性遵循[本地范围说明](../docs/local_scope.md)中用户于2026-09-23确认的public/main要求；此处保留当时的执行条件。

当前材料复核：2026-09-25，起点`a4d775c1d7883e5f7a4ad6431f406ec53529135c`。只读已提交报告和脱敏CSV，更新E1、MODEL-EVAL-01与POWER-01的当前能力说明；未读取raw、用户级缓存、模型、预测或membership，未运行训练、评分、bootstrap、模拟或历史测试。下方历史验收表保留当时事实。

## 已有产物能支持什么

| 项目 | 证据 | 当前结论与限制 |
|---|---|---|
| 数据正确性与可追溯输入 | [来源](../docs/data_sources.md)、[清单](../data/MANIFEST.md)、[T0.3](../docs/t03_validation.md)、[T1.1](../docs/t11_closeout_validation.md)、[T1.4](../docs/t14_validation.md) | 指定输入/日期下已有工程核验；本轮复核文档，不冒充重扫大文件 |
| 经营判断、价格关联与条件式实验设计 | [computers](computers_product_mix_review.md)、[购买时间](purchase_timing_review.md)、[PRICE-01](price_margin_review.md)、[购物车](next_experiment_design.md) | 价格对的同期支持和稀疏购买限制已纳入建议；条件毛利门槛是假设，不是实测盈利；没有调价、发券或事故因果证据 |
| 公开实验基准与离线方法 | [Criteo](criteo_business_summary.md)、[队列](cohort_definition.md)、[AA](aa_validation.md)、[注入](effect_injection.md)、[POWER-01](power_raw_report.md) | 三类证据未混同；POWER-01只完成固定历史队列下未调整购买率功效，CUPED及raw/CUPED对照未做；不是线上实验或目标业务功效保证 |
| 有限覆盖简单规则与留出比较 | [TARGET-01](targeting_coverage_review.md)、[TARGET-02](targeting_holdout_review.md)、[主差CSV](targeting_test/policy_differences.csv) | 该阶段30%容量下简单规则相对随机获正向支持；两种定向同名单。TARGET阶段只评价简单规则，后续模型证据另列；同源随机留出不验证跨期/跨市场 |
| 有限模型与追加公开基准 | [E1](uplift_model_card.md)、[valid原表](uplift_valid_policy_comparison.csv)、[MODEL-EVAL-01](uplift_additional_evaluation.md)、[追加主差](model_evaluation/policy_differences.csv)、[验收](../docs/model_evaluation_validation.md) | E1响应/S/T三种方法结构、四分类器已训练并作valid开发比较；冻结模型的旧test追加比较完成。E2首次独立确认条件未满足；E3条件式迁移说明在主报告末节，不是部署批准或模型最佳证明 |
| 最小复现 | [runbook](../docs/runbook.md)、[薄入口](../scripts/demo_synthetic.py) | 历史新临时venv和代码副本实际运行passed；本轮未重跑。没有`.local`依赖，不是全量生产复现 |
| 简历与导航 | [README](../README.md)、[证据登记](../docs/result_registry.csv)、[三条草稿](resume_evidence.md) | 表述有来源/分母/日期/run/commit/限制；没有“全部代码独立完成”或已创造业务收益 |
| 本人理解与现场修改 | [练习材料](interview_notes.md) | **pending**；材料准备不能替代本人表现，未填写学习完成记录 |

## 历史最小复现与检查（2026-09-21）

| expected | actual | 结果 |
|---|---|---|
| 隔离环境只需锁内演示依赖 | Python3.11.15/macOS arm64的新venv；duckdb1.5.5、numpy2.4.6、PyYAML6.0.3、scipy1.17.1；pip check无冲突 | pass |
| 无真实数据、私有收据、绝对路径依赖 | 仅复制Python/SQL与依赖锁的临时副本，未复制`.local`；同命令执行成功 | pass |
| synthetic名单与分母字面预期 | 12条事件；A/B/C入组，N/R/未返回/B为3/2/1/1，B/N=1/3、B/R=1/2 | pass |
| 小样本不伪造推断 | 独立6人计数例子返回sparse_cells、CI/p为null | pass |
| 数字可回到原证据 | 结果登记逐项复读来源单元格/JSON路径及原commit；唯一新加总仅61个不重叠日期事件数 | pass |
| 规模与技术边界 | 双月样本事件5,455,032；没有相加月用户；源扫描规模分开；十月Spark/十一月DuckDB分开 | pass |
| 历史结果不改 | 只变导航、状态与新增T7材料；原报告、CSV、契约、代码及主环境锁文件哈希保持 | pass |
| 链接、敏感信息与提交范围 | 新文档本地链接可定位；只提交文档/脱敏登记/演示入口；日志/用户数据不入Git | pass |

独立venv运行ID为`t7-synthetic-isolated-01`；实际日志、临时路径、安装记录和最终文件核对收据只在本地`.local/t7/`。最小环境仅证明这一人工路径，未声称重新验收整个Spark环境。原README在参考commit完整保留，历史报告的“当轮未执行”原样保留；当前状态以TASKS任务块与本表为准。

## 历史材料核对（2026-09-22）

| expected | actual | 结果 |
|---|---|---|
| 新结果登记保留阶段、完整精度、分母/单位/run及限制 | 新增21个来源单元格登记；旧41条原列值保留，新增data_stage列只补本轮条目。PRICE原始关联/假设门槛、valid开发和test留出分开 | pass |
| TARGET-02主差从原策略差取值，不由舍入G相减 | 原值2.6063689715161527，区间[1.713007888790414,3.4389972459362395]；展示+2.6064及[1.7130,3.4390] | pass |
| 简历最多三条且均有证据/本人解释问题 | 经营及价格判断、购物车试验条件、有限覆盖test比较；A/A和注入仅作方法支撑 | pass |
| 三类证据和能力边界不扩大 | 观察性关联、公开基准比较、人工方法验证分开；同名单不算双重成功，复杂模型未比较，同源随机留出非跨期验证 | pass |
| 本人理解保持待验 | 仅追加Q9–Q11的问题及参考思路；作答、修改、通过均pending；T7.3/G2不勾选 | pending（本人待验） |
| 旧结果与本轮范围 | 只修改这五份既有求职材料；来源报告、规则、valid/test汇总、代码及锁文件不改，不执行历史任务 | pass |

## 当前材料核对（2026-09-25）

- 结果登记新增12个原CSV单元格：valid与旧test追加分别登记差、成对区间、容量、选中数及候选池规模；旧数值不变，TARGET限制文字仅明确为该历史阶段。主差原值分别为3.8461713615909128与4.314543590400747，区间从各自原表完整精度复制，不以舍入G相减。
- 简历仍为三条：经营诊断及价格/组合、购物车试验条件、模型与简单规则的同容量评价。第三条正文用valid开发差+3.85/万候选记录；追加+4.31与旧test使用限制留在映射表。A/A、注入及未调整功效为方法支撑，COST-01为人工情景附录。
- 仅核对数字、单位、来源阶段、链接与敏感信息；原结果、代码和依赖锁不改。新增Q12–Q15的问题与参考思路分开，本人答案、修改及通过均pending；不代勾T7.3/G2，也未重跑最小演示或历史任务。

## 按原定义审查总门槛

没有将门槛批量打勾；工程证据具备与本人理解签认分开。

| 门槛原定义 | 对应证据/现状 | 缺口或适用边界 |
|---|---|---|
| G0：T0.1–T0.4；小型Spark写读 | 范围、环境、Spark人工写读及REES46/Criteo corrected来源验收已有文档。见[TASKS对应项](../TASKS_v4.md)、[Criteo来源](../docs/criteo_source_validation.md) | **工程前置证据具备**，按原范围有效；不是本轮重新安装/下载或全项目理解签认 |
| G1：T1.1–T1.4样本核验 | 十月事实字段/守恒、日期门禁、质量敏感性、指标及DuckDB独立核验已有证据。见[T1.2](../docs/t12_validation.md)、[T1.3](../docs/t13_validation.md)、[T1.4](../docs/t14_validation.md) | **REES46指定范围工程条件具备**；十一月增量证据另见[双月验收](../docs/cross_period_validation.md)。Criteo走独立T0.4/T3路径，不能说所有数据经过同一指标流水线 |
| G2：所有P0通过，报告/代码/本人解释一致 | 业务及方法工程产物、T7.1和T7.2证据已整理 | **未通过**：T7.3待本人实际作答/现场修改，各历史本人解释项未代验；文件齐全不满足此条件 |
| G3：P0+P1，有YARN/CUPED/故障与性能证据 | T3.3有限描述分层已有TARGET-01证据；POWER-01完成T5.7的未调整购买率功效子项 | **未通过**：T4.5、T5.6、T5.7的raw/CUPED比较、T6.1–6.3未完成，也缺G2本人验收 |
| G4：相关P2完成 | E1有限训练/valid比较完成；MODEL-EVAL-01完成E2追加基准子项，E3本次条件式说明已提供 | **未通过**：E2首次独立确认条件未满足，旧test历史使用不能靠bootstrap消除；E4云迁移未执行，本人理解待验。已有模型比较不代表真实迁移、成本或部署通过 |

## T7状态与使用条件

- **T7.1 done**：求职版README、结果导航、运行手册与人工隔离复现完成；本人解释未代验。
- **T7.2 done**：三条简历草稿及证据映射、阶段审查完成；这不是全部能力或投递可用性的自动认证，本人解释未代验。
- **T7.3 in_progress**：仅练习材料已准备，本人待验；未创建已完成learning_log，未实际代写本人SQL、配置预测或修复记录。

模型能力只按已执行的有限训练、valid开发比较及旧test追加基准描述；功效只按未调整购买率描述。Hadoop/YARN、CUPED及raw/CUPED比较、受控加速、首次独立模型确认、真实跨团队协作和线上落地/ROI均不能冒充已完成成果。具备文件与代码不等于能独立维护；本人需在[练习材料](interview_notes.md)中完成不照稿解释、SQL/执行计划、配置预测和测试修改后再评估G2。下一步是这项理解验收，不追加月份、模型或方法。
