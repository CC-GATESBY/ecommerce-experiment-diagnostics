# 电商实验分析与指标异动诊断平台

分析课题：**电商增长分析与实验可信性验证**。计划用 SQL、Python 和 Spark 建立可核验的电商行为指标，解释指标变化，再通过离线校验与独立公开实验来源数据评估分析方法。

## 当前状态

S0、T0.1、T0.2、T0.3 已完成工程验收。REES46 10 月原始文件和两份 100,000 条头部工程样本保留；完整源扫描实测 42,448,764 条，新增固定用户候选含 151,121 用户、2,114,081 条事件，源与候选均观察到 10 月全部 31 天。这是可追溯输入准备，尚未运行正式业务 ETL、实验分析或性能基准。Criteo 来源验收后移未取消，整个 T0.4 与 G0 仍未完成。状态见 [任务清单](TASKS_v4.md)，完整结果见 [整月输入验收](docs/t04_rees46_month_validation.md)，原获取和环境证据见 [首次 REES46 验收](docs/t04_rees46_validation.md)及 [T0.3 验收](docs/t03_validation.md)。

仓库目标为 `CC-GATESBY/ecommerce-experiment-diagnostics`，可见性保持 **private**。仓库同步只包含审查过的文件，不表示全部本地文件、数据或运行环境已经上传。

T1.1 的旧 100,000 条工程样本子任务已通过：39 列事实 Parquet 保留原始字段及质量标记，标准库独立核验与两个独立 run 重跑一致。范围仅为 2019-10-01 00:00:00–04:28:27 UTC；整月候选未解析，T1.1 整体仍为 `in_progress`。见 [工程验收摘要](docs/t11_engineering_validation.md)与[质量表](reports/data_quality_engineering.csv)。

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

按已授权的顺序调整，Criteo 暂后移，REES46 工程解析按该数据线独立验收。T1.1 工程子任务的实际结果见下；整月候选继续等待明确授权。T1.1 整体、T1.5 与总 G0/G1 不提前完成。


## T1.1 工程样本事实层

仅使用第一份旧 100,000 条工程样本（约四小时），解析契约见 [event_parsing_contract.md](docs/event_parsing_contract.md)，schema 见 [events.sql](sql/ddl/events.sql)，实际结果见 [T1.1 工程验收](docs/t11_engineering_validation.md)。原始九字段保留为字符串；UTC 时间、Decimal(18,2) 和质量标记是新增列。不得用此范围推断整日或整月业务表现。

保留原有 `config/local.yaml` 环境绑定，单独填写 `config/events.example.yaml` 并保存为被忽略的 `config/events.local.yaml`。输入从 `data/manifest.json` 第一份工程样本定位；创建 `.local/t11/runs` 后填写输出根目录。模板不能直接运行，入口拒绝其他样本、目录通配符和整月候选。以下命令从实际项目根目录执行，两个 run ID 必须从未使用：

```sh
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" "scripts/run_events.py" --config "config/events.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-new-01"
".venv/bin/python" "scripts/run_events.py" --config "config/events.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-new-02" --compare-run-id "engineering-new-01"
```

测试含一个人工小文件 Spark 集成测试，需要允许本机 Python/JVM 回环端口通信。启动脚本沿用专用 `.venv` 和 JDK 17，以 local[4]、Driver 4g、32 个 shuffle 分区和 UTC 运行，不启用 Hive。独立标准库预期在启动 Spark 前计算；全部字段及重复重数、schema、聚合与金额精确核验通过且 Spark 正常停止后才发布 `complete`。两次输出独立保存；已有 run ID 会报错。原始字段、Parquet、期望侧文件、真实配置和收据仅留 `.local/`。该核验不替代 T1.4 DuckDB 验收。
