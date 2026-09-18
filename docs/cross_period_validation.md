# T4业务增强：10–11月持续性与品类差异验收

2026-09-18；状态：done（本轮工程及报告交付，本人解释未代验）。主结果为[双月业务复核](../reports/cross_period_business_review.md)：总体不是单向持续下跌，electronics主要随大盘；computers有重复相对偏弱但月底反弹。11月15日零purchase、16–17日峰值使总体购买事件覆盖/时间对账成为最高优先。本轮没有继续查询SKU、交易侧、其他月份或T4.5/T5。

起点`2ad666f7cb01574d13b0859d3f5393b4a5c36dc9`，初始工作区干净、remote main一致、仓库private。项目目录末尾U+0020保留。旧十月分析范围、两小表、事实、原始文件、旧案例/备忘录、原manifest、依赖锁和历史收据不改。新的来源及结果身份独立登记在[范围](../reports/cross_period/analysis_scope.json)和[来源清单](../reports/cross_period/source_manifest.json)，不是悄悄扩写原scope。

## 数据与来源

实际从原作者Kaggle说明中的REES46自有链接取得一份`2019-Nov.csv.gz`。目录v8是上下文；未声称外链有签名版本。来源/条款、远端HEAD和本机测量的区别见[来源说明](cross_period_source_scope.md)。

| 对象 | 本机bytes | 实测SHA256 |
|---|---:|---|
| gzip | 2,890,421,023 | `7d9932fdf2667f3d800655f55a623d7f71b22ff8d606da55bf93cfc307ebf213` |
| 解压CSV | 9,006,762,395 | `addd9a27ed99abdece368019ebfba19568972c7fcbe949db3484aab8a3bcffec` |
| 用户候选CSV | 445,979,066 | `46d918b3049ba540429519bd0f44852408910a00ce4ab48d569b429352d10e05` |

网络文件载荷就是完整gzip的2,890,421,023 bytes，不是抽取样本的字节数；不含少量HTTP元数据/协议开销。gzip CRC通过。源实测67,501,979记录，时间2019-11-01 00:00:00至11-30 23:59:59 UTC；候选3,340,951记录、184,855原始用户ID，时间00:00:05至11-30 23:59:57。双方30天都有记录，不等于上游完整。目标用户概率5%，实际事件抽取比例约4.9494%，全源去重用户数not_measured。

样本行为view/cart/purchase为3,145,326 / 150,065 / 45,560；21,955购买用户，合法观测金额13,878,438.48。时间、ID、未知行为、非法/缺失/非有限/负/超精度金额计数均0；零价格view8,736、cart206、purchase0。category_code缺失1,074,320，brand缺失453,959，session缺失0；非空不可解释category格式0。全部原九字段及重复记录保留。抽样没有读取/固定十月用户ID清单，11月新匹配用户自然进入。

## expected / actual / pass

| 核验 | expected | actual | pass |
|---|---|---|---|
| 官方对象及预算 | 一份11月原发布方对象，≤4GiB载荷 | HTTP长度/ETag、gzip CRC、全字节SHA一致；未重复下载十月 | true |
| CSV结构与窗口 | 原九字段、每记录9列、完整扫描，不用物理行数 | 67,501,979记录；结构/坏时间/越月0，30天观察到 | true |
| 固定用户选择 | 同ID跨月一致、允许新匹配ID；原值/顺序/重复保留 | 原selected函数；候选全量重读、独立uint64阈值、序列哈希及SQLite去重通过 | true |
| 解析独立性 | 冻结SQL与标准库csv/datetime/Decimal一致 | 3,340,951行双向EXCEPT ALL均0差异，包含原字段、派生字段、质量标记和重数 | true |
| 日期/用途 | 原质量规则，不因有日志就声称交易完整 | 30天count/amount允许并有维度缺失警告；11/15为no_purchases，M空值，业务覆盖仍待取证 | true |
| 日指标 | U/B/事件/购买/Decimal金额与独立oracle一致 | 30天逐日精确一致；用户日归并不漏/不重 | true |
| 品类指标 | 事件/购买/金额逐日守恒，unknown保留 | 420行、14桶×30天，与独立expected字段计算一致；按日合计全部相等 | true |
| 导出类型与重读 | 计数BIGINT、金额Decimal，逻辑内容不变 | 修正聚合整数导出类型后30/420小表重读一致，无CSV重解析 | true |
| 旧十月 | canonical唯一快照、原身份/文件指纹/结果不变 | 原选择器及已审查manifest兼容复用；31天检测核心数值和原两品类贡献逐项一致 | true |
| 固定比较 | 61天、全部9周五、11月30日，不使用未来 | 独立日历、median/MAD、品类自身/大盘差、覆盖和31/30日均复算通过 | true |
| 边界/回归 | 缺日、零/MAD、分母、跨月、新用户、原接入默认保持 | 53项相关人工及回归通过；11/15份额/M空值未填0 | true |
| 报告/图 | 只来自脱敏汇总，不新增明细切片 | 3张新图逐张检查、Artist值与CSV一致；旧图未重绘 | true |

