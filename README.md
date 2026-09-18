# 电商实验分析与指标异动诊断平台

分析课题：**电商增长分析与实验可信性验证**。计划用 SQL、Python 和 Spark 建立可核验的电商行为指标，解释指标变化，再通过离线校验与独立公开实验来源数据评估分析方法。

## 从三个业务问题进入

| 问题 | 已有证据 | 当前判断 | 待做部分 |
|---|---|---|---|
| 营销干预有没有增量，哪些用户值得进一步试验？ | [Criteo总体评估](reports/criteo_business_summary.md)；[购物车方案](reports/next_experiment_design.md)：首次加购等待24小时后，历史合格7,856人，后续购买参考率3.2459% | 在相同提醒下评估“加券”的价值，值得有条件准备；成本与样本不足以支持直接上线。Criteo不作为优惠券效果假设 | 券成本/贡献毛利、可触达流量、支付及安全护栏；定向分配曲线未做，不宣称已找到高增量用户 |
| 哪些价格—购买关系值得进入实验？ | [行为报告](reports/behavior.md)与[funnel_summary](reports/funnel_summary.csv)中首次浏览价格带的路径差异 | 现有差异仅为描述性关联，商品构成与用户选择尚未排除，不能直接调价 | 同商品价格分析、混杂核查与后续随机实验；目前均未完成 |
| 指标变化来自行为、商品构成还是覆盖变化？ | [10月25日案例](reports/case_observed_change.md)和[备忘录v2](reports/business_decision_memo.md)；下述三类品类覆盖 | 10月25日是固定规则唯一候选：M降幅最大，electronics承载主要金额差；不是因果事故，unknown保留在总量分母 | T4已完成一次回顾性案例；SKU构成、映射有效期、渠道/库存/履约仍待定向取证 |

### 品类覆盖补充：复用已验收汇总

| 可解释category_l1的覆盖 | 已知 / 全部 | 覆盖率 |
|---|---:|---:|
| 事件 | 1,444,660 / 2,114,081 | 68.3351% |
| 购买事件 | 28,299 / 37,019 | 76.4445% |
| 观测购买金额 | 10,389,499.31 / 11,598,630.22 | 89.5752% |

来自metrics-month-01已有month/unknown_dimensions汇总，[脱敏覆盖表](reports/category_coverage_context.csv)保留分母，未重新查询品类事实。这是编码可解释覆盖，不是上游日志完整性证明。若已知electronics归类正确且总金额不变，unknown全部不属于/全部属于electronics时，其金额占比边界为**75.4420%–85.8668%**。这是条件推导，不是重新分类或证明标签正确：高集中本身可以稳定成立，未知部分仍限制具体品类归因；没有证据证明Temu商家填报导致该问题。[T2.3初稿v1](reports/business_decision_memo_v1_t23.md)原文保留；本轮v2的优先级调整见下方T4案例。

## T4双月业务复核

[10–11月报告](reports/cross_period_business_review.md)保留原十月案例，并将核查优先级改为：先对账11月15–17日总体purchase事件覆盖与时间，再查computers在10月25日、11月1日和8日的商品构成。electronics整体更接近大盘；computers反复相对偏弱但月底反弹，不能定性持续恶化。11月15日有18,981名活跃用户却无purchase，16–17日占该月金额29.09%，不能以峰值直接证明恢复或事故修复。

新范围`rees46_oct_nov_user5_analysis_v1`延续同一5%目标概率用户哈希，包含11月新出现的匹配ID；11月新增3,340,951条样本事件，十月指标复用不重建。只补日指标/品类日表，不算品牌、first_seen、漏斗或实验。[范围与来源](docs/cross_period_source_scope.md) · [独立结果登记](reports/cross_period/analysis_scope.json) · [验收](docs/cross_period_validation.md)。不直接改变价格、流量或优惠策略；T4.5/T5未执行。

## 当前状态

