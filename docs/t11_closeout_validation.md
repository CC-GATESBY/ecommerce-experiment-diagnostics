# T1.1 工程收尾验收

验收日期：2026-09-17。起点提交：`95cf6708ef28fd43aaff94ae2b00d771c5d1af4d`。结论：**T1.1 done（工程验收，本人解释未代验）**。仅收口日期质量规则、读取端执行与人工跨月追加；未实现 T1.2 或正式指标。Criteo、T0.4、总 G0/G1、T1.2–T1.5 保持原状态。

## 唯一真实输入与既有证据

固定 `month-v101-01` 为下游批次，原因是它是首个成功运行，也是历史逐日质量表引用的 run。`month-v101-02` 保留作复验记录，两者没有合并。登记复验 run 返回 `already_registered`，仍选择首轮。

逻辑身份：来源 `rees46_multicategory_2019_oct`；scope `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`；输入 SHA256 `5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b`；契约 `rees46-events-v1.0.1`。分析序列 `rees46_fixed_users_20260916_v1`，抽样规则 `rees46-user-sample-v1|20260916`。run_id 不属于逻辑输入身份。

两份历史收据分别 66/71 项通过，汇总和逐日结果一致，复验全字段/重复重数差异为 0。只读所选 run 的 1 个事实 Parquet 文件，共 73,102,738 bytes、2,114,081 条，39 列 schema；实际时间范围 2019-10-01 00:00:23 至 2019-10-31 23:59:56 UTC。真实文件清单、指纹、路径和完整运行收据只留本地。

| 原综合验收拆分 | 本轮处理 | 证据 |
|---|---|---|
| 记录守恒、原始字段及重复重数保留 | 引用已通过证据，不重新解析 | [工程验收](t11_engineering_validation.md)、[整月验收](t11_month_validation.md) |
| 金额与 UTC 时间解析 | 沿用 v1.0.1 与 Decimal(18,2) | [解析契约](event_parsing_contract.md)、整月边界修复/回归 |
| 独立核验与重跑 | 引用两轮全量多重集独立核验 | 整月验收及 66/71 项历史收据 |
| 日期质量规则及读取执行 | 本轮通过 | [冻结规则](date_quality_policy.md)、[日期门禁表](../reports/date_quality_gate.csv) |
| 人工跨月追加与防重复登记 | 本轮通过 | 下表及本地 synthetic 收据 |

## 日期放行结果与实际读取

规则 `rees46-date-quality-v1` 在实现前冻结，未为结果调整阈值。两个用途都对 2019-10-01 至 10-31 的每一天实际评估，并由同一读取接口检查规则后取得 DataFrame。

| 用途 | 放行日期 | 阻断日期 | 有警告日期 | 含义 |
|---|---:|---:|---:|---|
| count | 31 | 0 | 31 | 时间、用户 ID、行为核心异常均为 0，event_eligible 与每日记录数相同 |
| amount | 31 | 0 | 31 | 各日 complete_observed，购买金额坏值为 0，购买行均 amount_eligible；保留全部行为作为后续分母 |

品牌缺失 299,547 条、品类代码缺失 669,421 条，分别涉及全部 31 天；维度分析以后须保留 unknown 档。非购买零价格为 view 3,286 条（31 天）、cart 6 条（3 天），作为单独提示；purchase 零价格 0。没有日期被填成零事件日，没有异常行被静默删除。质量门禁表按日期列出适用身份、来源 run、规则版本、行数、reason_codes 和 warning 数量。

`FactReader` 对明确文件清单只创建一次真实 Parquet 读取，并持久化在本地 Spark 缓存中；两个用途及计数核对复用该缓存。首次读取按日期检查记录数、event_eligible、amount_eligible 及每行四项逻辑身份/run_id；随后 amount 用途逐日核对全部行为记录数，证明没有只保留购买行。最多收回 32 个日期聚合，不 collect/toPandas 事实表；完成后释放缓存并正常停止 Spark。

| 检查 | expected | actual | pass |
|---|---|---|---|
| count 用途记录数 | 2,114,081 | 2,114,081 | 是 |
| amount 用途分母与每日 amount_eligible | 与既有 31 日收据逐日一致 | 全部一致，仍含 2,114,081 条全部行为 | 是 |
| 实际逐日记录数、eligibility 与来源身份 | 每日与收据一致，错误身份 0 | 全部一致，错误身份 0 | 是 |
| 真实 Parquet 加载次数 / 新真实事实文件 | 1 / 0 | 1 / 0 | 是 |
| 复验登记不新增批次 | already_registered，选择 month-v101-01 | 相同 | 是 |
| 两份真实 run 的事实/收据及旧逐日报告 | SHA256 不变 | 不变 | 是 |

历史 `data_quality_daily.csv` 中的 formal_analysis_release 仍为 not_granted。这里的放行只表示 T1.1 数据使用条件满足，不是 T1.3/T1.4 指标验收或上游日志完整性证明；user_sample_candidate 仍是候选。

## 人工跨月与拒绝路径

成功集成 run 使用 24 条人工输入记录（含同输入复验副本），全部位于独立 synthetic 空间。10 月和 11 月共用 `synthetic_fixed_users` 分析序列、`synthetic_rees46_fixture` 来源及固定人工用户规则 `synthetic_fixed-user-fixture-v1|literal-users`；scope 可以不同。它们不是实际 5% REES46 样本，不混入真实登记。

