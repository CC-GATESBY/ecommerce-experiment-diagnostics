# T1.4 独立比较契约

版本 `rees46-duckdb-crosscheck-v1`，2026-09-17，先于真实核验冻结。唯一候选 scope/series、UTC十月窗口和输入身份沿用T1.3；本轮保留10月5日完整UTC日的单独证据，同时逐行核验整月四层。这是核验覆盖扩展，不新增用户或月份，不重写T1.3历史产物。

DuckDB只从候选CSV九个VARCHAR列独立计算。CSV显式UTF-8、逗号、双引号/双双引号转义、LF记录分隔、header=true、auto_detect=false、strict_mode=true、null_padding=false、ignore_errors=false，九列force_not_null，空字符串不转NULL。标准库csv先核对表头及每条记录字段数，按记录计数；独立SQL再读取。原始ID、前导零、空格、引号内LF/CR不修剪。人工数据先逐值检查读取设置。

独立实现严格UTC格式/日期、ASCII数字用户ID、已允许行为、ASCII空白session、Decimal词法/有效整数位/小数位检查、非有限/负/零/缺失/非法标记。仅词法及精度通过后转换Decimal(18,2)，不依靠TRY_CAST接受舍入。日期核心异常和批次不可归属时间从CSV自行统计；坏购买金额保留购买用户、阻断该日正式金额，维度缺失不删行。不调用Spark解析、oracle或指标SQL计算DuckDB结果。

first_seen来自完整观察窗口；品牌映射独立按10月1–7日合格事件数降序、encode(原brand)字节序升序取Top200。先比较品牌原值、参考计数、排名、typed key及标签的逻辑内容，再检查来源指纹。Spark first_seen与品牌映射均只在比较端读取。维度和金额状态按既有文字契约，不改变主口径。

## 冻结字段对照

所有表主键含scope_id。整数值（Spark BIGINT/INT与DuckDB BIGINT/HUGEINT）、布尔、UTF-8字符串、DATE及Decimal逐值精确比较，NULL使用IS NOT DISTINCT FROM，不填0。UTC时刻统一为微秒TIMESTAMP比较；Spark存储时间单位可不同但不能改变时刻。金额期望Decimal(38,2)，价格输入Decimal(18,2)。浮点比率为DOUBLE，固定 `abs_tol=1e-6, rel_tol=1e-10`，允许差为max(abs_tol,rel_tol×max(|两值|))；NaN/Infinity直接失败。最大相对差以两值绝对值最大者为分母，两者0则0，空值配对不参与误差但核验一致性。

| 表 | 主键（另含scope_id） | 精确业务/状态字段 | 浮点字段 |
|---|---|---|---|
| dim_user_first_seen | user_id | first_seen_at_utc、first_seen_date_utc | 无 |
| agg_user_daily | utc_date,user_id | event_records、view_events、cart_events、remove_from_cart_events、purchase_events、sessions、purchase_sessions、is_buyer、is_first_seen_day、purchase_amount、purchase_amount_bad、purchase_amount_valid、purchase_zero_events、amount_status、count_allowed、amount_allowed、date_reason_codes | 无 |
| agg_daily_metrics | utc_date | active_users、buyers、上述事件/会话/金额质量计数、purchase_amount、first_seen_users、count_allowed、amount_allowed、amount_status、date_reason_codes及三个比率status | buyer_rate、amount_per_buyer、first_seen_ratio |
| agg_daily_dim | utc_date,dim_name,dim_value_key | dim_value_label、users、buyers、event_records、purchase_events、purchase_amount、purchase_amount_bad、purchase_amount_valid、amount_status、count_allowed、amount_allowed、date_reason_codes | 无 |
| 品牌映射 | brand | reference_events、brand_rank、dim_value_key、dim_value_label | 无 |

每表核对schema字段覆盖、行数、主键空值/重复、缺键/多键、每个字段差异数；键关联在引擎内完成。差异明细只写本地。运行元数据（source_id、source_run、input_sha256、metric_version、contract_version、date_policy_version、brand_mapping_version/sha256、观察窗口）与冻结来源及收据核对，不当作DuckDB业务计算输入；run_id/耗时不要求两个实现相同。

日汇总另与独立CSV日期质量及既有结果比对；10月5日从完整窗口结果选择，first_seen不缩窗重算。历史数字只用于结果对账，不进入计算SQL。

## 人工快照验收

≤100条原始人工CSV，先有字面预期，再测试两个实现。使用真实 `build_metrics` / `publish` 接口生成不可变run快照：相同输入重复、同run拒绝覆盖、一个输出日期扩展为两日、失败保留后新run重试。first_seen与品牌参考仍固定于同一完整观察范围。最终读取显式选择一个完成快照，不合并旧/新快照；半成品及非唯一选择拒绝。它是本地串行快照选择，不是原地物理分区append、并发写入或分布式事务。

资源：先完成人工Spark并停止，再运行真实DuckDB；threads=4、memory_limit=2GB、temp目录独立、临时文件上限受累计10GiB/至少150GiB空闲监控。memory_limit不是进程RSS硬上限。真实核验先一次，失败保留证据，不调预期、删日期或放宽容差。T1.3历史证据不改写。