S0、T0.1、T0.2、T0.3 已完成工程验收。REES46 10 月原始文件和两份 100,000 条头部工程样本保留；完整源扫描实测 42,448,764 条，新增固定用户候选含 151,121 用户、2,114,081 条事件，源与候选均观察到 10 月全部 31 天。上述是可追溯输入准备；后续已完成的事实解析和指标工程验收见下文，REES46线上实验与性能基准尚未运行，已完成的Criteo总体评估和本轮离线方案见下文。Criteo corrected v2.1来源验收现已补齐，T0.4 done（工程验收，本人解释未代验）；G0/G1仍需另行审核。状态见 [任务清单](TASKS_v4.md)，完整结果见 [整月输入验收](docs/t04_rees46_month_validation.md)，原获取和环境证据见 [首次 REES46 验收](docs/t04_rees46_validation.md)及 [T0.3 验收](docs/t03_validation.md)。

仓库目标为 `CC-GATESBY/ecommerce-experiment-diagnostics`，可见性保持 **private**。仓库同步只包含审查过的文件，不表示全部本地文件、数据或运行环境已经上传。

T1.1 已完成工程验收，本人解释未代验。旧 100,000 条工程样本、整月候选解析及重跑证据保留；该收尾阶段完成日期用途规则和人工跨月追加，以 `month-v101-01` 为唯一真实下游，未重建事实表。见 [收尾验收](docs/t11_closeout_validation.md)、[旧工程验收](docs/t11_engineering_validation.md)与[整月验收](docs/t11_month_validation.md)。

T1.2 已完成工程验收，本人解释未代验。该候选范围内识别892个重复候选组；每组留一条的假设会减少1,433条事件及1427.11观测购买金额，用户/购买用户不变。有效会话460,550个，最多350条事件，未命中>5000探索阈值。主事实保留全部合格事件，结果不等于清洗真值或业务收益。见 [T1.2 验收](docs/t12_validation.md)。

## 范围与证据

唯一主环境为本地，先做工程小样本，再做满足完整观察窗口要求的分析样本。全量双月或七个月处理是可选扩展，须由用户在小批量验收后明确决定，不作为首版完成条件。MRC、Nectar 和 Spartan 不作为当前依赖。

REES46 行为日志用于观察行为与指标变化；人工模拟用于校验方法；Criteo 用于独立公开实验来源基准。三类证据分别记录，不连接两份数据的用户，不将观察变化、模拟结果写成线上策略收益。所有尚未实现的交付物均为 `planned`，结果为 `not_run`。

## 阅读顺序

1. [本地范围补充](docs/local_scope.md)：当前小批量边界与扩量条件。
2. [项目简介](docs/project_brief.md)与[岗位证据映射](docs/jd_mapping.md)：项目问题、优先级和证据边界。
3. [规划 v4](plan_v4.md)、[执行约束](CODEX_START_v4.md)、[任务清单](TASKS_v4.md)：任务依赖、统计与质量要求、实际状态。
4. [环境摘要](docs/environment.md)：保留原 T0.2 检查结果；新专用环境以 [T0.3 验收](docs/t03_validation.md) 为准。

环境摘要引用的 `runs/environment_snapshot.txt` 以及任务中提到的原始收据仅保留在本机，GitHub 上不提供这些文件。T0.1、T0.2 文档保留原始检查日期和内容，本轮没有重新生成。

## Git 工作方式

每个任务先检查状态与差异，完成对应验收，再审查文件名、大小、内容及敏感信息；按明确路径暂存，检查暂存差异后 commit、push，并比较本地 HEAD 与远程对应分支 SHA。Git 提交与推送需有当前任务授权，不启用目录自动推送，也不进行强制推送。已有历史、远程或可见性冲突时先停止并报告。

`.gitignore` 排除原始数据、抽样明细、数据库、模型、原始运行日志、环境快照、本机配置、凭据及旧参考资料；安全元数据与小型汇总结果逐文件审核，不统一排除所有 CSV。忽略规则不替代提交内容检查，也不会移除已经被跟踪的文件。

## 复跑人工数据 smoke

从实际项目根目录执行，保留目录名末尾空格。需要项目 `.venv` 中的 Python 3.11、PySpark 3.5.8，以及已填写的 `config/local.yaml`；未填写模板会直接报错。首次准备方法见 [T0.3 验收](docs/t03_validation.md)。

