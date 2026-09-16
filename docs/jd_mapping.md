# 岗位要求与项目证据映射

任务：T0.1。日期：2026-09-16。run_id：`bootstrap-20260916T085801Z`。

本表整理 `plan_v4.md` 第 1.2 节已有的岗位能力维度，不是本轮重新核实的官方招聘 JD。当前仅完成项目范围文档，以下分析交付均为 `planned`，执行结果均为 `not_run`。

| 岗位能力维度 | 对应任务 | 拟交付证据 | 能支持的判断与限制 |
|---|---|---|---|
| SQL / Python、数据处理 | T1.1–T1.4 | `etl/01_events.py`、`sql/metrics/`、`reports/crosscheck.csv`、重复运行测试 | 后续以实际范围下的口径、数据对账和独立核验说明能力；当前没有处理规模或正确性结果 |
| 电商业务理解与行动建议 | T2.1–T2.3 | `reports/behavior.md`、`reports/period_summary.md`、`reports/business_decision_memo.md` | 连接问题、证据、替代解释与核查行动；不将日志金额称为财务收入，不编造库存、履约或策略收益 |
| 异动监控与定位 | T4.1–T4.4 | `reports/anomaly_flags.csv`、`reports/decomposition.csv`、`reports/dimension_contributions.csv`、`reports/case_observed_change.md` | 支持候选变化与代数贡献解释；没有外部证据时不能称为已验证事故根因 |
| 实验设计与效果评估 | T3.1–T3.2、T3.4、T5.1–T5.5 | `reports/criteo_ate.md`、`reports/next_experiment_design.md`、`reports/aa_validation.md`、`reports/effect_injection.md` | 分开呈现公开基准、未上线方案与离线方法校验；不能称为拼多多线上实验成果 |
| Spark / Hadoop 与性能实践 | T0.3、T1.1–T1.5、T6.1–T6.3 | 小型读写核验、执行计划、`reports/hadoop_practice.md`、`reports/performance.md` | 需实际作业、相同输入输出和运行记录；当前未运行 Spark/Hadoop，不能用安装或原理说明替代实践 |
| 沟通与解释 | T2.3、T7.1–T7.3 | 业务备忘录、复现手册、`reports/learning_log.md` 与现场解释 | 可证明项目表达和维护能力；真实跨团队协作须由另有证据的实习或校企经历证明，本项目不虚构协作经历 |

P1 的 CUPED、功效和故障恢复，以及 P2 的 Uplift / 云迁移，均依照任务清单后续验收。当前不存在可引用的改善比例、性能收益、业务增长或模型胜出数字。

未来用于求职材料的每个数值，都必须对应实际输入范围、结果文件与 run_id。本人独立解释的核查仍待进行，不在本表提前打勾。

依据：[plan_v4.md](../plan_v4.md) 第 1.2、2、5、8 节；范围见 [project_brief.md](project_brief.md)。
