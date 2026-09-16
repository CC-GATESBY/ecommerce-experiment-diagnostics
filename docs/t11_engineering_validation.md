# T1.1 工程样本验收

验收日期：2026-09-16。工程子任务 `passed`；T1.1 整体仍为 `in_progress`。起点提交 `2b779bfd1dbb3816e6117bba9921a5bc3f41451c`，实际目录末尾空格保留。未读取整月候选或重扫原始整月 CSV，未下载安装、修改依赖锁或运行后续模块。仓库继续 private/main。

## 输入、契约与 schema

- 唯一输入：`data/manifest.json` 中第一份 `engineering_samples`，本地相对路径 `.local/t04/samples/rees46-oct-head-01/engineering_sample.csv`；第二份同内容样本没有混入。
- scope_id：`rees46_oct_head_d50b23d8c05613dfd1eb`；100,000 条数据记录，表头不计数；输入 13,352,959 bytes。
- SHA256：`fe2cd808172c853217201660a98a8c8600fb0230f5c89efda45a9a1a2fdae754`，每次前后均一致。
- 时间范围：2019-10-01 00:00:00–04:28:27 UTC，只有约四小时，不能视为完整日或整月。
- 价格预检查：全部两位小数，整数有效位最多四位；固定 `Decimal(18,2)`，先检查最多 16 位整数/2 位小数，再直接从原字符串解析。超限标记并置派生 Decimal 为 null，不扩大、不舍入；原值保留。
- 39 列：原始九列 String；event_timestamp_utc Timestamp、event_date_utc Date、price_decimal Decimal(18,2)；21 个布尔质量/范围标记；5 个来源/契约/run 字符串与 parsed_at_utc Timestamp。逐列定义见 `sql/ddl/events.sql`，完整口径见 `docs/event_parsing_contract.md`。Parquet 重读类型全量核验。
- 每行仍是一条日志事件。所有可解析行保留；无隔离行，无去重。Parquet 不保证物理行顺序，原字段及派生值按包含重复重数的多重集精确比较。

## 首张质量概览

| 项目 | 实测记录数 |
|---|---:|
| 输入 / 事实输出 / 隔离 | 100,000 / 100,000 / 0 |
| view / cart / purchase / remove_from_cart | 97,130 / 1,215 / 1,655 / 0 |
| 时间缺失 / 非法 | 0 / 0 |
| user_id、product_id、category_id 缺失或非法 | 各 0 |
| 未知行为 | 0 |
| 品类代码缺失 / 品牌缺失 / session 缺失 | 32,587 / 14,391 / 0 |
| 价格缺失 / 非法 / 非有限 / 负值 | 各 0 |
| 零价格 | 119 |
| 价格整数精度超限 / 小数位超限 | 0 / 0 |
| purchase 金额缺失或不合格（全部 / 合格事件范围） | 0 / 0 |

维度缺失、零价格均保留。零价格属于可观测非负值并单独标记，不是用缺失补零。字段数异常为 0（标准库逐 CSV 记录严格检查）；各项脱敏汇总与两次运行对账在 `reports/data_quality_engineering.csv`。

## 工程核对表与独立验收

预期由标准库 csv、datetime、Decimal 在 Spark 启动前独立计算；没有读取 Spark 汇总作为预期，也不调用 Spark 的价格/时间解析函数。用户集合最多受 100,000 条输入硬限制。逐行期望侧 JSONL 只保存在本机。Spark 读取独立预期后用双向 exceptAll 核对所有原字段、UTC/Decimal 派生值、标记及重复重数；事实表未 collect/toPandas，返回 driver 的仅一行有界汇总和两条 synthetic worker 探针。

| 检查 | expected（独立标准库或冻结要求） | actual（两次最终 Spark run） | 结果 |
|---|---|---|---|
| 数据记录 / Parquet 读回 | 100,000 | 100,000 | pass |
| 不同用户（合格行为范围） | 20,384 | 20,384 | pass |
| 购买用户 | 1,336 | 1,336 | pass |
| 购买事件 | 1,655 | 1,655 | pass |
| 合格观测购买金额 | 501176.21 | 501176.21 | pass |
| 金额完整性状态 | complete_observed | complete_observed | pass |
| 各行为、21 项标记、购买金额异常计数 | 独立预期逐项值 | 全部精确相同 | pass |
| 原字段、派生字段和重复重数双向差异 | 0 / 0 | 0 / 0 | pass |
| 39 列 schema / Decimal | 冻结 schema / (18,2) | 全列相同 / (18,2) | pass |
| 最早 / 最晚 UTC 时间 | 00:00:00 / 04:28:27，2019-10-01 | 精确相同 | pass |
| Python / Java / PySpark / Spark JVM | 3.11 / 17 / 3.5.8 / 3.5.8 | 3.11.15 / 17.0.19 / 3.5.8 / 3.5.8 | pass |
| master / Driver / JVM 堆 / shuffle / timezone | local[4] / 4g / 4294967296 B / 32 / UTC | 全部符合 | pass |
| driver / worker Python | 同一项目 .venv | 同一项目 .venv | pass |
| catalog / 正常停止 Spark | in-memory / true | in-memory / true | pass |
| 原有配置、接入、抽样测试 | 52 项通过 | 52 项通过 | pass |
| 新工程测试 | 21 项通过，含 36 条 synthetic Spark 数据 | 21 项通过 | pass |
| 最终两次收据全部断言 | 29 / 33 项全部通过 | 29 / 33 项全部通过 | pass |
| 重跑逻辑内容双向差异 / 汇总 | 0 / 0，汇总相同 | 0 / 0，汇总相同 | pass |
| 首轮最终输出所有文件内容哈希 | 重跑前后相同 | 相同 | pass |
| 已有 run / 中断 / 解析失败 | 拒绝覆盖 / 不发布 complete | 人工测试符合 | pass |

