# T1.1 工程样本解析契约 v1

本契约先于 Spark 实测冻结，仅放行清单中第一份旧 `engineering_sample`，SHA256 `fe2cd808172c853217201660a98a8c8600fb0230f5c89efda45a9a1a2fdae754`。同内容第二份不读入；整月候选另行授权。粒度是一条原始行为记录，不是用户、订单或用户日。

价格预检查实际读取 100,000 条 CSV 记录：小数位全部为 2；整数有效位 1/2/3/4 位分别为 2,591/33,705/58,546/5,158 条；无异常格式。冻结 `Decimal(18,2)`，最多 16 位整数和 2 位小数，预留明确固定容量；不声称整月已符合此范围。允许 ASCII 正负号、整数与普通小数，不接受指数、前后空白、千分位或无整数部分的小数。有效整数位不包含前导零；额外小数位即使全为零也标记超限，不悄悄舍入。原字符串直接 cast 为 Decimal，从不经过 float/double。

空或仅 ASCII 空白（空格、制表、回车、换行、垂直制表、换页）标记 missing；非有限 NaN/sNaN/Inf/Infinity（大小写及正负号均识别）、其余非法格式、负值、零值、整数精度超限、小数位超限分别标记。负值和零值可保留派生 Decimal；负值不进入合格购买金额，零值保留且单独报告。非有限、格式或精度无效时派生 Decimal 为 null，原值保留。超限数字的正负/零仍独立标记。

时间严格接受 `YYYY-MM-DD HH:MM:SS UTC`，要求真实公历日期、年份 0001–9999；派生 UTC timestamp 和 UTC date。空时间与非法时间分开标记。原始九列均为 String，空字符串保持空字符串；所有标准化只写派生列。用户/商品/品类 ID 仅非空 ASCII 数字串有效；不转浮点，不去前导零或空白；缺失与非空非法分别标记。商品或品类异常不改变 v4 用户范围。品牌、品类代码、session 缺失不删行；不补造值。

允许行为 `view/cart/remove_from_cart/purchase`，其他原值保留并标记 unknown。`event_eligible` 只要求有效 UTC 时间、有效 user_id、允许行为。`amount_eligible` 进一步要求 purchase 且 Decimal 非空、非负；不因金额无效删用户。保留所有重复候选，不做 T1.2 去重或 session 分析。

工程核对表的 users/buyers/purchase_events 使用上述同一合格范围；purchase_events 是日志记录数，不是订单。金额为合格购买价格的精确观测总和，单位沿用原 price，不指定币种。金额状态为 `complete_observed`（范围内购买金额均合格）、`partial_observed`（有有效值也有坏值）、`unknown`（有购买但全部金额不可用）或 `no_purchases`（合格范围没有购买，仅此时和为结构性 0）。前两者不证明上游完整，头部范围不能宣称完整日。零值不会被当作缺失；缺失不会被填 0。

CSV 使用 UTF-8、逗号、双引号及双双引号转义，允许引号内换行。标准库先 strict 解析、逐记录检查恰为九字段及精确表头/行数；不以物理行计数，不依赖 Spark FAILFAST 发现全部宽度错误。保留字段内容，不承诺保留原文件引号排版。Spark 关闭首尾空白忽略，开启 multiLine，仅把空字符串设置为 CSV nullValue/emptyValue；解析空值恢复为原空字符串，再做全部字段的多重集核验。字符串 null、NULL、标记样式文本和字段内控制字符不擅自当成缺失。结构错误或两个解析器不能一致保留输入时整个 run 失败，失败 staging 不发布为完成。

事实 schema 由 `sql/ddl/events.sql` 明确描述。每条记录附 source_id、scope_id、input_sha256、contract_version、run_id 和 parsed_at_utc。Parquet 不承诺物理顺序；逐字段和重复重数必须一致。两次运行排除 run_id/parsed_at_utc 后逻辑多重集相同，不要求 Parquet 二进制哈希相同。

输出先写独立 scope/run staging，标准库预期、Parquet 重读、schema、原字段及派生字段、多重集和汇总全部通过并正常停止 Spark 后，才在同一 run 内发布 `complete` 目录。已有 run 拒绝覆盖，失败记录保留。全部明细、期望侧文件、运行收据和日志只在 `.local/t11/`。此处独立检查是工程证据，不替代 T1.4 DuckDB 正式核验，也不放行任何日期进入后续正式指标。

## 补丁 v1.0.1（2026-09-16）

以上 v1 为工程阶段历史契约，旧代码版本 `rees46-events-engineering-v1` 的报告和输出保留。本次实现版本为 `rees46-events-v1.0.1`，只修复不符合原约定的边界，不扩大字段或金额可接受格式：

- 非有限值最多允许一个可选正负号。NaN、+NaN、-Inf 为 nonfinite；++NaN、+-Inf、--Infinity 为 invalid。oracle 不再用会吞掉连续符号的 lstrip；使用 Python fullmatch。原字段不修改。
- Spark 的 Java 正则使用 `\A`、`\z` 匹配完整输入。旧 `$` 能在末尾行终止符前匹配；数字 ID、金额或 UTC 时间末尾的 LF/CR/CRLF 必须非法，不能 strip 后接收。纯 ASCII 空白仍是 missing，口径不变。
- 实测发现默认 CSV 自动检测会规范化引号内 CR/CRLF。现在从严格表头的有界前缀识别记录分隔符，显式设置 Spark lineSep 并保留 multiLine，使引号内换行原样保留；带/不带引号空字段、LF/CR/CRLF 均进入人工回归。

当前额外授权仅放行清单中唯一 `user_sample_candidate`：scope `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`，SHA256 `5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b`，2,114,081 条、282,405,091 bytes。白名单同时核对 manifest、完成收据、类型、scope、路径、大小、哈希和行数；旧工程输入保护保留。整月入口还要求当前实现的工程回归通过，以及本轮累计预算文件。其他月份、全源 CSV 或未登记输入未获放行。

独立 oracle 仍逐记录用标准库解析，SQLite BINARY 主键保存全局/日期范围的原始 ID 及合格/购买标记，4096 条插入批次、4 MiB cache；不维护全事件列表或无界用户集合。期望 JSONL 包含全部记录，Spark 双向 exceptAll 比较所有原字段、派生字段和重复重数。全月与每个 UTC 日期分别核对计数、不同用户、金额、完整性状态和按行为的零价格；日期汇总最多返回 64 桶，超出则失败而非截断；无效时间保留在单独桶。日期用户数不可相加当月去重用户数。

complete_observed/partial_observed/unknown/no_purchases 的金额含义与 v1 相同。逐日质量汇总不是正式指标层；即便解析通过，也不把输入候选提升为最终分析范围，不自动批准全部日期开展金额分析。跨 run 对比只排除运行 ID 与运行时间；旧版本工程回归额外排除已明确变更的契约版本，但其余全部字段必须相同。

本轮所有新增 `.local/t11/` 产物累计上限 20 GiB，保留至少 150 GiB 可用空间；预算包括预期 JSONL、SQLite、事实 Parquet、临时文件、重跑与日志。oracle 每 10,000 条、Spark 运行时每不超过 2 秒检查，超限停止、保留失败 staging；磁盘峰值只报告采样高水位，不冒充连续精确峰值。运行根目录和临时文件固定留在本机。
