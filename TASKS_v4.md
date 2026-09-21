# TASKS v4｜每日执行与验收清单

配套：`plan_v4.md`（完整规格）与 `CODEX_START_v4.md`（协作约束）。

**本轮更新（2026-09-19）：computers六日商品构成定向核查done（工程与业务补充，本人解释未代验）。记录数量及两期购买商品组合变化的证据强于同商品金额下调；优先收窄到B六日记录与规格对账，以A单日集中为基准核查对照。不进入价格实验/T4.5/T5。**

**历史更新（2026-09-18）：11月14–18日购买记录限定核查done（证据定位及报告使用限制；本人解释未代验）。零/峰值已存在于公开源，同哈希候选与指标一致；现实交易与记录机制仍无法区分。旧结果不改，不自动进入computers商品、T4.5或T5。**

**上一轮更新（2026-09-18）：T4业务增强（10–11月持续性及品类差异）done，工程及报告交付，本人解释未代验。旧十月结果不改；优先核对11月15–17日总体购买事件覆盖/时间，再对computers偏弱日期定向查SKU构成。不进入其他月份、T4.5或T5。**

P0＝投递核心；P1＝完整增强；P2＝延后扩展。完整目标=P0+P1。MRC尚未确认不阻塞本地；Hadoop尚未跑通不得填入实践成果。

## S0 仓库初始化（本轮恢复）

- [x] 已确认实际本地目录；目录名末尾保留一个 U+0020 空格，未重命名。
- [x] 初始化前本目录及父目录不属于 Git 仓库，无已有历史或 origin；已在本目录执行 `git init -b main`。
- [x] 已重新核验活动 GitHub 账号为 `CC-GATESBY`；目标仓库 API 返回 404，账号仓库列表无同名目标。
- [x] 已读取本地 `CODEX_LOCAL_GITHUB_BOOTSTRAP.md`；旧路径按用户本轮说明纠正，文件本身不提交。
- [x] 已建立 `.gitignore`、README、AGENTS 与 `docs/local_scope.md`；T0.1、T0.2 产物未重新生成。
- [x] 完成忽略规则与暂存审查，创建首个安全提交；27 个排除路径与 15 个允许路径检查通过。
- [x] 创建 private 仓库、首次 push 成功；本地、远程 main 与 GitHub API 的 SHA 一致，10 个文件的远程 Git 对象与本地一致。

状态：`done`　run_id：`s0-resume-20260916T094342Z`　实际完成日期：`2026-09-16`　阻塞：`无`

上一轮 `runs/bootstrap_receipt.md` 原样保留为历史记录；本次收尾记录保存在本地 `runs/s0_receipt.json`。这些原始记录不提交。T0.1、T0.2 段落保留上一轮验收内容，其中当时的 S0 缺文件情况已解决。

