# 首版成果阶段审查

2026-09-21，证据起点`8be3b17175e5a52d99dcb895f177bb026746ab7b`。审查run_id=`t7-evidence-review-01`。本轮只重组已提交证据、核对数字/引用并运行人工最小演示；没有读取真实明细、重建指标、重跑A/A或效应注入。仓库保持private/main，未外发简历或发布站点。

## 已有产物能支持什么

| 项目 | 证据 | 本轮结论与限制 |
|---|---|---|
| 数据正确性与可追溯输入 | [来源](../docs/data_sources.md)、[清单](../data/MANIFEST.md)、[T0.3](../docs/t03_validation.md)、[T1.1](../docs/t11_closeout_validation.md)、[T1.4](../docs/t14_validation.md) | 指定输入/日期下已有工程核验；本轮复核文档，不冒充重扫大文件 |
| 经营判断与条件式实验设计 | [computers](computers_product_mix_review.md)、[购买时间](purchase_timing_review.md)、[购物车](next_experiment_design.md) | 可解释取证顺序和暂不行动条件；没有真实价格、库存、发券或事故因果证据 |
| 公开实验基准与离线方法 | [Criteo](criteo_business_summary.md)、[队列](cohort_definition.md)、[AA](aa_validation.md)、[注入](effect_injection.md) | 三类证据未混同；公开样本差异、无处理重分组、人工真值分别登记 |
| 最小复现 | [runbook](../docs/runbook.md)、[薄入口](../scripts/demo_synthetic.py) | 新临时venv和代码副本实际运行passed；没有`.local`依赖，不是全量生产复现 |
| 简历与导航 | [README](../README.md)、[证据登记](../docs/result_registry.csv)、[三条草稿](resume_evidence.md) | 表述有来源/分母/日期/run/commit/限制；没有“全部代码独立完成”或已创造业务收益 |
| 本人理解与现场修改 | [练习材料](interview_notes.md) | **pending**；材料准备不能替代本人表现，未填写学习完成记录 |

## 最小复现与本轮检查

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

## 按原定义审查总门槛

没有将门槛批量打勾；工程证据具备与本人理解签认分开。

| 门槛原定义 | 对应证据/现状 | 缺口或适用边界 |
|---|---|---|
| G0：T0.1–T0.4；小型Spark写读 | 范围、环境、Spark人工写读及REES46/Criteo corrected来源验收已有文档。见[TASKS对应项](../TASKS_v4.md)、[Criteo来源](../docs/criteo_source_validation.md) | **工程前置证据具备**，按原范围有效；不是本轮重新安装/下载或全项目理解签认 |
| G1：T1.1–T1.4样本核验 | 十月事实字段/守恒、日期门禁、质量敏感性、指标及DuckDB独立核验已有证据。见[T1.2](../docs/t12_validation.md)、[T1.3](../docs/t13_validation.md)、[T1.4](../docs/t14_validation.md) | **REES46指定范围工程条件具备**；十一月增量证据另见[双月验收](../docs/cross_period_validation.md)。Criteo走独立T0.4/T3路径，不能说所有数据经过同一指标流水线 |
| G2：所有P0通过，报告/代码/本人解释一致 | 业务及方法工程产物、T7.1和T7.2证据已整理 | **未通过**：T7.3待本人实际作答/现场修改，各历史本人解释项未代验；文件齐全不满足此条件 |
| G3：P0+P1，有YARN/CUPED/故障与性能证据 | 仅保留规划 | **未通过**：T3.3、T4.5、T5.6–5.7、T6.1–6.3未完成，也缺G2本人验收 |
| G4：相关P2完成 | 仅保留规划 | **未通过**：E1–E4模型、留出评价、定向建议/云迁移未完成 |

## T7状态与使用条件

- **T7.1 done**：求职版README、结果导航、运行手册与人工隔离复现完成；本人解释未代验。
- **T7.2 done**：三条简历草稿及证据映射、阶段审查完成；这不是全部能力或投递可用性的自动认证，本人解释未代验。
- **T7.3 in_progress**：仅练习材料已准备，本人待验；未创建已完成learning_log，未实际代写本人SQL、配置预测或修复记录。

不得把Hadoop/YARN、CUPED、完整功效曲线、uplift模型、受控加速、真实跨团队协作、线上落地/ROI写成已完成成果。具备分析文件与代码不等于能独立维护；本人需在[练习材料](interview_notes.md)中完成不照稿解释、SQL/执行计划、配置预测和测试修改后再评估G2。下一步是这项理解验收，不追加月份、模型或方法。