金额是合法购买日志价格之和，单位沿用原 price，不是订单收入，也不宣称币种。complete_observed 只表示这一合格工程范围内的购买金额没有发现坏值，不证明上游完整。没有扩大整数或 Decimal 容差；没有运行总体购买率、完整日指标、用户日表或正式业务分析。

## 运行、规模与复跑

全部产物位置：`.local/t11/runs/<scope_id>/<run_id>/complete/`；事实文件在 `fact_events/`，独立预期、完整验证和原始启动日志均留本机，不进 Git。

| 最终 run_id | 总耗时（秒） | Spark 部分（秒） | Parquet 文件 bytes | run 全部文件 bytes |
|---|---:|---:|---:|---:|
| engineering-20260916-03 | 12.511 | 8.766 | 2678274 | 91588781 |
| engineering-20260916-04 | 14.665 | 10.833 | 2678275 | 91591686 |

两轮最终运行前后可用磁盘观测值为 573,219,516,416 → 572,996,603,904 bytes，差值 222,912,512 bytes；这是整个卷的观测变化，不能全部归因于本任务。验收整理时 `.local/t11/` 所有新增/保留文件合计 366,559,096 bytes（包含前期成功运行、测试与失败记录），远低于 10 GiB，剩余空间高于 150 GiB。峰值内存和峰值磁盘未测；上述耗时不是性能基准。

人工测试先于真实输入运行；最初沙箱限制 Python/JVM 回环端口绑定，保留了一次失败收据，未发布完成。获准本机通信后 73 项测试通过。初版工程 run 01/02 也已成功；随后去掉不必要的特殊 null 标记，补强字面量 null/控制字符/首尾空白原值保留测试，最终 73 项测试再次通过，使用全新 run 03/04 完成验收。最终审查又显式区分带引号/不带引号空字段，仅改动 synthetic fixture，受影响的 21 项工程测试再次通过，生产解析代码及最终 run 对应代码哈希未改变。此前输出均保留、不覆盖。
完整源、压缩包、两份旧工程样本和整月候选的大小/mtime 与开始前一致；指定输入另核对了内容 SHA。未为核验而读取完整源或整月候选内容，因此没有把元数据不变说成重新完成这些大文件的哈希核验。

从实际项目根目录复跑（保留目录尾部空格；本机 config 不能提交；使用新的 run ID）：

```sh
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" "scripts/run_events.py" --config "config/events.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-new-01"
".venv/bin/python" "scripts/run_events.py" --config "config/events.local.yaml" --runtime-config "config/local.yaml" --run-id "engineering-new-02" --compare-run-id "engineering-new-01"
```

配置模板须填第一份样本的清单相对路径和既有 `.local/t11/runs` 输出目录。模板空路径、错误 SHA、其他样本/整月 kind、目录通配符和重复 run 均被拒绝。只复用已验收环境，不修改原 smoke 配置校验或依赖锁。

本次最终实际执行代码 SHA256：

| 文件 | SHA256 |
|---|---|
| `etl/01_events.py` | `ea4ba60f3408b46384c335b50e7fc27731e507fb8ccbd824ad0a0013419d678e` |
| `etl/oracle.py` | `151f68ec924f6df3ab8693454454ca953595dc9dab2e4f4e0bf88c87c2bbe212` |
| `etl/event_config.py` | `348c18495706098f45590f7956808a2fe11dd39de09315a8c8d6c866ff7ea316` |
| `scripts/run_events.py` | `7eed303bde6f7a5f0957933726667422943ceaaf14567ca58f6d41e25cedfd20` |

## 未完成项与交接

T1.1 engineering_sample 子任务通过；T1.1 整体仍为 in_progress，整月候选解析、后续正式质量门禁和扩量未运行。Criteo 来源验收仍待完成，T0.4/G0、T1.2–T1.5/G1 及用户本人解释项不勾选。标准库核验不是 T1.4 DuckDB 验收。

当前工程子任务无未解决阻塞。限制：头部约四小时、非随机样本；品类和品牌缺失明显；价格精度契约只经工程范围实测；后续格式或精度变化须显式标记/拒绝且重新验收。下一步只建议在用户明确授权后，把同一契约用于整月用户样本候选；本轮到此停止。

需要理解：① 一行是日志事件，重复候选与购买事件都不能改称订单。② 原始值和派生缺失/无效标记不同；缺金额不能变 0，维度缺失不能删整条行为。③ 独立预期、原字段多重集与不同 run 复现共同证明工程处理一致，不能证明四小时样本代表总体或上游完整。