| 情景 | expected | actual | pass |
|---|---|---|---|
| A：登记 10 月，读取合格日期 | 10-01 有 3 行，amount_eligible 1 行 | 3 / 1，amount 用途仍保留 3 行 | 是 |
| B：追加 11 月，同序列读取 10-01 与 11-01 | 原 3 行 + 新 3 行 = 6；10 月文件/结果不变 | 6，旧文件哈希及查询结果不变 | 是 |
| C：同输入重复登记和换 run_id | 已登记、维持 2 批及 6 行 | already_registered；2 批、6 行 | 是 |
| D：未授权日期重叠 | 拒绝合并/替换 | 拒绝 | 是 |
| E：写入前/登记原子替换前失败 | 半成品不可读，登记文件与旧批次可读性保持 | 拒绝半成品；模拟替换失败后旧 3 行仍可读 | 是 |
| F：缺失金额 unknown / 部分坏金额 partial_observed | count 分别保留 2 / 3 行；amount 拒绝 | 2 / 3，amount 均拒绝 | 是 |
| 只有维度缺失 | 两种用途仍读全部 3 行 | 3 / 3 | 是 |
| 核心字段错误、缺失日期、混合好坏日期请求 | 对应用途/整个请求拒绝，不跳过坏日 | 均拒绝 | 是 |
| 合格无购买 / 合法零购买 / 非购买坏价与空 session | 允许当前范围；分别保留 2 / 1 / 1 行 | 相同 | 是 |
| 无法归属日期的坏时间 | 即使另有合格日期也阻断全批 | 拒绝 | 是 |
| 错 scope、错行数、证据/文件指纹不符、登记表重复、未登记序列 | 拒绝 | 均拒绝 | 是 |

实际通过：9 项规则单元测试、17 项旧配置测试、53 项人工集成检查、6 项真实读取检查（含完整逐日子结果）。解析代码、oracle、依赖锁未改；之前 83 项解析测试引用历史验收，本轮没有声称重跑它们。

首轮 synthetic-01 因测试工作目录相对/绝对路径混用，在写 Parquet 前失败；保留失败收据和 14 条人工 CSV。修复路径解析后，synthetic-02 用新目录通过。连同失败轮共写入 38 条人工 CSV 记录，未超过 100；没有改规则来通过。独立人工预期先用标准库生成，全部字段与重复重数核对；上述用途和追加情景另有字面预期。只证明本地串行机制，不声称实现并发或分布式事务。

## 资源、不可变性与复跑

复用 Python 3.11.15、JDK 17.0.19、PySpark/Spark 3.5.8，local[4]、Driver 4g、UTC、32 shuffle 分区，无 Hive。首轮失败 2.364 秒，人工成功轮 13.438 秒，真实读取轮 17.512 秒；这些是执行收据耗时，不是性能基准。峰值内存 `not_measured`，未为测量增加重跑。

本地累计新增预算 2 GiB、磁盘保留 150 GiB。每至多 2 秒采样累计产物，包含保留失败、人工 CSV/JSONL/SQLite/Parquet、缓存落盘、临时文件及日志。运行采样新增高水位 991,881 bytes，最低可用 566,865,944,576 bytes（约 527.935 GiB）。静态代码/文档/模板也远低于余量；最终文件规模记录在本地交付收据中。

既有 104 个本地数据/事实/辅助文件的大小、mtime_ns、inode 后检无变化；所选及复验 run 的事实和收据另有 SHA256 前后核验。本轮旧 CSV 未读取、未修改，没有重建真实 Parquet；既有 JSONL、SQLite 和验收文档未修改。

模板 `config/fact_access.example.json` 的空路径/日期不能执行。填写本地精确 run 路径和日期后保存为 `config/fact_access.local.json`（已验证被忽略）。以下命令从项目根目录执行；所有占位符要替换，run 目录必须未使用，同轮预算基线不可重置。新轮复跑须获得对应范围授权，不能自动再次读取真实事实。

```sh
".venv/bin/python" -m unittest discover -s tests -p test_fact_access.py -v
".venv/bin/python" -m unittest discover -s tests -p test_config.py -v
".venv/bin/python" scripts/run_fact_closeout.py --stage synthetic --runtime-config config/local.yaml --run-dir "<NEW_LOCAL_RUN>" --budget "<LOCAL_BUDGET_JSON>"
".venv/bin/python" scripts/run_fact_closeout.py --stage real --runtime-config config/local.yaml --config config/fact_access.local.json --synthetic-gate "<PASSED_SYNTHETIC_VALIDATION_JSON>" --run-dir "<NEW_REAL_READ_RUN>" --budget "<SAME_LOCAL_BUDGET_JSON>"
```

受控读取复用入口为 `FactReader(spark, project_root, registry_path, series_id)`；在上下文内调用 `.read([UTC日期], 'count'或'amount', expected_scopes=[scope])`，退出上下文释放缓存。登记文件只存本机，使用 `register_batch` 追加，不能手工合并两份复验文件清单。

工程验收无剩余缺口；本人解释仍由用户确认。下一项仅建议 T1.2 重复候选与会话核验，不继续扩充 T1.1。