首次同步的提交为 `9071c17cc2f7b71a3f3fcad9ddc08fc2bc219af4`，核验时间为 2026-09-16 09:50:05 UTC。仓库：[CC-GATESBY/ecommerce-experiment-diagnostics](https://github.com/CC-GATESBY/ecommerce-experiment-diagnostics)，可见性 private，分支 main。此状态更新提交后的最终 HEAD 与远程 SHA 记录在本地收尾收据及交付回复中。

## 今晚先执行

- [x] T0.1：只冻结项目范围，不继续扩充数据集。
- [x] T0.2：记录本机真实配置与MRC状态。
- [x] T0.3：固定环境，跑通小型Spark读写。
- [x] T0.4：验收当前所需数据文件，记录来源与校验（工程验收，本人解释未代验）。
- [x] T1.1（小样本子任务）：读CSV、标记质量、写Parquet、读回；用小型工程核对表做独立核对。历史验收已通过。

上述子任务完成不等于完整T1.1/T1.3/T1.4全部完成；正式任务按下表核对。

## 任务总表

| 勾选 | 编号 | 级别 | 任务 | 前置 |
|---|---|---|---|---|
| [x] | T0.1 | P0 | 冻结目标、证据边界与首版范围 | 无 |
| [x] | T0.2 | P0 | 确认真实资源并选定一个主环境 | T0.1 |
| [x] | T0.3 | P0 | 仓库、版本锁定与最小 Spark 验证 | T0.2 |
| [x] | T0.4 | P0 | 数据来源验收与不可变原始区（工程验收，本人解释未代验） | T0.3 |
| [x] | T1.1 | P0 | 解析事实表并保留质量标记（工程验收，本人解释未代验） | T0.4（REES46 分数据线放行） |
| [x] | T1.2 | P0 | 重复候选与会话分布核验（工程验收，本人解释未代验） | T1.1 |
| [x] | T1.3 | P0 | 建设统一口径的指标层 | T1.1、T1.2 |
| [x] | T1.4 | P0 | 独立交叉核验与重复运行测试（工程验收，本人解释未代验） | T1.3 |
| [x] | T1.5 | P0 | 冻结10月首版分析范围（本人解释未代验；双月可选） | T1.4 |
| [x] | T2.1 | P0 | 区分行为覆盖与顺序漏斗（工程验收，本人解释未代验） | T1.5 |
| [x] | T2.2 | P0 | 行为分析与阶段业务总结（工程验收，本人解释未代验） | T2.1 |
| [x] | T2.3 | P0 | 完成一页业务决策备忘录（工程验收，本人解释未代验） | T2.2 |
| [x] | T3.1 | P0 | Criteo 稳定身份与封存划分（工程验收，本人解释未代验） | T0.4、T0.3 |
| [x] | T3.2 | P0 | 真实实验来源数据总体评估（工程验收，本人解释未代验） | T3.1 |
| [ ] | T3.3 | P1 | 有限的描述性异质性分析 | T3.2 |
| [x] | T3.4 | P0 | 编写下一轮业务实验设计（历史基准＋条件式实验设计；未上线，本人解释未代验） | T2.3、T3.2 |
| [x] | T4.1 | P0 | 实现可解释的候选异动检测 | T1.5 |
| [x] | T4.2 | P0 | 保持恒等式的三因子变化拆解 | T4.1 |
| [x] | T4.3 | P0 | 维度贡献与分布变化排序 | T4.2 |
| [x] | T4.4 | P0 | 形成一个真实日志观察案例 | T4.1、T4.2、T4.3、T2.2 |
| [ ] | T4.5 | P1 | 人工故障注入与恢复验证 | T4.4、T1.4 |
| [x] | T5.1 | P0 | 构建固定前置期用户队列 | T1.5 |
| [x] | T5.2 | P0 | 稳定分组与SRM质量检查 | T5.1 |
| [x] | T5.3 | P0 | 实现统一统计结果接口 | T5.2 |
| [x] | T5.4 | P0 | 完成基础A/A校准报告 | T5.3 |
| [x] | T5.5 | P0 | 已知效应注入与可复现单次评估 | T5.3 |
| [ ] | T5.6 | P1 | CUPED调整与方差口径校准 | T5.3、T5.4 |
| [ ] | T5.7 | P1 | 功效曲线及适用条件报告 | T5.5、T5.6 |
| [ ] | T6.1 | P1 | 独立验证HDFS/YARN环境 | T1.4、T0.2 |
| [ ] | T6.2 | P1 | 通过YARN完成一条真实指标作业 | T6.1、T1.4 |
| [ ] | T6.3 | P1 | 完成两项受控性能对照 | T1.5 |
| [ ] | T7.1 | P0 | 生成可追溯README与运行手册 | T2.3、T3.2、T3.4、T4.4、T5.4、T5.5 |
| [ ] | T7.2 | P0 | 简历证据映射与阶段完成审查 | T7.1 |
| [ ] | T7.3 | P0 | 理解验收与现场修改练习 | T7.2 |
| [ ] | E1 | P2 | 训练响应/S/T三个有限基线 | T3.1、T3.3、T7.1 |
| [ ] | E2 | P2 | 冻结方案后评价留出排序 | E1 |
| [ ] | E3 | P2 | 条件化投放建议与方法迁移说明 | E2 |
| [ ] | E4 | P2 | 有授权时迁移学校云或HPC | T1.4、T0.2 |

## 每项验收与证据路径

### T0.1 冻结目标、证据边界与首版范围（P0）

- [x] 文档已生成并记录实际输入范围（仅规划文档与本机只读检测，无业务数据）。
- [x] 每条岗位要求对应至少一项拟交付证据；所有尚未执行的结果标记 planned/not_run；没有“已处理上亿条”“已提升转化率”等预填成果。
- [x] 证据已保存：`docs/project_brief.md`；`docs/jd_mapping.md`
- [ ] 能独立解释：为什么使用两份数据？为什么真实行为变化不等于策略因果效果？

状态：`done`（文档与命令验收；本人解释项未代验）　run_id：`bootstrap-20260916T085801Z`　实际完成日期：`2026-09-16`　阻塞：`无；S0 缺文件不阻塞本项文档`

### T0.2 确认真实资源并选定一个主环境（P0）

- [x] 文档已生成并记录实际输入范围（仅规划文档与本机只读检测，无业务数据）。
- [x] 环境记录来自实际命令；MRC 状态为 available/blocked/unverified 之一并说明依据；不共享密钥；不同时维护本地、MRC 和 Spartan 三套主环境。
- [x] 证据已保存：`docs/environment.md`；`runs/environment_snapshot.txt`
- [ ] 能独立解释：哪些资源属于本机，哪些属于云项目？为什么存储后端与计算运行方式要分开配置？

状态：`done`（文档与命令验收；本人解释项未代验）　run_id：`bootstrap-20260916T085801Z`　实际完成日期：`2026-09-16`　阻塞：`无；S0 缺文件不阻塞本项文档`

### T0.3 仓库、版本锁定与最小 Spark 验证（P0）

- [x] 已实现并记录实际输入范围。
- [x] 小型 Parquet 写入、读回及聚合均成功；执行器和 Python 包 Spark 版本一致；配置缺失时报错；raw、私钥、token、临时数据不入 Git。smoke 只能证明基本环境，不能代表全量性能。
- [x] 证据已保存：`config/local.yaml`；`requirements.lock.txt`；`scripts/smoke_spark.py`；`tests/test_config.py`；`.gitignore`
- [ ] 能独立解释：local[4] 的含义是什么？为什么 JVM 堆不等于总进程内存？

状态：`done`（工程验收；本人解释未代验）　run_id：`t03-20260916T100642Z`　实际完成日期：`2026-09-16`　阻塞：`无`

Git 子项记录：已完成独立 `main` 分支初始化、忽略规则与提交审查、private 远程仓库创建、首次提交及 push，并通过 SHA 和远程文件树核验。本轮补齐专用 Python 3.11.15 / JDK 17.0.19 / PySpark 与 Spark JVM 3.5.8；实际锁导出、17 项配置测试和两次各 23 项 smoke 断言均通过。本人解释框仍未勾选。

本轮证据：`docs/t03_validation.md`、`config/local.example.yaml`、`scripts/project_config.py`、`scripts/run_smoke.py`；本机配置、日志、人工 Parquet 和收据均被忽略。原 T0.2 环境文档未改。T0.4 与 G0 仍未完成。

### T0.4 数据来源验收与不可变原始区（P0）

- [x] REES46 当前文件子任务：核对原发布链与条款，取得原发布方 `2019-Oct.csv.gz`，登记压缩包与解压 CSV，分别记录大小、SHA256、获取时间及关系。
- [x] REES46 原始文件可定位且校验值可复查；表头与数据记录分开；重复登记和同内容换名被识别，同名异内容拒绝；失败下载不能登记完整。首次获取时完整行数、完整时间范围为 `not_measured`；本轮补充实测见下文，原获取验收记录保留。
- [x] 头部工程样本两次各 100,000 条、9 字段，逐字段与源前缀相同，样本 SHA256 一致；37 项单测和 34 项真实产物独立检查通过。样本不是随机样本，不支持总体结论。
- [x] 证据已保存：`data/MANIFEST.md`；`data/manifest.json`；`ingest/ingest.py`；`tests/test_ingest.py`；`docs/data_sources.md`；`docs/t04_rees46_validation.md`。本机配置、原始数据、样本与原始日志未提交。
- [x] Criteo 子任务：官方 corrected v2.1身份、字段、CC BY-NC-SA 4.0条款已核实；完整gzip与CSV分别实测SHA/bytes，13,979,592条/16列，双实现四字段计数一致，空值/非法/非有限值均0。只读raw与重复登记保护通过。
- [x] Criteo增量证据：`ingest/ingest_criteo_source.py`、`tests/test_criteo_source.py`、`docs/criteo_source_validation.md`、`reports/criteo_source_profile.csv`及独立manifest来源条目；raw未入Git。
- [ ] 能独立解释：如何证明这次处理的数据是哪一版？为什么不能以文件名当作唯一标识？

状态：`done`（工程验收，本人解释未代验；REES46与Criteo来源均通过）　Criteo run_id：`criteo-v21-2026-09-17T095629.361727_0000`　整项工程完成日期：`2026-09-17`　剩余：`本人解释未代验；项目G0/G1门槛另审`

历史：REES46获取run `rees46-oct-20260916T104053Z-4e081494` 于2026-09-16通过时，Criteo尚未开始；以下保留该阶段及后续REES46覆盖检查的历史记录，不代表本轮仍阻塞。

此前获取子任务的源文件下载载荷为 1,741,928,540 bytes，解压 CSV 为 5,668,612,855 bytes；不是仅下载 100,000 行。头部工程样本时间范围为 2019-10-01 00:00:00–04:28:27 UTC，解析失败 0 条。Kaggle 目录版本 8 已核实，但原发布方外链对象没有独立版本号，未与 Kaggle 文件逐字节比较。当时整月 ETL、事实 Parquet、业务指标和 T1.1 均未运行；本轮 T1.1 工程子任务另记如下。G0 继续未勾选。

本轮补充子任务顺序：先完成 REES46 全文件覆盖核验与固定用户样本候选准备，Criteo 来源验收暂后移但不取消。该输入准备不等于 T1.5 正式扩量通过；后续 REES46 受控工程解析可按本数据线验收独立推进，不必等待 Criteo。整个 T0.4、T1.1、T1.5 与总 G0 均不因此提前勾选。规则已先冻结于 `docs/analysis_sampling.md`。

- [x] 完整源覆盖核验：42,448,764 条数据记录；2019-10-01 00:00:00–2019-10-31 23:59:59 UTC；31 天、744 小时均有记录。结构、时间、ID 缺失/不可使用及窗口外异常均为 0；每天有记录不证明上游无漏数。
- [x] 固定用户候选准备：种子 20260916、用户哈希目标 5%；151,121 个样本用户、2,114,081 条事件，实际事件比例 4.980312%，全量不同用户数未测。候选覆盖 10 月全部日期，尚未通过正式业务质量门禁。
- [x] 先通过 52 项新旧测试，再扫描和重读；字段、顺序、计数与内容哈希均核对通过，另有 25 项收尾检查。只生成一份 282,405,091 bytes 的整月候选 CSV；原 CSV 和旧样本未变。
- [x] 增量证据：`docs/t04_rees46_month_validation.md`、`docs/analysis_sampling.md`、三份 `reports/*_coverage.csv`、`data/manifest.json`；run_id `rees46-oct-user5-20260916`，本轮输入准备子任务 `done`，整项 T0.4 仍为 `in_progress`。

附加资源测量限制：`time -l` 在程序完成后查询 sysctl 被系统权限限制，包装命令返回 1；源扫描和候选验证已有完整成功收据，程序计时共 161.674 秒。峰值内存记 `not_measured`，未重跑生成第二份样本。下一步先用旧 100,000 条工程样本验证 T1.1，再获授权处理整月候选；本人解释框与总门槛保持未勾选。

### T1.1 解析事实表并保留质量标记（P0）

- [x] 已实现并记录实际输入范围：旧工程样本及本轮唯一登记的整月用户候选。
- [x] 记录守恒和字段保留：输入记录数=事实层记录数；无静默丢弃，原字段和重复重数保留。引用工程/整月验收。
- [x] 金额与时间解析：UTC、Decimal(18,2)、精度异常有标记；引用 v1.0.1 边界修复和工程回归。
- [x] 独立核验与重跑：整月两轮全量多重集、逐日核对通过；引用历史 66/71 项收据，不重复制造结果。
- [x] 日期质量规则及读取端执行：按日期、按 count/amount 分别放行；受控读取实际拒绝缺失/阻断范围。见 `docs/t11_closeout_validation.md`。
- [x] 人工跨月追加与防重复登记：同一分析序列新增 11 月不改变 10 月；同逻辑输入换 run 不新增；冲突/半成品拒绝，旧批次仍可读。
- [x] 证据已保存：`etl/01_events.py`；`sql/ddl/events.sql`；本地独立 scope/run 事实 Parquet；`reports/data_quality_month.csv`、`reports/data_quality_daily.csv`、`reports/month_parsing_checks.csv`。
- [ ] 能独立解释：哪些字段无效会阻止哪一种分析？为什么缺失 session 不应让该用户所有行为被删除？

状态：`done（工程验收，本人解释未代验）`　旧工程 run_id：`engineering-20260916-03`、`engineering-20260916-04`　工程及整月子项验收日期：`2026-09-16`　工程收尾日期：`2026-09-17`　剩余：`工程无剩余缺口；本人解释仍待确认`

- [x] `engineering_sample` 子任务通过：仅清单第一份旧样本，100,000 条、SHA256 `fe2cd808172c853217201660a98a8c8600fb0230f5c89efda45a9a1a2fdae754`；范围为 2019-10-01 00:00:00–04:28:27 UTC。未读取整月候选或重扫完整源。
- [x] 先预检价格并冻结 Decimal(18,2)；全部原始九字段、来源、范围、运行信息与质量标记保留，事实输出 100,000 条，无隔离、无去重。异常输入留原值并标记；CSV 结构错误失败且不发布完成。
- [x] 73 项测试（原有 52、新增 21）通过，包含 36 条独立 synthetic Spark 边界数据；标准库预期先于 Spark 计算。最终两个 run 分别通过 29、33 项断言；全字段多重集、UTC、Decimal、计数与金额精确相同，重跑前一轮文件未变。
- [x] 工程核对：20,384 用户、1,336 购买用户、1,655 购买事件，观测合格购买金额 501176.21（原 price 单位），状态 complete_observed，仅限四小时样本。缺品类代码 32,587、缺品牌 14,391、零价格 119；不因此删记录。
- [x] 证据：`docs/event_parsing_contract.md`、`docs/t11_engineering_validation.md`、`reports/data_quality_engineering.csv`、`sql/ddl/events.sql`；两次事实 Parquet 和完整收据只留 `.local/t11/`。

此前工程核验不替代 T1.4 DuckDB 正式验收；整月输入在下述历史阶段获单独授权，正式指标仍未放行。当时 T1.1 整体、T1.2–T1.5、T0.4、G0/G1 与本人解释项保持未完成；本轮仅收尾 T1.1 工程项。

历史整月候选解析子任务（旧报告和输出保留）：

- [x] 边界修复和工程回归 `passed`：先复现 oracle 连续符号 3 例和 Java 行终止锚点 9 例，再固定完整输入匹配；额外修复 CSV 引号内 CR/CRLF 规范化。契约补丁 `rees46-events-v1.0.1`；83 项新旧测试通过。
- [x] `engineering-regression-v101` 47 项检查通过：旧样本原字段/派生值及质量计数不变，20,384 用户、1,336 购买用户、1,655 购买事件及 501176.21 金额与历史完全一致。仅运行信息与明确补丁版本不参与旧/新逻辑比较。
- [x] 整月事实解析 `passed`：输入仍为 `user_sample_candidate`，scope `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`，SHA256 `5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b`；2,114,081 条全部保留，151,121 个原始/合格用户，无隔离、无去重。
- [x] 逐日质量和重跑 `passed`：`month-v101-01`、`month-v101-02` 分别通过 66、71 项检查。31 天记录数与已提交候选覆盖表一致；全量原字段/派生字段/重复重数独立核验及两轮逻辑差异均为 0，旧输出不变。
- [x] 实际工程核对：17,121 购买用户、37,019 购买事件、11598630.22 合法观测购买金额（原 price 单位）。31 天金额状态均为 complete_observed；零价格 3,286 view、6 cart、0 purchase。品类代码缺失 669,421、品牌缺失 299,547，每天均有维度缺失；不代表自动获得正式分析资格。
- [x] `docs/t11_month_validation.md` 与三份脱敏汇总已保存；独立预期、SQLite、Parquet、真实配置和日志仅留本地。新增约 3.75 GiB、运行中磁盘采样高水位约 4.73 GiB；未触及 20 GiB/150 GiB 边界。未安装、下载、重抽样或重扫完整源。
- 历史阶段剩余项：日期质量规则被读取端执行、人工跨月追加。已在下述收尾子任务验收，未引入 11 月真实输入；本人解释项仍不代勾。

本轮收尾（2026-09-17）：

- [x] `rees46-date-quality-v1` 先冻结再实现；31 天 count/amount 均放行、0 天阻断、31 天维度警告。历史 formal_analysis_release=not_granted 不改写。
- [x] 只选 `month-v101-01`，1 次真实 Parquet 加载、2,114,081 行逐日及身份核对通过；`month-v101-02` 登记幂等，不合并复验副本，未重读 CSV 或生成新真实事实。
- [x] 9 项规则单测、17 项原配置测试、53 项人工集成检查、6 项真实读取检查通过。成功人工轮 24 条，连同保留的失败路径测试共 38 条人工 CSV 记录；跨月、用途拒绝、登记失败隔离均实测。
- [x] 原有数据及历史报告保留；新增本地产物未触及 2 GiB/150 GiB 边界。证据：`docs/date_quality_policy.md`、`docs/t11_closeout_validation.md`、`reports/date_quality_gate.csv`。

未实现 T1.2–T1.5 或正式指标/实验，候选未提升为最终分析范围；T0.4/Criteo、总 G0/G1 保持原状态。下一项唯一建议：T1.2 重复候选与会话核验，须用户另行授权。

### T1.2 重复候选与会话分布核验（P0）

- [x] 已实现并记录实际输入范围：唯一 month-v101-01，原整月用户候选scope/series，2019-10-01至10-31 UTC；通过既有FactReader，未读真实CSV。
- [x] 缺失 session 不组成共同会话；有效(user_id,user_session)不跨用户合并，跨日不重切。候选、会话及双标签左连接前后，全月/逐日行数、行为数、用户、购买用户/事件和Decimal金额均守恒。
- [x] B每组留一条、C排除>5000会话只作独立敏感性分析；五项指标全月和逐日重新计算，基线零相对变化为null。未修改或登记为正式事实，未叠加B+C。
- [x] 证据：两个SQL、`scripts/run_quality.py`、`tests/test_quality.py`、`reports/quality_policy.md`、三份脱敏汇总和`docs/t12_validation.md`。
- [ ] 能独立解释：候选重复与真正重复的区别？数据倾斜与数据无效为什么不能混为一谈？

状态：`done（工程验收，本人解释未代验）`　run_id：`quality-month-01`　工程验收日期：`2026-09-17`　剩余：`工程无缺口；本人解释未代验`

- [x] 规范化与原九字段完全相同对照均为892组、2,325条涉及、1,433条超额、638用户；购买4组/8条涉及/4条超额。B金额减少1427.11（−0.012304%），用户及购买用户全月和逐日均不变。
- [x] 有效会话460,550，缺失session事件0；事件数p50/p90/p99为2/10/32，最大350；>5000命中0，C与A全月/逐日完全相同。跨日键1,442，最大观察跨度2,565,947秒，不称停留时长。
- [x] 28项单元/回归、100项人工集成断言、19项真实核验通过。人工两轮共36条，首轮空分支汇总失败及修复保留记录；真实只运行一次，367个既有本地文件元数据无变化，核心输入及收据SHA不变。
- [x] 累计新增产物采样高水位4.140 GiB，最低空闲521.447 GiB，未超5 GiB/150 GiB边界；没有安装、下载、改锁或重建真实事实。

下一项仅建议T1.3正式指标层；本轮不自动执行，不继续扩建质量平台。T0.4/Criteo、T1.3–T1.5及总G0/G1不提前勾选。

### T1.3 建设统一口径的指标层（P0）

- [x] 已实现并记录实际输入范围。
- [x] 主键唯一；无分母时输出 null+状态而非无穷；满足条件的日期有 V=U×(B/U)×(V/B) 恒等式核验；每个维度金额加总等于同范围总金额；同一报告注明金额缺失范围。
- [x] 证据已保存：`docs/metric_contract.md`；`sql/metrics/`；`docs/t13_validation.md`；`reports/daily_metrics_preview.csv`；`reports/metric_checks.csv`；四层Parquet仅本地独立run
- [ ] 能独立解释：购买事件、购买会话、购买用户分别是什么？金额/购买用户和金额/订单为什么不同？

状态：`done`（工程验收，本人解释未代验）　run_id：`metrics-month-01`　实际完成日期：`2026-09-17`　工程阻塞：`无`

人工18条，4项指标单元、9项日期规则、17项配置回归通过；人工40项场景、75项首轮、75项重跑、52项空输入检查通过。真实433项核验通过；151,121用户、17,121购买用户、37,019购买事件、11598630.22观测购买金额保持主口径。品牌映射基于10月1–7日冻结200个；31天计数与金额均放行，维度缺失保留unknown。未读取真实CSV或改写事实/登记/旧质量表，输入候选未升级为最终范围。下一项仅建议T1.4 DuckDB独立核验，不提前完成T1.4/T1.5/Criteo或总G0/G1。

### T1.4 独立交叉核验与重复运行测试（P0）

- [x] 已实现并记录实际输入范围。
- [x] 行数、去重用户数、购买事件数一致；Decimal 金额按同一精度精确核对；派生浮点比率用预设容差。原始过滤范围不同必须解释并修复，不能通过扩大容差掩盖。重跑结果不翻倍，历史分区不消失。
- [x] 证据已保存：`tests/crosscheck_duckdb.py`；`tests/test_idempotency.py`；`reports/crosscheck.csv`
- [ ] 能独立解释：两个系统数字相等为什么仍可能一起错？什么叫独立实现与相同口径？

状态：`done`（工程验收，本人解释未代验）　run_id：`crosscheck-month-01`　实际完成日期：`2026-09-17`　工程阻塞：`无`

实际范围：仅已登记2,114,081条整月固定用户候选；四层151,121/322,660/31/6,879行及200条品牌映射，键、类型及99项字段比较差异均0，金额最大差0.00，三个比率最大绝对/相对差0。31天独立质量与历史一致；10月5日单独保留完整UTC日证据。4项单元和150项最终人工集成通过，真实DuckDB运行一次。复用真实build/publish验证不可变快照，不声称物理分区append或分布式事务。

新增证据：`docs/t14_comparison_contract.md`、`docs/t14_validation.md`、`reports/crosscheck_daily.csv`、`sql/validation/`。仅新增DuckDB 1.5.5到项目环境，实际锁单项变化、pip check通过；旧事实、指标、登记及T1.3报告不改。下一项仅建议T1.5冻结首版分析范围，未执行；Criteo/T0.4及总G0/G1未完成。

### T1.5 按验收扩量并冻结分析范围（P0）

- [x] 已实现并记录实际输入范围。
- [x] 范围包含足够的历史日期以支持拟用基线；每次扩量仍通过核心核验；运行规模均来自记录。头部行样本只作工程测试，不用于总体行为结论。
- [x] 证据已保存：`config/analysis_scope.yaml`；`.local/t15/freeze-oct-v1/complete/etl_baseline.json`（仅本机等价收据）；`reports/scale_baseline.md`
- [ ] 能独立解释：为何用户抽样保留轨迹，而逐行抽样会改变会话与转化路径？

状态：`done`（10月首版范围冻结；本人解释未代验）　run_id：`freeze-oct-v1`　实际完成日期：`2026-09-17`　工程阻塞：`无`

本轮明确范围决定：原v4双月目标保留，首版仅十月固定用户；11月及更多用户为以后可选扩展，未执行且不属本首版完成条件。原candidate scope/manifest不重命名，以analysis_scope `rees46_oct_user5_analysis_v1`引用批准用途。31天日指标可用；24小时路径起始view只用1–30日，31日保留结果观察与总体指标；探索诊断只在22–31日有至少3点的声明日期内准备，29–31日有4点，状态history_available_not_evaluated。前置[10月1日,15日)、结果[15日,29日)仅检查窗口，队列未生成。

18项新配置/日历与4项原接口单元通过；轻量完成证据和31行日表核对通过。四表151121/322660/31/6879行引用原收据；66个Parquet文件平铺、非日期分区。不读CSV、不启动Spark、不重算ETL/指标。证据：`docs/t15_validation.md`、`reports/history_readiness.csv`、`reports/scale_baseline.md`。REES46分数据线具T1.1–T1.4工程证据，Criteo和本人解释不代验；下一项仅建议T2.1。

### T2.1 区分行为覆盖与顺序漏斗（P0）

- [x] 已实现并记录实际输入范围：analysis_scope首版，唯一month-v101-01，十月31天合格事件。
- [x] 行为覆盖与路径粒度分开；首次view全月每有效复合键一个起点，24小时窗口、严格/可能类别、同秒不确定、跨日/末日和重复事件均通过人工及真实核验。
- [x] 证据已保存：`sql/metrics/behavior_coverage.sql`、`sql/metrics/funnel_paths.sql`、`sql/metrics/funnel_summary.sql`、`reports/funnel_definition.md`、四份脱敏CSV、`docs/t21_validation.md`；路径明细仅在被忽略的`.local/t21/funnel-month-01/complete/analysis/funnel_paths/`。
- [ ] 能独立解释：为什么三类行为人数不能直接相除当顺序漏斗？为什么“没观察到加购”不等于没有加购？

状态：`done（工程验收，本人解释未代验）`　run_id：`funnel-month-01`　实际完成日期：`2026-09-17`　阻塞：`无工程阻塞；范围与解释限制见验收文档`

定义先冻结；86条人工事件得到33条路径，与独立标准库穷举逐字段一致。31项配置/日期回归、303项人工检查通过。首次人工空输入失败已修复，旧失败产物保留；真实一次执行，623项检查通过。读取2,114,081事件，建立1,382,516路径；正式1,341,998，右端观察不足40,426，同秒不确定92。正式三步15,112、无确认中间cart的购买18,212、仅后续cart15,741、仅view1,292,933；购买审计37,019，日/价格桶守恒和Parquet全内容读回通过。

原事实、指标、范围配置和绑定证据未改写；不读CSV、不扩量、不装依赖、不重新生成T1.3。T1.5历史冻结记录保留，未进入T2.2/T2.3或其他模块。下一项唯一建议T2.2行为分析与阶段业务总结，须另行授权。

### T2.2 行为分析与阶段业务总结（P0）

- [x] 已实现并记录实际输入范围：analysis_scope首版、唯一month-v101-01 / metrics-month-01 / funnel-month-01、baseline_keep_all。
- [x] 每张图附数据范围、粒度、来源表、分母及一句可验证结论；每个报告数字可追溯到CSV/Parquet；不将相关、价格带差异或首次观察用户解释成业务因果。
- [x] 证据已保存：`reports/behavior.md`；`reports/period_summary.md`；`reports/figures/`；`docs/t22_validation.md`。
- [x] 日/漏斗复用历史证据，品类金额保留unknown；仅一次Spark受控小时聚合，24桶精确对账。39项先行单元/回归、2项报告补验、894项准备、97项小时及791项独立CSV断言通过；8张图逐张检查。
- [x] closeout获明确授权后，从唯一事实run一次聚合补齐14桶月去重users/buyers；原user_days/buyer_user_days保留。每桶事件/购买/金额精确对账，人工跨日/跨品类/unknown与真实非加性核验通过，非相加改名。
- [ ] 能独立解释：给业务同事一分钟，最重要的发现是什么？它影响哪些人或商品？

状态：`done（工程验收，本人解释未代验）`　run_id：`behavior-month-01 / hourly-month-01 / category-month-01`　实际完成日期：`2026-09-17`　阻塞：`无未解决工程缺口`

closeout证据：8项新单元、18项报告/旧汇总回归、88项实际运行检查（含人工SQL）、792项独立CSV/旧图检查通过。electronics月users=84077/用户日156714，月buyers=9902/购买用户日15196；unknown月users=75652、buyers=5201。仅补CSV三列及必要报告段落，原图无重绘、原小时无重算、T1.3/T2.1无重跑。详见docs/t22_validation.md的closeout记录。

本轮三项描述性观察：日金额极值与U/R/M不同步；formal路径96.34%仅观察到view，非永久流失；electronics占75.44%、unknown占10.42%的金额结构需连同覆盖解释。UTC小时峰值不解释当地作息。未读真实CSV、重建事实/指标/漏斗、改口径或装依赖；既有数据与报告不改写。后续唯一建议为T2.3一页业务决策备忘录，尚未实施。

### T2.3 完成一页业务决策备忘录（P0）

- [x] 已实现并记录实际输入范围：唯一rees46_oct_user5_analysis_v1，仅既有脱敏报告/CSV及范围配置。
- [x] 建议含具体对象、下一步操作、所需证据和验证方式：unknown+electronics编码模式/来源覆盖/日期稳定性；字段规范与映射；核对解释前后金额结构。当前暂不调整价格、流量、商品或漏斗策略，无虚构收益。
- [x] 证据已保存：`reports/business_decision_memo.md`、`reports/business_decision_memo_evidence.csv`、`docs/t23_validation.md`。
- [ ] 能独立解释：为什么先做这项而不是其他项？什么新证据会改变你的建议？

状态：`done（工程验收，本人解释未代验）`　run_id：`memo-electronics-unknown-v1`　实际完成日期：`2026-09-17`　阻塞：`无未解决工程缺口`

851汉字首稿，4个替代解释及条件式决策；20条来源登记、60项引用/结构检查、12项回归测试通过。仅Python标准库复读已提交脱敏CSV，未启动Spark/DuckDB、读取用户级数据或生成新切片。本轮不更新T4.4最终案例，未来修订须保留首稿和原因。后续T3公开实验线、T4异动诊断或T5实验模拟由总体项目顺序另定，不自动执行。

### T3.1 Criteo 验收并提前封存划分（P0）

- [x] 唯一corrected v2.1 raw身份重新核实：13,979,592条、3,248,115,221 bytes，CSV SHA/header不变；T0.4 manifest/registry不改。
- [x] 先冻结源SHA＋逻辑ordinal身份及treatment分层整数hash阈值；seed 20260917，不使用outcome/exposure/features，不改变原treatment。
- [x] 单份确定性gzip membership全量生成并逐条独立核验：train 8,387,273、valid 2,797,762、test 2,794,557；两个arm及source四字段守恒，整体与9个序列digest一致，6个占比保护线通过。
- [x] 45项人工/来源回归及25项真实检查通过；跨进程复现、拒绝覆盖及失败隔离通过。首次发布权限顺序错误保留失败记录，修正后核对原产物并发布，未重划/改seed。
- [x] test封存纪律、T3.2预声明全量总体aggregate例外和label-rate QC边界已记录；不把0.85当精确原实验分流概率，不做SRM声明。
- [x] 证据：`uplift/ingest_criteo.py`；`uplift/split.py`；`tests/test_criteo_split.py`；`docs/criteo_split_contract.md`；`reports/criteo_manifest.md`；`reports/criteo_split_summary.csv`；`data/criteo_split_manifest.json`；`docs/t31_validation.md`。逐条membership仅留本地。
- [ ] 能独立解释：为什么先封存测试集再探索特征？为什么Criteo不能和REES46按用户拼接？

状态：`done`（工程验收，本人解释未代验）　run_id：`criteo-split-v1-01`　实际完成日期：`2026-09-17`　未解决工程阻塞：`无`；T3.2–T3.4未执行，下一项仅建议T3.2，不自动开始。

### T3.2 先完成真实实验来源数据的总体评估（P0）

- [x] 唯一corrected v2.1源一次Spark聚合为treatment两行；13,979,592条全部作为assigned分母，不筛exposure，不查看split效果。
- [x] 分母明确、低频条件检查、20条人工数据/18项测试及独立公式核验通过；报告名称优先用“公开基准的组间差异/增量估计”，并说明RCT来源与发布抽样限制，不能恢复原广告主收益或把它当补贴效果。
- [x] 证据：`uplift/ate.py`；`tests/test_criteo_ate.py`；`reports/criteo_effects.csv`；`reports/criteo_ate.md`；`reports/criteo_business_summary.md`；`docs/t32_validation.md`。绝对/相对/每万人量级及区间已区分，成本和收益缺口明确。
- [ ] 能独立解释：为什么看 treatment 而不只看实际曝光者？CI跨零与证明无效果的区别？

状态：`done`（工程验收，本人解释未代验）　run_id：`criteo-itt-v1-02`　实际完成日期：`2026-09-18`　工程阻塞：`无`；商业成本/价值等数据未提供，不能作ROI或预算决策。下一项仅建议T3.4，未执行。

### T3.3 有限的描述性异质性分析（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 切片只基于基线特征；稀疏组不输出虚假精确结论；显著性探索采用预定的多重比较说明；不把“A显著B不显著”当作两组效果显著不同。
- [ ] 证据已保存：`uplift/hetero.py`；`reports/criteo_heterogeneity.md`
- [ ] 能独立解释：描述性分层、CATE建模、正式异质性检验有什么区别？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T3.4 编写下一轮业务实验设计（P0）

- [x] 查询前冻结首个cart的24+24小时规则；唯一analysis_scope与month-v101-01一次真实事实加载，历史资格7,856人、购买255人、金额完整。没有更换等待时长或寻找第二起点。
- [x] 主指标为全部分配用户的24小时购买用户率，含未返回者；上线前券与触达许可、支付/退款/取消、净贡献和长期护栏仍待补。1:1、alpha=0.05、power=0.8、双侧固定期限均为规划选择。
- [x] 9个样本量情景独立公式复算；9个成本情景按全部兑券购买用户计费。成本门槛与统计MDE分别解释，不把日志金额当利润，不将Criteo或旧路径比例作为本轮基准。
- [x] 证据：`reports/next_experiment_design.md`；`reports/cart_recovery_baseline.csv`；`reports/sample_size_scenarios.csv`；`reports/coupon_economics_scenarios.csv`；`reports/category_coverage_context.csv`；`abtest/sample_size.py`；`sql/experiments/cart_recovery_eligibility.sql`；`scripts/run_cart_recovery.py`；`tests/test_cart_recovery.py`；`docs/t34_validation.md`。
- [ ] 能独立解释：为什么随机化单位这样选？上线、继续验证、无足够证据分别需要什么条件？

状态：`done`（历史基准＋条件式实验设计；未上线，本人解释未代验）　run_id：`cart-baseline-02`　实际完成日期：`2026-09-18`　工程阻塞：`无`；线上成本/触达/护栏待补，未执行线上分流、发送或发券。T3.3/T4/T5与全项目门槛不提前完成。

### T4.1 实现可解释的候选异动检测（P0）

- [x] 已实现：唯一metrics-month-01，analysis_scope=rees46_oct_user5_analysis_v1；只读日/维度日小表。
- [x] 历史不足、零基线、缺分区测试通过；带输出status与reason；阈值在案例筛选前固定；仅金额主筛选，绝对金额只排序，不虚构商业损失门槛。MAD分数不称为已校准的统计显著性，也不预设某天必须报警。
- [x] 证据已保存：`anomaly/diagnose.py`；`config/anomaly.yaml`；`reports/anomaly_flags.csv`
- [ ] 能独立解释：检测阈值和统计显著性有什么不同？为什么先检查数据完整性？

状态：`done`（工程验收，本人解释未代验）　run_id：`diagnosis-oct-02`　实际完成日期：`2026-09-18`　工程阻塞：`无`；本轮为回顾性探索，详见`docs/t4_validation.md`，没有确认业务原因或策略收益。

### T4.2 保持恒等式的三因子变化拆解（P0）

- [x] 已实现：唯一metrics-month-01，analysis_scope=rees46_oct_user5_analysis_v1；只读日/维度日小表。
- [x] 输入有效时log变化相加等于总log变化；份额相加约为1但可以负数或大于1；不适用样例返回状态而不是NaN串；标注这是代数贡献不是因果归因。
- [x] 证据已保存：`anomaly/diagnose.py`；`tests/test_diagnose.py`；`reports/decomposition.csv`
- [ ] 能独立解释：检测基线为什么可以不同于分解基准？份额为负说明什么？

状态：`done`（工程验收，本人解释未代验）　run_id：`diagnosis-oct-02`　实际完成日期：`2026-09-18`　工程阻塞：`无`；本轮为回顾性探索，详见`docs/t4_validation.md`，没有确认业务原因或策略收益。

### T4.3 维度贡献与分布变化排序（P0）

- [x] 已实现：唯一metrics-month-01，analysis_scope=rees46_oct_user5_analysis_v1；只读日/维度日小表。
- [x] 新增类别、消失类别、完全无变化、正负抵消、全零分布测试通过；每个维度所有金额差之和与全局差一致；总差近零或分布不能定义时输出状态。代码名与报告均称简化贡献排序，不称论文完整复现。
- [x] 证据已保存：`anomaly/diagnose.py`；`tests/test_diagnose.py`；`reports/dimension_contributions.csv`
- [ ] 能独立解释：为什么新增类别要outer join？维度贡献为什么不能再相加？

状态：`done`（工程验收，本人解释未代验）　run_id：`diagnosis-oct-02`　实际完成日期：`2026-09-18`　工程阻塞：`无`；本轮为回顾性探索，详见`docs/t4_validation.md`，没有确认业务原因或策略收益。

### T4.4 形成一个真实日志观察案例（P0）

- [x] 已实现：唯一metrics-month-01，analysis_scope=rees46_oct_user5_analysis_v1；只读日/维度日小表。
- [x] 报告数字均能追溯到运行结果；没有“证明由促销/疫情造成”等缺证据表述；没有数据的履约、渠道、库存内容明确标为待核查；候选窗口与因果事故标签分开。
- [x] 证据已保存：`reports/case_observed_change.md`；`reports/business_decision_memo.md`；原稿`reports/business_decision_memo_v1_t23.md`（原证据CSV不变）
- [ ] 能独立解释：你真正定位到了什么？还不能确定什么？给业务团队的下一步是什么？

状态：`done`（工程验收，本人解释未代验）　run_id：`diagnosis-oct-02`　实际完成日期：`2026-09-18`　工程阻塞：`无`；本轮为回顾性探索，详见`docs/t4_validation.md`，没有确认业务原因或策略收益。

### T4定向补充｜computers购买记录与商品组合

状态：`done`（工程及报告交付，本人解释未代验）；run_id：`computers-mix-01`；日期：`2026-09-19`。

- [x] 六天computers事件/购买数/金额与旧品类汇总精确对齐；复用October唯一事实和November只读派生库，不读CSV。
- [x] 商品日表、六天分类检查、四部分互斥金额差及共同商品两项拆解精确守恒；重复保留。
- [x] 主案例负向Top5及正向前2名固定别名跟踪；Top1/Top5用全部负向金额差作分母，另列净差。
- [x] 人工字面预期、独立小表复算、报告/图核对及旧证据保护通过；完整商品/用户身份不入Git。
- [ ] 本人解释：购买记录不是件数；无购买不能补零价格；商品构成差额与同商品金额项为什么都不是调价因果。

证据：[业务报告](reports/computers_product_mix_review.md)、[三份汇总与图](reports/computers_mix/)、[验收](docs/computers_product_mix_validation.md)。六天168个购买商品所见分类均稳定；主案例共同12商品同商品金额项−39.24，不能解释−10,213.70品类净差；Top5仅占全部负向35.92%。业务建议收窄B记录/规格核对，未取得外部交易证据，不扩大样本、查询11月15–17日、执行价格实验/T4.5/T5或更改总门槛。

### T4限定核查｜11月15日零购买与16–17日峰值

状态：`done`（证据定位及使用限制，本人解释未代验）；run_id：`timing-01`。

- [x] 一次源流式扫描及候选重读，SHA/严格结构/固定哈希/原字段顺序重数一致；只分析14–18日。
- [x] 5天日对账、240行源/样本小时表、窗口purchase重复候选核查；原指标/质量规则/报告不改。
- [x] 保留完整11月主结果；27天事后分支及5个受影响后续日期的历史敏感性独立保存，不认定三天无效。
- [x] 业务报告、简短验收、人工边界及检测回归通过；公开源观测形态已确认，真实原因未确认。
- [ ] 本人独立解释：为何源级零购买不是零交易证明；为何均值方向可变而候选不变；为什么敏感性不是修正结果。

证据：[主报告](reports/purchase_timing_review.md)、[汇总](reports/purchase_timing/)、[验收](docs/purchase_timing_validation.md)。最需要同范围交易侧控制总数与发生/入库/补发时间对账；公开数据未提供。本轮结束后另行决定是否查computers，不自动启动下一项，不更新全项目门槛。

### T4业务增强｜10–11月持续性与品类差异（本轮授权补充）

- [x] 同一REES46多品类商店11月官方单文件来源确认、不可变raw、全文件覆盖及固定5%用户规则通过；允许11月新匹配ID，不固定为十月回访名单。
- [x] 11月仅补日U/B/V/R/M与购买计数、category_l1日汇总，原解析/质量/指标口径不变；标准库独立全记录、逐日金额及品类守恒核验通过。
- [x] 全61日、10月4日起全9周五、11月30日筛选完整保留；原阈值和十月25日基准不改。electronics主要随大盘，computers重复相对偏弱但非单向持续。
- [x] 将11月15日零purchase及16–17日峰值列为最高优先对账；未把解析通过、日志零值或金额回升写成业务事故/修复证明。
- [x] 新范围及独立输出：`reports/cross_period_business_review.md`；`reports/cross_period/`；`docs/cross_period_source_scope.md`；`docs/cross_period_validation.md`。原十月scope、指标、案例、收据、manifest、依赖锁和旧图不变。
- [ ] 能独立解释：为什么electronics金额影响大不等于相对更差？零purchase与真实零交易有什么区别？为什么下一步先查15–17日覆盖，再查computers构成？

状态：`done`（工程及业务报告交付，本人解释未代验）　run_id：`nov-source-01 / nov-sample-01 / nov-metrics-02 / review-03`　实际完成日期：`2026-09-18`。未解决业务问题：事件/交易侧覆盖、入库时间及SKU/库存证据待取；未确认原因或策略收益。T4.5/T5和总门槛不自动完成。

### T4.5 人工故障注入与恢复验证（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 原始文件哈希不变；能列出真实移除的记录数/金额和预期受影响范围；报告是否报警、TopK是否命中及恢复后是否回到基准。未命中算方法局限，不调数据到必胜；单案例不报告泛化准确率。
- [ ] 证据已保存：`tests/faults/inject_events.py`；`reports/fault_manifest.json`；`reports/fault_injection.md`
- [ ] 能独立解释：人工测试和真实事故验证有什么不同？为何要从事件层重建指标？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T5.1 构建固定前置期用户队列（P0）

- [x] 仅复用十月metrics-month-01用户日表；前置10月1–14日、结果15–28日UTC，不读取事实或CSV，不启动Spark。
- [x] 每用户一行，前置期独立入组84,165人；返回33,442、未返回50,723、购买4,812。以同一购买人数比较5.7173%与14.3891%，差8.6718个百分点仅为分母选择。
- [x] 身份与数值分开保存、稳定键连接；金额未知与结构零分开；名单/计数/Decimal守恒和Parquet全字段读回通过，旧输入与报告不变。
- [x] 证据：`sql/exp/user_window.sql`；`reports/cohort_definition.md`；`reports/cohort_baseline.csv`；`docs/t51_validation.md`。本地队列在`.local/t51/cohort-oct-01/complete/cohort/`，不提交用户级数据。
- [ ] 能独立解释：为何不能默认只保留实验后活跃用户？当前队列能否代表全部新老用户？

状态：`done`（固定队列与分母验收；本人解释未代验）　run_id：`cohort-oct-01`　实际完成日期：`2026-09-21`　阻塞：`无工程差异；尚无随机处理或实验效果`

本轮结束T4追加调查，原computers报告保留。此队列不是T3.4加购后24小时未购买资格人群；T5.2–T5.5仍未执行，其他门槛不提前勾选。

### T5.2 稳定分组与SRM质量检查（P0）

- [x] 复用cohort-oct-01全部84,165人，SHA256版本/ID/键编码与50:50阈值在真实执行前冻结，不按结果配平。
- [x] 同ID、改变行顺序、跨进程及独立DuckDB实现分配一致；空/重复键拒绝；人工明显失衡触发SRM。真实300次标记0，保留全部结果，不宣称ID正交。
- [x] 证据：`abtest/assign.py`、`abtest/srm.py`、`tests/test_aa.py`、`docs/statistical_contract.md`、`docs/t54_validation.md`（合并记录，未另建平台）。
- [ ] 能独立解释：确定性分流和随机化如何兼容？SRM检验的原定比例从哪里来？

状态：`done`（工程验收；本人解释未代验）　run_id：`aa-oct-01`　实际完成日期：`2026-09-21`　阻塞：`无工程差异；仅离线方法验证`

### T5.3 实现统一统计结果接口（P0）

- [x] 购买率未合并Wald-z、每用户金额Welch-t及成对ratio-of-sums delta method均实现，统一B−A、SE/CI/p/单位/状态。
- [x] 字面公式/官方库独立核验通过；空组、常量、非有限、稀疏及零总分母有状态。成对bootstrap仅用预设人工数据：delta SE0.02970186、bootstrap SE0.02930588、MC标准误0.00027256，保留实际差异，不以10%作为硬门槛。
- [x] 证据：`abtest/stats.py`、`tests/test_aa.py`、`docs/statistical_contract.md`、`docs/t54_validation.md`；ratio要求未删减。
- [ ] 能独立解释：为什么ratio-of-sums不同于mean-of-ratios？为什么要按用户而非事件做方差？

状态：`done`（工程验收；本人解释未代验）　run_id：`aa-oct-01`　实际完成日期：`2026-09-21`　阻塞：`无工程差异；统计近似有适用前提`

### T5.4 完成基础A/A校准报告（P0）

- [x] 固定0001–0300全部完成，购买率/金额各300个有效结果；失败0、SRM0，全部可计算与SRM通过辅助汇总分母均明确。
- [x] 购买率显著21/300（正10/负11），Wilson [4.62%,10.46%]；金额17/300（正11/负6），Wilson [3.57%,8.89%]。不要求恰5%，不挑种子；预先指定0001两项正向显著仍照实报告。
- [x] 证据：`abtest/aa_test.py`、`reports/aa_runs.csv`、`reports/aa_summary.csv`、`reports/aa_validation.md`、`docs/t54_validation.md`。原输入不变，仅一次读取用户级小表，没有线上干预。
- [ ] 能独立解释：为什么300次并不保证误报率恰好5%？低频或重尾指标有什么风险？

状态：`done`（工程验收；本人解释未代验）　run_id：`aa-oct-01`　实际完成日期：`2026-09-21`　阻塞：`无工程差异；校准仅限固定历史队列与当前分配/方法`

T5.5、CUPED及功效曲线未执行；不自动更新其他门槛。下一轮若授权再执行已知效应注入，本轮停止。

### T5.5 已知效应注入与可复现单次评估（P0）

- [x] 仅复用cohort-oct-01全部84,165人的二元结果；4,812个原购买标记不变。S0/S1、PCG64 seed20260921及新实验ID在执行前冻结。
- [x] 分组前构造完整潜在结果；零效应、非法参数、单调性、独立字面U、跨进程/顺序可复现、同组增量恒等式及人工二项MC核验通过。原AA限制未放宽。
- [x] 只运行一个固定场景对：S1目标+0.5717pp，488个新增标记形成真值+0.5798pp；估计+0.2955pp，CI[−0.0255,+0.6165]pp，p=.0712。不以显著或包含真值为工程通过条件。
- [x] 证据：`abtest/inject.py`、`scripts/run_injection.py`、`tests/test_inject.py`、`config/injection.json`、`docs/injection_contract.md`、`reports/effect_injection.md`、`reports/effect_injection_results.csv`、`docs/t55_validation.md`；用户级模拟仅在被忽略的`.local/t55/injected-oct-01/`，未接回金额或真实指标。
- [ ] 能独立解释：相对2%和增加2个百分点有何区别？期望效应与单次实现效应为什么不完全相同？

状态：`done`（已知效应模拟与单次评估；非真实策略效果，本人解释未代验）　run_id：`injected-oct-01`　实际完成日期：`2026-09-21`　阻塞：`无工程差异；单次不估计功效或真实投入价值`

T5.6/CUPED、T5.7完整功效曲线未执行，其他门槛不代勾。下一项优先T7首版成果整理与理解验收，本轮未开始。

### T5.6 CUPED调整与方差口径校准（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 明确variance_ratio=SE_adj²/SE_raw²，variance_reduction=1-ratio；允许减少比例为负并解释；常量X返回未调整结果；用共同分组比较调整前后，报告效果/SE/CI/FPR，不要求必然提升。
- [ ] 证据已保存：`abtest/cuped.py`；`tests/test_cuped.py`；`reports/cuped_validation.md`
- [ ] 能独立解释：剩余36%方差和降低36%差在哪？为什么theta按A/B分别居中会出问题？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T5.7 功效曲线及适用条件报告（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 报告零效应校准、实现效应、区间和未成功计算次数；点估计可轻微不单调，两条曲线可交叉；不强行修改模拟让CUPED胜出。若功效全饱和，先确认方法再调整预先说明的n/效应范围。
- [ ] 证据已保存：`abtest/power.py`；`reports/power_runs.csv`；`reports/power_report.md`；`reports/figures/power_curve.png`
- [ ] 能独立解释：功效为什么受样本量和基准率影响？为什么观察到的功效曲线不必严格单调？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T6.1 独立验证HDFS/YARN环境（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 可列出DataNode/NameNode状态、HDFS写读一致；停止/启动不丢文件；无自动重复format；给出完整内存预算，包含Driver、executor/Python、AM及守护进程。失败记录为blocked，不用原理笔记替代成功。
- [ ] 证据已保存：`infra/hadoop/`；`scripts/init_hdfs_once.sh`；`scripts/start_hadoop.sh`；`docs/hadoop_environment.md`
- [ ] 能独立解释：NameNode管什么？单副本伪分布式能证明多机容错吗？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T6.2 通过YARN完成一条真实指标作业（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 不仅有Pi样例：真实业务输出与本地相同样本结果一致；能查看作业记录与失败日志；README明确单机伪分布式、数据范围及client/cluster模式。仅从HDFS读数据但local计算不能写成Spark on YARN。
- [ ] 证据已保存：`scripts/run_metrics_yarn.sh`；`reports/hadoop_practice.md`；`runs/yarn/`
- [ ] 能独立解释：local、YARN client、YARN cluster三种模式中Driver/Executor在哪里？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T6.3 完成两项受控性能对照（P1）

- [ ] 已实现并记录实际输入范围。
- [ ] 优化前后结果一致；未通过结果检查的运行不作为性能收益；没有“删除高频session使作业更快”的伪优化，也不把启用默认AQE当收益来源。没有加速可照常交付，解释数据规模和启动开销。
- [ ] 证据已保存：`benchmarks/`；`reports/performance.md`；`runs/benchmarks.csv`
- [ ] 能独立解释：为什么分区可能有帮助，也可能没有？如何区分计算时间、排队时间与数据传输时间？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T7.1 生成可追溯README与运行手册（P0）

- [ ] 已实现并记录实际输入范围。
- [ ] 干净环境可按记录复跑自造小样本；结果表、报告、简历数字一致；没有凭空存在的文件或命令；不会因展示而公开下载凭据、未授权原始数据或SSH密钥。
- [ ] 证据已保存：`README.md`；`docs/runbook.md`；`docs/result_registry.csv`；`reports/period_summary.md`
- [ ] 能独立解释：没有原始大文件，评审者怎样验证你的逻辑？哪个run_id支持核心结论？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T7.2 简历证据映射与阶段完成审查（P0）

- [ ] 已实现并记录实际输入范围。
- [ ] 每条简历经历可验证；无日期驱动的“第5天必可投”；不得使用“搭建线上企业平台/业务增长由我带来”等超出个人项目的表述；未完成能力不通过括号二选一混入简历。
- [ ] 证据已保存：`reports/resume_evidence.md`；`reports/project_release_checklist.md`
- [ ] 能独立解释：项目在哪些要求上能证明能力，哪些需要实习或协作经历补充？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### T7.3 理解验收与现场修改练习（P0）

- [ ] 已实现并记录实际输入范围。
- [ ] 不照稿能说出指标粒度、处理边界和下一步；能独立更改一个配置/查询并预测影响；知道CATE识别依赖设计或额外假设，不能把模型相关关系直接当因果。
- [ ] 证据已保存：`reports/interview_notes.md`；`reports/learning_log.md`
- [ ] 能独立解释：哪些部分由工具辅助？哪些判断是你作出的？遇到负面结果如何解释？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### E1 训练响应/S/T三个有限基线（P2）

- [ ] 已实现并记录实际输入范围。
- [ ] 特征白名单与数据划分检查通过；常数模型作logloss基准；记录失败/不优于基准的模型，不要求T-learner必胜。模型可加载复现valid预测。
- [ ] 证据已保存：`uplift/models.py`；`reports/uplift_model_card.md`
- [ ] 能独立解释：响应预测与增量预测区别是什么？为什么样本少的对照组会增加估计不稳定？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### E2 冻结方案后评价留出排序（P2）

- [ ] 已实现并记录实际输入范围。
- [ ] 测试集未参与模型选择；三个模型按相同规则评价；允许曲线不优于随机线；整体估计接近0或为负时不输出误导性的“前20%贡献全量X%”。数据bug修复后的重评估必须登记，不能伪装全新盲测。
- [ ] 证据已保存：`uplift/evaluate.py`；`tests/test_uplift_metrics.py`；`reports/uplift.md`；`reports/uplift_test_metrics.csv`
- [ ] 能独立解释：Qini的纵轴是什么？高分组不显著和模型完全无用是否同一结论？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### E3 条件化投放建议与方法迁移说明（P2）

- [ ] 已实现并记录实际输入范围。
- [ ] 建议含不确定性和下一步实验，允许“证据不足，暂不改变策略”；没有确定性“只投前40%”。
- [ ] 证据已保存：`reports/uplift_decision_note.md`
- [ ] 能独立解释：为什么公开基准上的排序效果不能直接变成拼多多的预算决策？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

### E4 有授权时迁移学校云或HPC（P2）

- [ ] 已实现并记录实际输入范围。
- [ ] 用途与资源获授权，密钥不入仓库；同输入输出一致；记录CPU/RAM/存储和实际运行模式。权限未获批不阻塞本地核心，也不创建收费资源。
- [ ] 证据已保存：`config/mrc.yaml`；`docs/cloud_runbook.md`；`reports/cross_environment_check.csv`
- [ ] 能独立解释：为什么同一业务逻辑应跨环境保持一致？单节点多线程为什么不是多机集群？

状态：`not_started`　run_id：`未运行`　实际完成日期：`未完成`　阻塞：`无已记录阻塞`

## 发布门槛

- [ ] G0：环境与数据验收已完成。
- [ ] G1：独立指标核验、重复运行与边界测试通过。
- [ ] G2：全部P0通过；可以仅按已完成能力准备投递。
- [ ] G3：全部P0+P1通过；可以加入实际完成的Hadoop、CUPED及性能证据。
- [ ] G4：可选模型/云扩展实际完成，未越过测试集或权限边界。

本轮门槛核对：G0相关T0.1–T0.3、REES46与Criteo/T0.4现已有工程证据；本人解释及全项目门槛尚需另行审核，G0不自动勾选。G1要求的T1.1–T1.4证据在REES46分数据线已满足；这不代表项目其他数据线也已通过，全项目G0/G1不自动勾选。T1.5只完成十月首版范围冻结，本人解释未代验。

## 每次工作结束填写

任务编号：
实际完成内容：
运行命令与环境：
输入范围与run_id：
通过的检查与实际数值：
未通过/未运行的检查：
新增口径变更及原因：
我今天能独立解释的内容：
下一次唯一优先任务：

**禁止：** 为了打勾而强迫FPR=5%、CUPED胜出、Uplift优于基线或黑五被告警。实现是否正确与结果是否理想分开评价。
