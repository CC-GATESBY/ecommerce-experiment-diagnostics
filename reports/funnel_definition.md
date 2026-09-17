# 行为覆盖与 24 小时顺序漏斗 v1

规则版本：`rees46-funnel-v1`。本定义在人工验证和真实事实读取之前冻结；实现错误可以修复，不能根据真实结果调整定义。沿用 v4 §4.2、T2.1 与本轮明确补充；T1.5 的历史范围配置不改写。

## 输入与粒度

唯一分析范围 `rees46_oct_user5_analysis_v1`，事实 `month-v101-01`，通过 FactReader 的 count 日期规则读取十月全部合格事件；主口径 `baseline_keep_all`，不合并复验 run，不采用 T1.2 假设过滤。行为覆盖分别以事件和行为去重用户计数，整月用户独立去重；包含缺 session 或无效 product 的合格事件。只输出实际出现的行为，不补造 remove_from_cart。

路径主键 `(scope_id,user_id,user_session,product_id)`。有效 ID 依据既有 missing/invalid 标记，session 非缺失；字符串不 trim、不改写。每个有效键只用完整十月中最早合格 view 建一个起点，不每天重置、不重切 session。同秒重复 view 不增加路径；缺品牌、品类、价格不删除起点。不可建路径的事件按 user ID、product ID、session 的优先级互斥披露，同时保留逐项重叠标记计数；无 view 的有效键不制造路径。

## 时间和严格顺序

观察区间 `[2019-10-01T00:00:00Z,2019-11-01T00:00:00Z)`；正式起点区间 `[2019-10-01T00:00:00Z,2019-10-31T00:00:00Z)`。起点所属日为 first_view_time 的 UTC 日期。后续条件 `v < t <= v+24h`，并处于观察区间；所有阶段共享同一 v 和截止点。31 日起点 `right_censored`，不进正式分母，但31日事件继续作为其他路径结果。声明的观察覆盖不是最后一条事件证明的上游完整性。

分别保存 has_cart_after_view、has_purchase_after_view、has_three_step（存在 `v<c<p<=v+24h`）。严格类别按以下优先级互斥：

1. `view_cart_purchase`；
2. `view_purchase_no_confirmed_intermediate_cart`；
3. `view_cart_no_observed_purchase`；
4. `view_only`。

实现先对窗口和起点过滤，再取该窗口最早 cart 和最晚 purchase 验证是否存在严格 cart<p。这是存在性等价判断，能识别 view→purchase→cart→purchase；不能用全局最早 purchase 判定。另以 `v<=c<=p<=v+24h` 计算允许同秒排序时可能的最高类别。可能类别与严格类别不同才标 `order_uncertain`；已有严格三步不被无关同秒排除。不使用行序、分区序、行为排序伪造时间证据。

互斥 release_status 优先级：`right_censored`，其次 `order_uncertain`，最后 `formal`。另保存两项独立布尔标记（允许重叠），其分母为所有有效有 view 的路径。正式子集必须起点合格、观察完整、类别可判。第二类不等于真实未加购，第三/四类不等于永久流失。正式比率仅用于此可判定子集，不外推所有访问机会。

## 首次 view 价格

只检查最早 view 时刻的全部 view，使用既有 Decimal(18,2)；不看购买价。若存在多个不同的有效非负价格，状态 `conflicting`；否则任一记录缺失、非法或负值导致 `invalid_or_missing`；否则唯一非负价格为 `unique_valid`。冲突优先于坏值，另保存坏值记录数和有效价格种数，避免掩盖混合原因。有效值与坏值混合也归 unknown，不任挑有效记录。零为真实价格。价格仅影响分组，不影响路径是否保留。

价格带固定为 `[0,20)`、`[20,50)`、`[50,200)`、`[200,+inf)`、`unknown`。汇总只提供整体、实际出现正式路径的起始日、全部五个价格桶（零路径桶明确为结构性空桶）。无正式路径时整体行仍存在，日行为空；这不意味着原始日期零事件。

## 分母与核验

在相同 formal 子集上：N_view=路径数；N_cart=严格后续 cart 标记数；N_purchase=严格后续 purchase 标记数；N_three_step=严格三步标记数。四比率为 N_cart/N_view、N_three_step/N_cart、N_purchase/N_view、N_three_step/N_view。每项独立保存分子、分母；零分母为 null 并附 `zero_denominator`。展示浮点比率，整数计数精确核验。purchase 后 cart 而无后续 purchase 可同时计入 N_cart 与 N_purchase，但不计入 N_three_step。

检查三步≤cart≤view、三步≤purchase≤view，四类和=路径数，日期与价格桶各项计数和=总体。不能相加日用户当月用户、相加或简单平均桶比率当总体。

购买事件审计以以下顺序互斥分类，保留重复重数：`invalid_path_key` → `no_view_same_key` → `purchase_at_or_before_first_view` → `start_outside_formal_range` → `beyond_24_hours` → `within_path_window`。最后一类不是成功路径数，也可属于顺序不确定路径；它只证明事件窗口关系。所有类别合计等于31日购买事件数。提供整月及逐日计数。

唯一键起点左关联回全事件，核验总行数、日/行为数量和去重用户不变；无键事件仍保留。路径唯一键、时间见证、正式分类守恒及写后 Parquet schema/行数/双向 exceptAll 全记录核验通过后才发布完成收据。事实、指标、范围和原始证据不可修改。

## 证据与限制

人工记录不超过100条；独立标准库穷举小样本的事件组合，并用字面预期验证边界；真实数据仅受控读取一次上下文。路径明细、真实 ID、机器路径和日志只留 `.local/t21/`。这只是固定用户单月日志中的顺序证据，不是用户意图、因果、订单或全平台转化率。后续 T2.2 须单独授权。
