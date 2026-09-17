# T1.4 DuckDB 独立核验

2026-09-17：`done`（工程验收，本人解释未代验）。真实核验 run 为 `crosscheck-month-01`，人工最终回归为 `synthetic-02`。本轮只新增独立证据，T1.3 历史报告和指标产物保留。

## 输入与独立性

唯一输入是已登记 `user_sample_candidate`：2,114,081 条、282,405,091 bytes，SHA256 `5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b`。scope 为 `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`，series 为 `rees46_fixed_users_20260916_v1`。实际时间为 2019-10-01 00:00:23 至 2019-10-31 23:59:56 UTC，31 个日期；这仍是固定用户候选，不是源文件全体用户。

待比较的是事实来源 `month-v101-01` 对应的 `metrics-month-01` 四张指标表和品牌映射。逐个明确 Parquet 文件路径读取，不合并不同 run。候选大小、哈希、完成收据与登记共同字段一致。公开 manifest 用报告引用替代本地逐日/逐小时明细，因此按共同字段和明细合计验证，未改写登记文件。

独立 SQL 位于 `sql/validation/`：从原始九个 VARCHAR 字段解析、独立生成日期质量状态、first_seen 和品牌映射，再直接按各粒度聚合。未调用 Spark/oracle 解析函数，未执行 Spark 指标 SQL 生成独立结果；四张 Spark 表只参与比较端。用户日表与日表分别从合格记录聚合，避免用同一中间汇总充当两层独立答案。字段、类型和容差在真实运行前冻结于 [比较契约](t14_comparison_contract.md)。

## 四层与映射逐键比较

| 表 | 独立 expected 行数 | Spark actual 行数 | 缺键/多键 | 空键/重复键 | 类型差异 | 业务字段差异 | pass |
|---|---:|---:|---|---|---:|---:|---|
| dim_user_first_seen | 151121 | 151121 | 0/0 | 两端均0/0 | 0 | 0 | true |
| agg_user_daily | 322660 | 322660 | 0/0 | 两端均0/0 | 0 | 0 | true |
| agg_daily_metrics | 31 | 31 | 0/0 | 两端均0/0 | 0 | 0 | true |
| agg_daily_dim | 6879 | 6879 | 0/0 | 两端均0/0 | 0 | 0 | true |
| brand_mapping | 200 | 200 | 0/0 | 两端均0/0 | 0 | 0 | true |

这里的 expected 来自本轮 CSV 独立计算，历史行数和金额未硬编码进计算 SQL。表内所有业务、状态字段均比较，另核对 40 项表级来源字段，共 99 项字段比较，差异数全部为 0；完整明细见 [crosscheck.csv](../reports/crosscheck.csv)。字段比较在 DuckDB 内连接完成，未把用户级表取回 Python。

三张金额表的 `purchase_amount` 最大绝对差均为 Decimal `0.00`。日表 buyer_rate、amount_per_buyer、first_seen_ratio 最大绝对差与相对差均为 `0.0`；仍使用预先冻结的 abs_tol=1e-6、rel_tol=1e-10，未调宽容差。NULL 按空值相等比较，未填成 0；NaN/Infinity 会失败。

整月 first_seen 的 151,121 个用户键、UTC 时刻、日期逐值一致。品牌参考期固定在 10 月 1–7 日，独立 Top200 的品牌、排名、参考事件数、typed key、标签全部一致；10 月 8 日以后事件未参与选取。不是仅比较一个映射哈希。

## 日期质量与 10 月 5 日

31 天独立计数/金额状态均与已登记规则及历史结果一致：计数允许 31 天，金额允许 31 天，购买金额异常 0，购买零价格 0。原始缺品牌 299,547 条、缺品类代码 669,421 条，session 缺失 0；维度缺失保留 unknown，不能据此声称品牌/品类完整。

独立全月结果为事件 2,114,081、用户 151,121、购买用户 17,121、购买事件 37,019、合格观测购买金额 `11598630.22`，有效复合会话 460,550。用户数和会话数重新去重，未相加每日值。金额使用原 price 单位，不解释为订单收入或财务收入。

| 2019-10-05 UTC 核验项 | 独立 expected | Spark actual | pass |
|---|---:|---:|---|
| 事件 | 65613 | 65613 | true |
| 用户 / 购买用户 | 9654 / 828 | 9654 / 828 | true |
| 购买事件 | 1157 | 1157 | true |
| 观测购买金额 | 392555.09 | 392555.09 | true |
| 会话 / 购买会话 | 13756 / 989 | 13756 / 989 | true |
| 窗口内首次出现用户 | 6195 | 6195 | true |
| 金额状态 | complete_observed | complete_observed | true |

该日 buyer_rate=`0.08576755748912368`，amount_per_buyer=`474.1003502415459`，first_seen_ratio=`0.641702921068987`；三个比率均一致。first_seen 从整月上下文计算，再选择 10 月 5 日，未把单日第一次出现当作新增用户。全 31 天结果见 [crosscheck_daily.csv](../reports/crosscheck_daily.csv)。

## 人工及失败重试验收

主人工 CSV 为 18 条，解析边界 CSV 为 25 条，共 43 条；两个人工运行复用同一输入，不复制原始人工记录。另有一次 1 条 CSV 设置探针和临时结构错误用例，总规模仍不足 100。正常/缺失/非法时间、ID 前导零和 LF/CR、引号与跨行、金额 0/20/50/200、精度/小数位、多符号非有限值、维度缺失均有检查。人工边界字段与字面预期比较，并做两引擎原值/标记多重集核对。

