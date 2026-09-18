# T3.2 总体评估验收

## 运行前固定的方法与范围

估计对象为 published corrected Criteo benchmark sample 中的 treatment assignment ITT group difference（公开随机实验基准样本中的组间增量估计）。仅使用 T0.4 已登记的 corrected v2.1 CSV；不按 exposure 筛选，不分 train/valid/test，不探索匿名特征。conversion 是主结果，visit 是辅助结果，exposure 只描述两组实际曝光相关比例。

全部 assigned 记录进入各自 treatment 分母，不以转化、访问或实际曝光决定是否入组。用显式字符串 schema 读取16列，二元字段仅接受0/1，再按 treatment 汇总 n 与三项标签总数；只取回两行。源CSV既有完整SHA证据由T0.4/T3.1承接，本轮检查清单、完成收据、只读权限、size/mtime及运行前后stat；不为重新计算哈希额外扫描源文件。Spark只扫描真实CSV一次，不读取membership内容。

方向固定为 treatment−control。绝对差使用两组样本率之差；SE采用非合并的两独立二项比例标准误，95%区间为差±1.96×SE。用40位Decimal计算并输出字符串；第二套math标准库公式独立核对两行充分统计量。独立公式浮点对账的绝对容差1e−14、相对容差1e−12，只处理计算表示差异，不改变计数。

低频检查固定为两组成功/失败四个格子最小值至少5，属于项目正态近似诊断，不是行业统一保证。小于5时保留点估计/SE、不给Wald区间，返回 sparse_cells_ci_not_reported；空组返回empty_group；control率为0时相对提升为空。exposure不输出相对效果、推断区间或每万人业务增量。

同一输入复跑分两层：人工CSV完整重聚合两次；真实CSV只扫描一次，将仅两行汇总缓存并读回两次，效果公式从这两行重算一致。后者不冒充第二次独立真实CSV扫描。独立核验只处理最终小表，不构建第二条全量pipeline。

区间是公开样本上的独立二项大样本近似，不能量化非均匀发布抽样、广告主间结构、未提供聚类标识或外推误差；不计算p值、SRM、ROI或原广告主总体incrementality。下列为实际通过后的结果，不把近似区间当作原广告主总体的效应区间。


## 实际结果与最低必要验收

T3.2 **done（工程验收，本人解释未代验）**；完成日期2026-09-18，唯一成功真实run为`criteo-itt-v1-02`。conversion与visit完整精度、SE、区间、每万人换算在[效果表](../reports/criteo_effects.csv)，业务结论先读[一分钟摘要](../reports/criteo_business_summary.md)与[总体评估](../reports/criteo_ate.md)。没有计算p值、ATE切片、特征统计或ROI。

| treatment | n | conversion_count | visit_count | exposure_count |
|---|---:|---:|---:|---:|
| 0 | 2,096,937 | 4,063 | 80,105 | 0 |
| 1 | 11,882,655 | 36,711 | 576,824 | 428,212 |

| 检查 | expected | actual | pass |
|---|---|---|---|
| 人工数据与公式 | 20条：两组n=10；conversion=2/5，visit=4/7，exposure=0/6；差0.3，SE=√0.041 | Spark计数、手算和实现一致 | 是 |
| 边界与回归 | 空组有状态；零基准relative为空；稀疏不给CI；非法标签/错header拒绝 | 18项测试通过，包含实际元数据形状核对 | 是 |
| 完整样本量及两组分母 | 13,979,592；2,096,937 / 11,882,655 | 完全一致 | 是 |
| source事件守恒 | conversion 40,774；visit 656,929；exposure 428,212 | 与T0.4原profile完全一致 | 是 |
| 已有独立全扫描证据对账 | T3.1预声明QC计数仅按treatment归并后，与本次两组充分统计量一致 | n及三项事件计数完全一致；未计算split效果 | 是 |
| 独立公式 | 两结果的diff、SE、CI、每万人及其区间与另一套math实现一致 | 全部在预定数值表示容差内 | 是 |
| 低频条件 | 两组成功/失败四格最小值≥5 | conversion 4,063；visit 80,105 | 是 |
| 同一输入复算 | 人工CSV重聚合；真实两行缓存重读及公式重算一致 | 一致；真实没有第二次raw扫描 | 是 |
| 输入保护 | raw/membership只读，运行前后stat不变，原manifest/registry/依赖锁不改 | 一致；未打开membership内容 | 是 |

18项测试由13项统计公式测试、4项Spark人工CSV测试和1项只读前置元数据测试构成。人工CSV最多20条；若正常近似不成立，点估计/SE与CI放行状态分开。本轮不是原实验SRM验证。

## 执行、资源与失败记录

沿用项目Python 3.11.15、JDK 17.0.19、PySpark/Spark 3.5.8；local[4]、Driver 4g、UTC，禁用Hive，正常停止Spark。只持久化两行聚合结果于内存，读回后释放；未缓存完整源、复制raw/membership或collect明细。仅元数据指纹沿用已验收的CSV SHA `e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`，本轮未声称重新实测该完整SHA。

首次synthetic-01在Py4J本地端口绑定处被沙箱拒绝，尚未读真实数据；按已授权本地Spark用途取得必要进程权限后synthetic-02通过。首次真实入口criteo-itt-v1-01在元数据比较处提前失败：CSV摘要读取代码遗漏已有invalid=0键；没有开始源扫描。修复适配、加入元数据回归，synthetic-03的18项测试通过后才运行criteo-itt-v1-02。失败日志和收据保留，未改原profile或expected。

成功运行扫描3,248,115,221 bytes一次，Spark初始化后的核验/聚合/计算耗时10.658秒，完整launcher耗时13.399秒；此前失败和人工测试另计，不拼接为性能基准、不进行引擎比较。成功运行结束时本轮本地树54,420 bytes，之后仅增加少量报告/收据；新增预算1 GiB。检查点最低空闲556,269,793,280 bytes，高于150 GiB；这是采样低点，非连续瞬时监测。峰值内存not_measured。

## 复现入口与保留项

```sh
.venv/bin/python -m uplift.ate --run-id synthetic-03 --test
.venv/bin/python -m uplift.ate --run-id criteo-itt-v1-02 --synthetic-gate .local/t32/synthetic-03/validation.json
```

这是本轮实际成功命令，已有run ID拒绝覆盖。未来获授权重跑需新run ID与同版本人工通过收据；输出只到`.local/t32`，本地validation/launch日志不提交。CSV中的空单元格代表null；exposure行的relative/SE/CI/每万人字段留空，因为本轮只把它作为描述性执行信息。保留三行已审查的效果表，不发布任何记录级数据。

T3.1契约、membership、来源清单和历史报告原样保留；T3.3/T3.4均not_started，G0/G1和本人解释项不代勾。本轮没有下载、安装、修改锁或连接REES46。下一项仅建议T3.4下一轮业务实验设计；待授权，不自动执行。

收尾8项小型核对通过：已提交QC按arm归并、效果CSV与运行结果逐字节一致、报告数字绑定、摘要586字符、exposure字段留空规则、旧文件与后续任务状态保护、敏感内容排除。盘点含本地日志及9份安全交付整文件的保守新增量约201 KB，远低于1 GiB；不以大量重复检查替代业务解释。仓库开始时已核对private/main，交付时再次核对；具体commit与远程交付收据只留本地。
