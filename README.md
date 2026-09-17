# 电商实验分析与指标异动诊断平台

分析课题：**电商增长分析与实验可信性验证**。计划用 SQL、Python 和 Spark 建立可核验的电商行为指标，解释指标变化，再通过离线校验与独立公开实验来源数据评估分析方法。

## 当前状态

S0、T0.1、T0.2、T0.3 已完成工程验收。REES46 10 月原始文件和两份 100,000 条头部工程样本保留；完整源扫描实测 42,448,764 条，新增固定用户候选含 151,121 用户、2,114,081 条事件，源与候选均观察到 10 月全部 31 天。这是可追溯输入准备，尚未运行正式业务 ETL、实验分析或性能基准。Criteo 来源验收后移未取消，整个 T0.4 与 G0 仍未完成。状态见 [任务清单](TASKS_v4.md)，完整结果见 [整月输入验收](docs/t04_rees46_month_validation.md)，原获取和环境证据见 [首次 REES46 验收](docs/t04_rees46_validation.md)及 [T0.3 验收](docs/t03_validation.md)。

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

T1.1 已达工程完成条件，本人解释未代验。固定 `month-v101-01` 为唯一真实下游批次，复验 run 不重复计入。[日期规则](docs/date_quality_policy.md)分别检查 count/amount 用途；[实际结果](reports/date_quality_gate.csv)为 31 天两类用途均放行、0 天阻断、31 天有维度缺失警告。这仅是 T1.1 使用条件，历史 formal_analysis_release 不改写，候选范围未升级，T1.3/T1.4 指标验收尚未进行。

复用接口为 `etl.fact_registry.FactReader`，必须传入本地登记文件、分析序列、明确日期、用途及预期 scope；任一日期缺失或阻断则拒绝整个请求。amount 用途仍返回全部合格行为，保留两个 eligibility 标记，不提前改变分母。登记按逻辑输入身份识别重跑，拒绝同序列日期重叠；只保证本地串行追加。

配置模板为 `config/fact_access.example.json`，填写后保存至被忽略的 `config/fact_access.local.json`。人工集成测试先于真实读取；只读事实不重跑解析。独立 run、预算、运行命令及 expected/actual/pass 见 [收尾验收](docs/t11_closeout_validation.md)。该阶段预算 2 GiB/保留 150 GiB，原始收据、文件清单与人工数据仅留本机。

## T1.2 重复候选与会话核验

[质量定义](reports/quality_policy.md)在真实运行前冻结：完整九字段规范化键包含Decimal价格，另算原始字符串完全相同的对照；会话按有效用户/session复合键，空session不成组，跨日不重切，观察跨度不解释为停留时长。真实阈值始终为>5000。

Spark SQL 实现在 [重复候选](sql/quality/duplicate_candidates.sql)和[会话统计](sql/quality/session_profile.sql)。运行入口 `scripts/run_quality.py` 使用原 FactReader 和独立新目录；主口径保持全部事件，B/C只作三场景敏感性对照。配置由 `config/quality.example.json` 填写为被忽略的 `config/quality.local.json`；真实运行必须先有同一代码版本的人工通过收据，不能传入人工低阈值。

结果见 [重复汇总](reports/duplicate_summary.csv)、[会话汇总](reports/session_summary.csv)、[全月及逐日敏感性](reports/quality_sensitivity.csv)。用户级明细、实际配置和原始日志不提交。预算、复跑命令、失败修复与守恒证据见 [验收文档](docs/t12_validation.md)。下一项仅建议T1.3正式指标层，须另行授权。