```sh
".venv/bin/python" -m pip --isolated --no-cache-dir check
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" "scripts/run_smoke.py" --config "config/local.yaml"
```

启动器在创建 Spark JVM 前设置专用 Python、JAVA_HOME、`local[4]`、Driver `4g`、32 个 shuffle 分区和 UTC。临时目录及输出目录均来自配置，必须位于被忽略的 `.local/` 内。每次自动生成独立 run ID，原始日志、收据和 Parquet 留在本机；不覆盖旧运行，不启用 Hive。

## REES46 接入与工程样本

来源及使用说明见 [data_sources.md](docs/data_sources.md)，文件、哈希与样本范围见 [数据清单](data/MANIFEST.md)。原始文件和样本只留本机；GitHub 不提供数据。样本按源顺序取前 100,000 条数据记录，表头不计数，所有字段保持字符串值；不是随机样本，不能用于总体转化率、留存、长周期异动或 CUPED。

接入只使用现有专用环境中的 Python 标准库。独立配置模板为 `config/ingest.example.json`，填写后保存到被忽略的 `config/ingest.local.json`；不改动 T0.3 的配置校验。模板的空路径不可直接运行。复跑说明见 [数据清单](data/MANIFEST.md#安全复跑)：已有 raw 先校验哈希再复用，样本使用新的 run ID，不覆盖既有产物。

首次下载的是完整单月压缩包（1,741,928,540 bytes），解压为 5,668,612,855 bytes，再提取头部工程样本。T0.4 补充阶段复用该 CSV 完成覆盖核验，没有再次下载或解压。按[冻结规则](docs/analysis_sampling.md)以原始用户 ID 选择约 5%，保留选中用户在本源文件中的全部记录；实际事件比例为 4.980312%，不是实测用户比例。新产物标为 `user_sample_candidate`，原样本不覆盖、不拼接；每日覆盖见[源](reports/source_daily_coverage.csv)与[候选](reports/sample_daily_coverage.csv)。

按已授权的顺序调整，Criteo 暂后移，REES46 工程解析按该数据线独立验收。T1.1 的工程样本、整月候选及收尾验收见下；T1.5 与总 G0/G1 不提前完成。


## T1.1 工程样本事实层

仅使用第一份旧 100,000 条工程样本（约四小时），解析契约见 [event_parsing_contract.md](docs/event_parsing_contract.md)，schema 见 [events.sql](sql/ddl/events.sql)，实际结果见 [T1.1 工程验收](docs/t11_engineering_validation.md)。原始九字段保留为字符串；UTC 时间、Decimal(18,2) 和质量标记是新增列。不得用此范围推断整日或整月业务表现。

保留原有 `config/local.yaml` 环境绑定，单独填写 `config/events.example.yaml` 并保存为被忽略的 `config/events.local.yaml`。输入从 `data/manifest.json` 第一份工程样本定位；创建 `.local/t11/runs` 后填写输出根目录。模板不能直接运行，该工程模板拒绝其他样本和目录通配符；本轮唯一获准的整月候选使用下述独立模板和回归门槛。以下命令从实际项目根目录执行，两个 run ID 必须从未使用：

```sh
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" "scripts/run_events.py" --config "config/events.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-new-01"
".venv/bin/python" "scripts/run_events.py" --config "config/events.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-new-02" --compare-run-id "engineering-new-01"
```

测试含一个人工小文件 Spark 集成测试，需要允许本机 Python/JVM 回环端口通信。启动脚本沿用专用 `.venv` 和 JDK 17，以 local[4]、Driver 4g、32 个 shuffle 分区和 UTC 运行，不启用 Hive。独立标准库预期在启动 Spark 前计算；全部字段及重复重数、schema、聚合与金额精确核验通过且 Spark 正常停止后才发布 `complete`。两次输出独立保存；已有 run ID 会报错。原始字段、Parquet、期望侧文件、真实配置和收据仅留 `.local/`。该核验不替代 T1.4 DuckDB 验收。


## T1.1 整月候选解析与质量核对

此前工程回归及两个整月候选 run 均通过：各 2,114,081 条，31 天逐日覆盖一致，全字段与重复重数无差异。质量核对实算 151,121 名合格用户、17,121 名购买用户、37,019 条购买事件，观测购买金额 11598630.22（原 price 单位）。结果只限固定用户候选；日期放行与人工跨月追加在下述收尾阶段验收。

边界补丁为 `rees46-events-v1.0.1`：非有限字面值最多一个符号；Java 正则完整输入匹配；CSV 内 LF/CR/CRLF 保持原样。旧工程契约及验收不覆盖，补丁原因见[契约附录](docs/event_parsing_contract.md)。整月子任务结果见[独立验收](docs/t11_month_validation.md)，[全月质量](reports/data_quality_month.csv)、[逐日质量](reports/data_quality_daily.csv)、[逐项检查](reports/month_parsing_checks.csv)只用于工程核对。

整月配置使用 `config/events_month.example.yaml`，填入 manifest 的唯一候选相对路径，保存到被忽略的 `config/events_month.local.yaml`。源文件大小、哈希、完成收据及 scope/类型/行数须全部匹配，原始整月源和其他输入仍不允许。先使用工程配置在新 run 回归历史 Parquet；同一实现的通过收据才能作为 `--engineering-gate`。下例为本轮实际路径，复跑须使用新的 run ID，累计预算不得重置以掩盖旧输出：

```sh
".venv/bin/python" "scripts/run_events.py" --config "config/events_regression.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-regression-new" --regression-against ".local/t11/runs/rees46_oct_head_d50b23d8c05613dfd1eb/engineering-20260916-03" --budget ".local/t11/month-20260916/budget.json"
".venv/bin/python" "scripts/run_events.py" --config "config/events_month.local.yaml" --runtime-config "config/local.yaml" --run-id "month-new-01" --engineering-gate ".local/t11/month-20260916/runs/rees46_oct_head_d50b23d8c05613dfd1eb/engineering-regression-new" --budget ".local/t11/month-20260916/budget.json"
```

预算文件仅本机使用，记录本轮开始前 `.local/t11/` 的 `initial_bytes`、`max_new_bytes=21474836480`、`minimum_free_bytes=161061273600`；初次设置必须基于实测基线，后续同轮运行复用。运行中持续计入独立 JSONL、SQLite、Parquet、临时文件与日志，超限保留失败记录并停止。必要重跑使用新 run ID 并加 `--compare-run-id` 指向首轮；不覆盖、不为性能数字反复运行。独立核验覆盖全部记录及重复重数，SQLite 以有界批次完成用户去重；金额按日期附状态，解析完成不等于正式分析范围或全部日期自动放行。

## T1.1 日期规则与受控读取

T1.1 已达工程完成条件，本人解释未代验。固定 `month-v101-01` 为唯一真实下游批次，复验 run 不重复计入。[日期规则](docs/date_quality_policy.md)分别检查 count/amount 用途；[实际结果](reports/date_quality_gate.csv)为 31 天两类用途均放行、0 天阻断、31 天有维度缺失警告。这仅是 T1.1 使用条件，历史 formal_analysis_release 不改写，候选范围未升级，该阶段尚未进行 T1.3/T1.4 指标验收；本轮 T1.3 结果见下方。

复用接口为 `etl.fact_registry.FactReader`，必须传入本地登记文件、分析序列、明确日期、用途及预期 scope；任一日期缺失或阻断则拒绝整个请求。amount 用途仍返回全部合格行为，保留两个 eligibility 标记，不提前改变分母。登记按逻辑输入身份识别重跑，拒绝同序列日期重叠；只保证本地串行追加。

配置模板为 `config/fact_access.example.json`，填写后保存至被忽略的 `config/fact_access.local.json`。人工集成测试先于真实读取；只读事实不重跑解析。独立 run、预算、运行命令及 expected/actual/pass 见 [收尾验收](docs/t11_closeout_validation.md)。该阶段预算 2 GiB/保留 150 GiB，原始收据、文件清单与人工数据仅留本机。

## T1.2 重复候选与会话核验

[质量定义](reports/quality_policy.md)在真实运行前冻结：完整九字段规范化键包含Decimal价格，另算原始字符串完全相同的对照；会话按有效用户/session复合键，空session不成组，跨日不重切，观察跨度不解释为停留时长。真实阈值始终为>5000。

Spark SQL 实现在 [重复候选](sql/quality/duplicate_candidates.sql)和[会话统计](sql/quality/session_profile.sql)。运行入口 `scripts/run_quality.py` 使用原 FactReader 和独立新目录；主口径保持全部事件，B/C只作三场景敏感性对照。配置由 `config/quality.example.json` 填写为被忽略的 `config/quality.local.json`；真实运行必须先有同一代码版本的人工通过收据，不能传入人工低阈值。

结果见 [重复汇总](reports/duplicate_summary.csv)、[会话汇总](reports/session_summary.csv)、[全月及逐日敏感性](reports/quality_sensitivity.csv)。用户级明细、实际配置和原始日志不提交。预算、复跑命令、失败修复与守恒证据见 [验收文档](docs/t12_validation.md)。该阶段下一项建议为T1.3；本轮按单独授权完成结果见下方。

## T1.3 统一指标层

T1.3 已达工程完成条件，本人解释未代验。四层由 Spark SQL 生成：first_seen 151,121行、user_daily 322,660行、daily_metrics 31行、daily_dim 6,879行；仅读取既有 month-v101-01，不去重或排除会话。全月购买用户17,121、购买事件37,019、日志观测购买金额11598630.22；计数和Decimal精确对账。它们是固定用户候选内的指标，本轮独立核验见下文；不是平台总体或财务收入。

[指标契约](docs/metric_contract.md)冻结粒度、分母、UTC、金额状态和维度；[品牌映射](reports/brand_mapping.md)只用10月1–7日选Top200，此后不重排。first_seen是观察窗口内首次出现，日用户/会话不能相加当月去重；金额按买家平均不是订单客单价。未知品牌/品类保留，并在[完整验收及31天预览](docs/t13_validation.md)报告其覆盖。

运行入口 `scripts/run_metrics.py`、核心 SQL 在 `sql/metrics/`；模板 `config/metrics.example.json` 填写明确登记路径后保存到被忽略的 `config/metrics.local.json`。先运行人工测试；真实入口要求同版本通过收据，输出独立staging，四层主键、守恒、schema、全字段多重集写后核验通过且Spark停止后才发布。具体命令、预算10 GiB/保留150 GiB及资源记录见验收文档。

可提交结果为[31天完整日指标CSV](reports/daily_metrics_preview.csv)、[433项核验](reports/metric_checks.csv)和脱敏文档；四层Parquet、用户标识、实际映射、配置及收据仅本地。该阶段下一项为T1.4，已按新授权完成，见下方；T1.3历史验收文档保持原样。


## T1.4 独立指标核验

T1.4 已达工程完成条件，本人解释未代验。DuckDB 1.5.5 从原始候选 CSV 独立解析并计算 first_seen、品牌 Top200 和三个指标粒度；四张表及映射全部逐键核对，无键/类型/字段差异，金额最大差0.00、三个比率误差0。31天日期质量一致，10月5日另有完整单日核验。结果仅适用于既有固定用户候选。

[比较契约](docs/t14_comparison_contract.md)在真实运行前冻结；[99项字段比较](reports/crosscheck.csv)、[31天结果](reports/crosscheck_daily.csv)与[验收、资源及复跑命令](docs/t14_validation.md)可直接检查。独立SQL位于 `sql/validation/`，入口 `tests/crosscheck_duckdb.py`；本机配置使用 `config/crosscheck.example.json` 模板，保存为被忽略的 `config/crosscheck.local.json`。

人工测试复用T1.3真实build/publish，验证重复运行、固定观察上下文的输出日期扩展、失败后重试。`scripts/metric_snapshot.py` 只选择一个完成快照，不把新旧结果累加；这是本地串行快照机制，不是物理分区append或分布式事务。先运行 `scripts/run_crosscheck.py` 的人工阶段并停止Spark，再执行真实DuckDB核验。

该阶段建议的T1.5已按本轮授权完成十月首版冻结，见下方；Criteo/T0.4和全项目G0/G1仍未完成。真实数据、数据库、Parquet、映射明细、实际配置和原始日志仍只留本机。


## T1.5 十月首版分析范围

首版 `rees46_oct_user5_analysis_v1` 已冻结（本人解释未代验），[共享配置](config/analysis_scope.yaml)绑定唯一事实month-v101-01、指标metrics-month-01、独立核验crosscheck-month-01，保留原candidate身份。仅含10月固定用户样本，151,121用户、2,114,081事件；不是双月、全体用户或已确定的实验队列。5%用户目标概率不等于实测事件比例，金额不直接乘20外推。

描述性指标可用10月全部31天；24小时顺序漏斗只批准1–30日的起始view范围，31日保留结果观察和总体指标。探索诊断历史按[7,14,21,28]天、至少3点准备：22–31日有至少3点，29–31日有4点，仅标历史可用未评估。实验前置[10月1日,15日)、结果[15日,29日)，未来队列须由前置期用户决定。本轮没有实现漏斗、MAD/告警或实验。

[逐用途历史清单](reports/history_readiness.csv)、[分阶段规模和真实布局](reports/scale_baseline.md)、[配置测试与验收](docs/t15_validation.md)可核对。校验入口 `scripts/validate_analysis_scope.py`复用旧快照选择器，只查收据、元数据和31行日指标；共享配置不含机器路径，本机绑定保存在被忽略配置中。旧事实、指标、manifest与历史报告未改写。

原v4双月扩展保留为后续选择，不自动下载或扩量。REES46分数据线已有T1.1–T1.4工程证据，Criteo/T0.4及全项目G0/G1仍有待办。该阶段下一项建议为T2.1；本轮单独授权的结果见下方。

## T2.1 行为覆盖与24小时顺序漏斗

T2.1 已通过工程验收，本人解释未代验。[预先冻结的定义](reports/funnel_definition.md)把31天行为覆盖与首次 view 起点的商品路径分开：一条路径是 `(scope_id,user_id,user_session,product_id)`，全月每键只有一个起点，后续共用24小时截止点。正式起点为10月1–30日；31日起点保留作观察不足审计，同秒不能判定的路径单列。价格桶只取首次 view，不用购买价。

真实只读 `month-v101-01`，不合并复验 run、不去重、不排除高频会话。结果为1,382,516条路径，正式子集1,341,998条，观察不足40,426条，同秒不确定92条。四类、四个分母明确的比率、逐日/价格桶和购买事件对账见 [T2.1验收](docs/t21_validation.md)；[行为覆盖](reports/behavior_coverage.csv)、[漏斗汇总](reports/funnel_summary.csv)、[排除原因](reports/funnel_exclusions.csv)、[购买事件审计](reports/purchase_path_coverage.csv)均为脱敏汇总。CSV空值表示 null；unknown价格桶本次0条，不能解读为0转化率。

入口为 `scripts/run_funnel.py`，复用 FactReader 和已有快照选择器。将 `config/funnel.example.json` 的占位路径填到被忽略的 `config/funnel.local.json`；占位符不能直接运行。复跑命令与本地预算/不可变证据基线见验收文档。只有同版本人工测试通过，才可运行真实范围；所有输出先写独立 staging，完成全内容读回且正常停止Spark后才发布 complete。路径明细、真实ID、配置、收据和日志只留 `.local/t21/`。

本轮未读取CSV、重建事实/指标、扩量或安装依赖。比率仅适用于固定用户单月的可判定路径，不能称平台转化率、业务损失或价格因果效果。下一项仅建议T2.2，未执行。

## T2.2 行为分析与阶段总结

先读[阶段总结](reports/period_summary.md)，详细定义、八张图和证据见[行为分析](reports/behavior.md)。本期金额高点与购买用户占比高点同在10月16日，但U、M高点不同日；formal路径96.34%仅观察到view；electronics占观测金额75.44%，unknown另占10.42%。这些只描述固定用户单月样本，不是异常认定、永久流失、价格效果或业务方案。

日指标和漏斗沿用已核验结果，只新增一次受控UTC小时汇总，24桶精确对上37,019购买事件和11,598,630.22观测金额。图均由提交CSV生成，使用既有Matplotlib、无新安装，专用环境和依赖锁不变。[验收文档](docs/t22_validation.md)记录运行入口、expected/actual/pass、资源及历史元数据缺陷；模板为`config/behavior.example.json`，真实配置仅本地。

**T2.2 done（工程验收，本人解释未代验）**。closeout按新授权从month-v101-01一次聚合补齐14桶的月去重users/buyers，同时保留用户日。electronics月用户84,077、月买家9,902，对应用户日156,714、购买用户日15,196；跨日及跨品类人数不可相加。逐桶事件/购买/金额精确对账，金额份额与八张图不变，原真实数据未重建。收尾入口为`scripts/close_behavior_categories.py`，测试和运行证据见原验收文档的closeout节。T2.3和T4未执行，下一项唯一建议为T2.3一页业务决策备忘录。

## T2.3 一页业务决策备忘录

[备忘录首稿v1](reports/business_decision_memo_v1_t23.md)的决定是暂不调整electronics策略，先核查unknown与electronics的品类编码覆盖。其依据是金额集中与编码解释盲区，尚不能证明业务异常或策略效果。核查对象、操作、新证据和改变建议的条件均已写明；库存、履约、营销来源标为待采集。

T2.3 done（工程验收，本人解释未代验）。[20条证据登记](reports/business_decision_memo_evidence.csv)可定位原CSV，[验收记录](docs/t23_validation.md)记录60项标准库检查及12项测试。未启动分析引擎或查询新切片，T2.2结果不变。T4.4未来修订应保留本稿和修订原因；后续进入T3、T4还是T5需按总体项目顺序另行决定，本轮未执行。


## T0.4 Criteo 来源收尾

已验收官方 corrected uplift v2.1（13,979,592条，16字段），只做来源质量profile与按内容hash的只读raw登记。历史入口HEAD 404、Range GET 206响应不一致，本次完整文件仅从Criteo官方HF固定commit取得。条款两处一致为CC BY-NC-SA 4.0；本地非商业研究、raw不再分发。详见 [来源验收](docs/criteo_source_validation.md)、[脱敏字段profile](reports/criteo_source_profile.csv)及独立manifest条目。

人工与原接入回归：`.venv/bin/python -m unittest tests.test_criteo_source tests.test_ingest -v`。入口：`.venv/bin/python -m ingest.ingest_criteo_source --execute`，已有registry时验证后复用；未登记时才会在授权范围内下载固定文件。原REES46产物和依赖锁未改，不运行Spark。T0.4工程完成不等于全项目G0/G1已通过；下一项仅建议T3.1稳定身份与60/20/20封存划分，本轮没有split、ATE或特征探索。


## T3.1 Criteo 稳定身份与封存划分

T3.1 done（工程验收，本人解释未代验）。corrected v2.1全13,979,592条按源SHA＋从0开始的逻辑记录ordinal生成身份，重复内容仍是独立记录；seed 20260917，treatment各arm分别用固定整数hash阈值按60/20/20概率划分，不改变原treatment、不用结果或特征决定split。

实际train/valid/test为8,387,273 / 2,797,762 / 2,794,557。只生成一份四列gzip membership（576,697,968 bytes），两套全量实现和逐条读回一致，source四字段计数守恒。标签率只作预声明QC，不优化seed；不是ATE或SRM验证。首次目录发布失败已修复并留痕，复用同一产物，未重划。

[冻结契约](docs/criteo_split_contract.md) · [脱敏结果与digest](reports/criteo_manifest.md) · [QC CSV](reports/criteo_split_summary.csv) · [机器清单](data/criteo_split_manifest.json) · [验收与资源](docs/t31_validation.md)。单测：`.venv/bin/python -m unittest tests.test_criteo_split tests.test_criteo_source -v`。实际运行入口：`.venv/bin/python -m uplift.split --run-id criteo-split-v1-01`；已有run拒绝覆盖。

train供后续训练/探索，valid供选择，test封存作预定最终评价。以后T3.2按固定协议进行全量总体aggregate evaluation是预声明例外，不授权利用test切片选变量或调模型。raw标签不删除，membership与日志只留本机。T3.2–T3.4保持未开始，G0/G1和本人解释项不自动勾选；下一项仅建议T3.2。


## T3.2 公开实验基准的总体增量估计

先读[一分钟业务摘要](reports/criteo_business_summary.md)。corrected公开样本的conversion从control 0.193759%到treatment 0.308946%，增加11.519 bp，相对提升59.45%；每万assigned users约多11.52个conversion（95%区间10.85–12.19）。visit约多103.42个/万人，两者同向；相对提升大不代表已具备扩投价值。

[总体评估](reports/criteo_ate.md)区分数据事实、业务解释和决策限制；[效果表](reports/criteo_effects.csv)保留计数、SE与完整精度。公开非均匀抽样不能恢复原广告主增量或ROI，也不能改写成补贴效果；投入判断仍缺成本、收入/毛利、退款、留存及护栏。exposure只作描述，不用于筛分母。

T3.2 done（工程验收，本人解释未代验）。入口`.venv/bin/python -m uplift.ate`复用既有local[4]/4g/UTC启动方式；人工先行，真实CSV仅扫描一次、只返回两行，独立标准库复核最终效果小表。18项测试、收据、低频规则与复跑命令见[验收文档](docs/t32_validation.md)。原raw/membership及历史结果未改，未安装依赖。本轮不分split分析、不做特征探索或T3.3，下一项优先建议T3.4业务实验设计，待另行授权。

## T3.4 购物车挽回的投入条件

T3.4 done（历史基准＋条件式实验设计；未上线，本人解释未代验）。[方案](reports/next_experiment_design.md)先冻结首次加购的24+24小时窗口，再经一次FactReader真实加载计算历史基准；未读取源CSV或Criteo明细，未重建指标/漏斗。中心基准下检测20%相对提升需两组25,648人，超过当前历史合格7,856人；这是规划比较，不推算未来流量或实验天数。券成本负担10%时，盈亏平衡相对提升为11.1111%，不是“显著就值得上线”。

[基准](reports/cart_recovery_baseline.csv)、[样本量](reports/sample_size_scenarios.csv)、[成本情景](reports/coupon_economics_scenarios.csv)均为小型汇总；用户级中间结果、失败记录及收据仅留本地。[验收与人工复跑](docs/t34_validation.md)记录旧登记对Criteo清单追加的限定兼容检查，原registry、manifest和数据不改写。下一主线为T4指标诊断，本轮未执行；T3.3/T5与总门槛不提前勾选。

## T4.1–T4.4 一个可追溯的金额变化案例

**先查electronics购买商品构成，暂不直接调价、改流量或发券。** [主案例](reports/case_observed_change.md)按固定规则选出10月25日：相对前三个合格周五的检测中位数下降12.4945%，是本轮唯一候选；与同组历史均值比下降15.3279%。每位买家金额M下降9.5620%，electronics承载77.96%的均值金额差；unknown绝对金额接近历史水平，其份额上升不能直接解释为编码丢失。窗口首次出现桶的变化受观察期成熟影响，不能当作新客渠道变化。

[完整筛选](reports/anomaly_flags.csv)、[经营拆解](reports/decomposition.csv)、[维度贡献](reports/dimension_contributions.csv)、[覆盖核对](reports/case_category_coverage.csv)与[验收](docs/t4_validation.md)均可追溯。T4.1–T4.4 done（工程验收，本人解释未代验）；只是回顾性探索和代数定位，未证明原因或上线收益。T2.3的[原始v1](reports/business_decision_memo_v1_t23.md)逐字保留，[v2](reports/business_decision_memo.md)记录修订原因。

本轮只通过既有选择器读取31行日指标和6,879行维度日指标，不读事实/用户日/路径/CSV，不启动Spark；无依赖安装或旧数据重建。一个运行入口为scripts/run_diagnosis.py；方法和复跑边界见验收文档。T4.5、T5及其他扩展不自动执行，G0/G1不自动勾选。
