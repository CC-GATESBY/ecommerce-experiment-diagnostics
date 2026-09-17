# T2.2 描述性报告规格 v1

版本 `rees46-behavior-report-v1`；2026-09-17，先于图表和真实新增聚合冻结。仅回答日观测购买金额与U/R/M、既有路径结构、category_l1金额集中度及UTC小时购买分布，不执行T2.3、T4归因/异常或因果分析。

## 唯一范围与来源

- analysis scope：`rees46_oct_user5_analysis_v1`；固定用户目标抽样概率5%，实际事件比例不称用户比例，金额不乘20外推。
- 观察窗口：`[2019-10-01T00:00:00Z,2019-11-01T00:00:00Z)`；fact `month-v101-01`、metric `metrics-month-01`、funnel `funnel-month-01`；主口径 `baseline_keep_all`。
- 日/维度数据从已验收指标快照的明确Parquet文件读取，只读取31日日指标及category_l1的小型日维度汇总。DuckDB仅作现有Parquet读取器，不重做T1.4独立ETL核验。
- 漏斗复用T2.1已发布CSV并对照完成收据，不重算路径。历史收据lineage.funnel_run误写为staging；本轮以明确funnel-month-01目录、成功launch/validation、原提交与结果内容确认身份，保留旧字段不改写并披露，不选择任何其他run。
- 只为UTC小时聚合启用一次既有Spark，通过FactReader只读一个事实批次；不读真实CSV，不重建事实/指标或修改历史证据。

## 词义、加总与缺失

V=purchase_amount，仅称观测购买金额/日志口径购买金额，原price单位，不称财务收入、GMV真值或订单收入。U=active_users，B=buyers，R=B/U，M=V/B（购买用户平均观测金额，不是客单价或订单均价）。first_seen仅为窗口内首次出现。

V=U×R×M仅作一致性检查，沿用既有绝对1e-6、相对1e-10浮点容差；整数和Decimal精确比较。不计算因子贡献或相关系数。日期amount不允许或金额缺失不得填0；当前固定范围必须有31个已放行日期，否则拒绝生成完整月报告。合格范围内不存在购买的小时才可补结构性0。所有比率零分母为null并带原因。

日/品类/小时去重用户不可相加为月去重；不同品类和小时用户也可重叠。仅有日维度汇总不能计算整月品类去重人数；未获额外事实聚合授权时保留user_days与buyer_user_days，月users/buyers标not_measured，不冒充月去重。品类金额与购买事件可按日期/类别相加，unknown必须在总金额分母中。

漏斗比例仅适用formal子集，按冻结路径键/首次view/24小时规则。N_cart与N_purchase不是严格嵌套，不能用传统逐层收窄漏斗表达；同秒不确定、右截尾分别保留，非流失。价格带用首次view价格，unknown零路径显示NA。价格差异只称当前样本描述性关联，尚未控制品类、品牌、商品和用户构成。

## 固定摘要规则

- 日：31天完整表，U、B、购买事件、V、R、M、first_seen_ratio的min/max/median及所有并列极值日期；不搜索其他切片。仅在金额最高/最低日并列展示U/R/M；不作贡献分解。
- 品类：category_l1全类别汇总；按金额降序、typed key升序打破并列；Top10（不足10全部保留）、Top1/5/10金额累计份额，unknown独列。unknown若进入Top10正常保留，图和分母一致，不删后重算。
- 小时：UTC 0–23全桶，购买事件、小时内去重购买用户、合格观测金额、购买事件占比；仅报告所有最高/最低小时。没有业务时区信息，不推断当地作息，不直接推荐投放时段。
- 路径：只展示T2.1整体及五个首次view价格带的已冻结四比率和四种互斥类别，不新增分层、窗口或过滤。

最高/最低只是描述极值，不叫异常；不预设促销、节日、事故。阶段总结固定A本期范围、B三个有数字/来源/分母/含义/限制的观察、C最多三个值得核查的问题，不提出确定业务方案。

## 八张图与证据

matplotlib（不用seaborn），独立PNG，不用subplot、多y轴或手工颜色主题。四张日图共用完整十月UTC横轴，y轴从0起；小时显示UTC；漏斗用独立比率条及分子/分母，价格unknown显示NA。

图名：daily_purchase_amount、daily_active_users、daily_buyer_rate、daily_amount_per_buyer、funnel_overall、funnel_by_first_view_price_band、category_purchase_amount_top10、purchase_events_by_hour_utc。每张图标注analysis_scope、粒度、单位/分母、UTC、限制与来源CSV；渲染后逐张检查可读性。matplotlib只消费已保存CSV，记录读取值及CSV指纹供逐项核对。

新增脱敏表：behavior_daily.csv、behavior_daily_stats.csv、category_concentration.csv、hourly_purchase.csv；漏斗直接引用旧CSV。用户级数据、机器路径、原日志和完成收据只留.local/t22。主环境不安装包；若项目无matplotlib，复用已存在本地绘图环境，仅消费脱敏CSV，不向Anaconda base安装依赖。

先人工小型汇总测试极值/中位数、Top10/累计占比、unknown、零分母、24小时桶、空或少类别、用户非加总、图输入。真实CSV由标准库独立算术复核；日表/漏斗对历史、品类及小时对月金额与购买事件、unknown对原覆盖、原始证据不可变全部通过才能完成。新增预算2GiB，空闲至少150GiB；耗时只作运行记录，不比较性能。
