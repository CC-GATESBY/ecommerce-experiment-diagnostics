# 指标契约 v1

版本 `rees46-metrics-v1`，2026-09-17，在人工测试和真实指标查询前冻结。只复用 `month-v101-01`，scope 为 `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`，series 为 `rees46_fixed_users_20260916_v1`；观察窗口固定为 `[2019-10-01, 2019-11-01)` UTC。输入仍为固定用户候选，不升级为最终分析范围。

沿用 `rees46-events-v1.0.1`、`rees46-date-quality-v1`，不更改解析和日期门禁。FactReader 先按 count 读取全部合格行为，再验证允许日期的 amount 用途；金额不合格不删除购买用户、其他行为或整天。源文件和复验 run 不作为额外输入。

## 粒度、指标和空值

| 表 | 粒度/主键 | 主要约束 |
|---|---|---|
| dim_user_first_seen | scope_id + user_id | 整个观察窗口首次合格 UTC 时间及日期；较短输出窗口不重算 |
| agg_user_daily | scope_id + utc_date + user_id | 仅实际出现的用户日，不生成全用户乘日期面板 |
| agg_daily_metrics | scope_id + utc_date | 从用户日聚合，并与独立事实 SQL 对账 |
| agg_daily_dim | scope_id + utc_date + dim_name + dim_value_key | 每条事件在每个维度恰好一个桶 |

active_users 是同范围合格用户去重；buyers 是有 purchase 的用户去重；purchase_events 是行为记录数，不是订单。purchase_amount 只累计 amount_eligible 的原单位日志价格，不称财务收入。重复候选仍保留。事件数、view/cart/remove_from_cart/purchase 数均按行计数。sessions 为当天有效 `(user_id,user_session)` 去重；purchase_sessions 仅统计当天有购买的有效键，不传播其他日期购买。缺 session 保留事件和用户。跨日不重切会话，不计算停留时长；日用户或会话数不可相加当月去重。

is_first_seen_day 仅指本观察范围首次出现；10 月 1 日所有当日用户均为首次观察，是窗口边界，不是注册、获客或真实新客户。

日期 count 不允许、缺失或证据无效即拒绝请求，不补零。count 允许而 amount 阻断时保留计数，三层聚合的正式 purchase_amount 和金额比率均为 null，保留金额质量计数、日期原因和状态。用户日/维度自身金额状态按购买数和坏金额数区分 no_purchases / complete_observed / partial_observed / unknown，同时携带日期 amount_allowed，不能以局部好金额绕过整日阻断。合格无购买时金额为结构性 0.00；未知金额不是 0。

buyer_rate=B/U（U=0 为 null，状态 no_active_users）；amount_per_buyer=V/B（金额阻断或 B=0 为 null，分别 amount_blocked/no_buyers）；first_seen_ratio=首次观察用户/U。均以 Double 保存比率及状态，金额列保持 Decimal。仅 U>0、B>0、金额允许时核验 `V=U×R×M`，预先固定 `abs_tol=1e-6, rel_tol=1e-10`；不调整容差。整数和 Decimal 精确相等。明细 Decimal(18,2)，聚合显式 Decimal(38,2)，ANSI 模式溢出失败；允许金额不应出现 null，写后重读核验类型和值。没有订单号，金额/购买用户不是订单客单价。

## 冻结维度

- category_l1：完整 category_code 必须符合 ASCII `[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*`，取首段，保留大小写。不 trim；空前缀、空段、尾点、纯空白或其他不可解释值归 unknown。内部键为 `category:<首段>` 或 `bucket:unknown`，原字段不改，不猜 category_id。
- price_band：基于非空、非负的合法 price_decimal，`[0,20)`、`[20,50)`、`[50,200)`、`[200,+∞)`；键为 `band:0_20` 等，异常归 `bucket:unknown`。0 属第一档；这是事件当时价格，不是首次浏览价格，不支持价格因果结论。
- brand_group：映射规则版本 `rees46-brand-oct01-07-top200-v1`。参考期 10 月 1–7 日 UTC，合格事件中的非缺失原品牌按事件数降序、原字符串 Spark UTF-8 二进制字典序升序排名，最多 200 个；不 trim、不改大小写。生成一次后物化为本地映射 Parquet/JSON，记录有序映射内容 SHA256。后续日期只查该映射，新品牌/未入选为 `bucket:other`，缺失为 `bucket:unknown`，入选为 `brand:<原品牌>`；显示标签与键分列，真实 unknown/other 不碰撞。参考期是用于建映射的历史数据，不是事前线上已知映射，10 月 8 日后不参与选择。人工 TopK=2 与真实常量 200 隔离。
- is_first_seen_day：`first_seen:true/false`，用户同日互斥。

同一日期、同一维度的事件/购买事件/金额可加总；前三个维度的用户、购买用户可能重叠，不可加总。is_first_seen_day 的用户及购买用户额外核验可加性。四个维度之间不可再求和当总体。unknown 的事件和购买金额覆盖单列，不隐藏缺失。

## 执行与验收边界

所有表带指标、解析、日期和品牌规则版本、映射内容指纹、输入身份、来源 run 和完整观察窗口；本次输出 run 信息在本地收据。事实→first_seen/品牌关联分别守恒；四张表主键唯一、无空键，写后逐列 schema/行数/双向多重集对账。日指标与独立事实 SQL、既有逐日基线核对；维度逐日守恒。仅收回至多 31/32 个日期汇总、4 个维度覆盖汇总、200 个品牌映射；不 collect 事实或用户日。

独立人工字面预期先行，空输入返回空表，不虚构零日期；单独验证零分母表达式。人工同输入新 run 逻辑一致；输出目录排他创建，失败 staging 不发布。真实先运行一次，原事实只读，预算累计 10 GiB、空闲至少 150 GiB。Spark 内部核对不能替代 T1.4 DuckDB；没有正式漏斗、实验或业务因果结论。