| 检查 | expected | actual | pass |
|---|---|---|---|
| 单元回归 | 4 项通过 | 4 项通过 | true |
| 最终人工集成 | 全部断言满足字面/独立预期 | 150 项通过 | true |
| 重复购买保留 | 10月1日2次购买、1买家、金额100.00 | 一致 | true |
| 跨日/同名 session | 按用户与日期正确计数，保留全窗口上下文 | 一致 | true |
| 无购买与坏购买 | 10月3日0.00/no_purchases；10月5日金额NULL、买家仍2 | 一致 | true |
| 同输入不同 run | 五表逻辑多重集差异0 | 差异0 | true |
| 同 run 再写 | 拒绝覆盖 | FileExistsError，原内容不变 | true |
| 输出一天扩为两天 | 旧10月5日不变；10月8日仅1行 | 五表核对通过；两日9事件 | true |
| 中途失败 | 实际 build 失败后保留 staging，不允许发布/读取 | 日期门禁不匹配导致失败；两接口拒绝 | true |
| 新 run 重试 | 与已完成两日快照一致，只选一个结果 | 差异0，最终两日9事件 | true |
| 多路径/通配符读取 | 拒绝合并快照 | 明确拒绝 | true |
| 品牌边界 | 参考期后新增品牌不入Top；并列按字节排序；保留typed key | 一致 | true |

测试使用既有 `build_metrics` 和 `publish`，未创建假的写入发布流程。失败注入是验收预期，不是未解决的运行故障。读取选择器只选一个成功快照。追加证明的是固定观察范围下扩展输出日期、本地串行快照选择；没有实现原地物理分区 append、并发事务或分布式幂等。

第一轮人工集成通过后，补充了收据脱敏格式验证和边界字面断言，再用同一 43 条输入跑最终回归。最终通过后才执行一次真实 DuckDB 核验，没有重跑真实 Spark 指标作业。

## 版本、资源与不可变证据

项目 .venv 新增 **DuckDB 1.5.5**，使用适配 CPython 3.11/macOS arm64 的官方 PyPI wheel，未源码编译。wheel 15,493,704 bytes，SHA256 `0c42757cb34722144bd4dfb94b6f336339e7b2468f6813fa7fa9a319ba07bab4`。来源见 [PyPI 版本页](https://pypi.org/project/duckdb/1.5.5/)及 [DuckDB Python 安装文档](https://duckdb.org/docs/stable/clients/python/overview)。安装报告只留本机。

实际 freeze 锁只新增 `duckdb==1.5.5`；Python 3.11.15、JDK 17.0.19、PySpark 3.5.8、PyYAML 6.0.3 及其他原锁版本未变化，pip check 通过。未安装 pandas/pyarrow 或修改全局环境。

人工 Spark 为 local[4]/4g/UTC，先停止 Spark 再运行真实 DuckDB。DuckDB threads=4、memory_limit=`2GB`（引擎显示约 `1.8 GiB`）、独立 temp、max_temp_directory_size=`8GiB`，累计预算另以每秒采样控制，memory_limit 不是进程 RSS 硬上限。

| 资源/保护项 | 实测 |
|---|---|
| 两次人工启动至完成 | 42.944 / 42.362 秒 |
| 真实核验阶段 | 9.144 秒；从创建核验 staging 后计时，不含前置身份/哈希检查 |
| 本地校验数据库 | 160,444,416 bytes |
| 累计新增产物采样高水位（含安装包落地） | 219,840,792 bytes，约0.205 GiB；低于10 GiB |
| 采样最低空闲 | 563,514,232,832 bytes，约524.814 GiB；高于150 GiB |
| 峰值进程内存/CPU峰值 | not_measured / not_measured |
| 既有本地文件元数据保护 | 756 个文件大小、mtime、inode未变 |
| 指标/登记/历史证据内容保护 | 78 个明确文件前后SHA256一致；候选SHA亦一致 |

采样高水位不是瞬时峰值。计时仅是本轮工程记录，不作为性能基准。未读取完整源 CSV，未重建真实事实或指标，未修改旧 manifest/覆盖表/质量表/T1.1 收据/T1.3 报告。

## 复跑与剩余边界

在保留末尾空格的项目根目录运行；沿用 `config/local.yaml`。复制脱敏模板为被忽略的 `config/crosscheck.local.json` 并填写已登记候选、指标快照、登记、人工成功收据四个明确路径。空路径不能通过；不能使用通配符或多快照。人工和真实 run 目录都必须是未存在的新路径。

```sh
.venv/bin/python -m unittest discover -s tests -p test_idempotency.py -v
.venv/bin/python scripts/run_crosscheck.py --run-dir .local/t14/synthetic-NEW --runtime-config config/local.yaml --budget .local/t14/budget.json
# 人工成功且 Spark 已停止，将本机配置 synthetic_gate 指向新成功收据后：
.venv/bin/python tests/crosscheck_duckdb.py --config config/crosscheck.local.json --run-dir .local/t14/crosscheck-month-NEW --budget .local/t14/budget.json
```

本轮预算文件保留最初 `.local` 字节基线，`max_new_bytes=10737418240`、`minimum_free_bytes=161061273600`，依赖落地 `dependency_bytes=46430370`；复跑不能重置基线来绕过累计预算。真实执行要求当前代码与人工收据哈希一致。临时数据库、用户级数据、差异明细、原始日志、真实配置与绝对路径均只在 `.local` 或忽略配置中。

无未解决的工程差异；本人解释未代验。两套实现一致与人工字面测试提高可核验性，仍不能证明上游日志无漏数、共同文字契约绝对正确或候选代表全平台。T1.5、Criteo/T0.4、总 G0/G1 及后续任务不提前勾选。下一项唯一建议为 **T1.5：基于已核验数据冻结首版分析范围**，不默认新增月份或处理全量。
