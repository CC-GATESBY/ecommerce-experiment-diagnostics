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