先运行小型人工测试，再真实计算；独立oracle为流式标准库＋SQLite，不存全事件Python列表。DuckDB仅使用既有1.5.5/项目Python3.11.15，复用原T1.4解析SQL及T1.1日期规则；小型SQL只摘出冻结日/品类口径，不重建first_seen、品牌、漏斗或Criteo。未启动Spark、安装依赖或修改锁。

## 导出边界与运行记录

`nov-source-01`下载/解压成功，`nov-sample-01`完整扫描/候选重读成功。`nov-metrics-01`完成独立解析、日/品类聚合及值守恒，但第一次`review-01`发现DuckDB将HUGEINT聚合计数写为Parquet DOUBLE；现有计数均在精确整数范围内，数值未变。没有放宽预期或以浮点容差掩盖：SQL显式CAST BIGINT，补物理类型人工测试，并只读30/420行新小表重新导出到`nov-metrics-02`，旧nov-metrics-01及收据保留。

修正导出过程中两个启动/API错误发生在任何输出前，留有本地记录；`review-02`因尚无完成收据拒绝。最终唯一双月结果`review-03`引用`nov-metrics-02`及旧十月metrics-month-01，通过后发布。没有再次扫描真实CSV或生成第二套事实。原十月未参与这些输出修复。

计时范围分别记录，不相加为性能基准：下载/解压及发布321.192秒；源扫描/样本核验256.854秒；独立oracle＋DuckDB解析/指标117.972秒；小表类型修正0.068秒，双月计算0.088秒（小表处理，不是性能对比）。DuckDB限制threads4/memory2GB/temp12GiB；峰值内存not_measured。最终本地新增约14.75GiB，仍远低40GiB，空闲约503GiB，超过150GiB；包括保留的失败记录、JSONL、SQLite、DuckDB及图缓存。原始载荷小于4GiB。所有真实明细和机器路径仅在被忽略的.local/t4_cross_period。

分析范围批准只针对该公开样本的声明用途；11/15的日志零购买不证明真实零交易。没有SKU、库存、渠道、入库/补发或交易侧控制总数，不声称定位了真实原因，也不以11月上涨证明原事故修复。T4.5、T5、后续月份、全项目门槛和本人解释项不提前执行或勾选。

## 复核入口

在实际项目根目录、现有环境与本地收据下：

```sh
.venv/bin/python -m unittest tests.test_cross_period tests.test_diagnose tests.test_ingest tests.test_user_sampling -v
# 以下真实处理仅在明确获准复跑时使用；已有产物拒绝覆盖。
.venv/bin/python ingest/november_source.py acquire
.venv/bin/python ingest/november_source.py sample
.venv/bin/python scripts/review_cross_period.py metrics
.venv/bin/python scripts/review_cross_period.py review --run-id review-NEW --november-run nov-metrics-02
```

acquire若存在完整登记则核对内容后复用，不重新下载；sample/metrics已有run会拒绝。全新执行使用已修复的BIGINT输出，可选默认nov-metrics-01；本轮已交付的canonical小表是nov-metrics-02。`scripts/plot_cross_period.py`只读取本轮安全CSV，复用已有绘图解释器；新图目录排他创建。原始下载/失败/修正/校验/预算收据均只留本地，提交脱敏清单与结论。
