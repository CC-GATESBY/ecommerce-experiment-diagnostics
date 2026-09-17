# T3.1 Criteo 稳定身份与封存划分验收

本轮范围：corrected v2.1既有raw的稳定记录身份及treatment分层60/20/20划分。没有下载、安装、Spark、DuckDB、特征探索、模型或ATE；T3.2–T3.4保持未开始。参考提交 `1b3a4d066f673487b232bbeed91336f8b9c82753`，保留实际目录尾部U+0020。

## 冻结与实现

真实运行前先生成 [划分契约](criteo_split_contract.md)，SHA256 `2e000f009c20fd31f85e09223daf0e9cd38acd0ab953956a8a1c847db5a23e03`。row_identity_version为`criteo-row-id-v1`，split_version为`criteo-stratified-hash-split-v1`，seed固定20260917。原treatment没有重新随机化；结果和特征均不参与身份或划分。标签率只作预声明QC，没有用于选择seed或方案。

`uplift/ingest_criteo.py`仅从已验收manifest定位唯一CSV，核对source/version/status、完成收据、16列header、精确bytes、只读权限与完整SHA。`uplift/split.py`流式写一份四列gzip membership；ordinal从0计数，保留内容完全相同的独立记录。未生成三个完整CSV或未压缩membership中间文件。

主实现使用`csv.reader(strict=True)`，第二实现使用既有T0.4独立CSV状态解析器。后者独立重算ordinal、两次SHA及整数阈值，以另一套计数器重建QC和所有序列digest，不读取主summary作为输入。每条expected membership还与gzip读回逐字节核对；这是全部记录核验，不是抽查。仅共享结果字段封装，不共享身份、划分或计数逻辑。

只用有界当前记录、固定9组统计与摘要状态；没有14M身份集合/list。连续source ordinal、一条一次分配、成员内容和全序列摘要共同证明覆盖与分配互斥。row_id是(SHA, ordinal)的SHA256表示，使用标准抗碰撞假设；不声称运行了14M row_id外部排序或穷举碰撞证明。

## 人工测试

真实运行前43项（21项新划分测试＋22项T0.4接入回归）通过。包含独立字面公式与固定golden值、重复内容、源SHA变化、quoted newline/空字段、header排除、空文件/header-only、错header/少列/多列、非法二元字段、两个threshold两侧、已有产物拒绝覆盖、写入中断不发布complete、gzip确定性、跨进程不同PYTHONHASHSEED仍相同、结果标签及特征变化不改归属、全量读回缺行/多行/篡改及gzip损坏拒绝。

提交测试fixture使用全零synthetic源命名空间，避免测试golden值与真实源前几条row_id重合；更换测试命名空间后43项复跑仍通过，生产算法与冻结契约没有改变。

## 实测

T3.1 **done（工程验收，本人解释未代验）**；run `criteo-split-v1-01`。Python 3.11.15，zlib 1.2.12；未安装依赖，未改依赖锁。

| 检查 | expected | actual | pass |
|---|---|---|---|
| 输入身份 | 固定corrected源SHA/bytes/header | 3,248,115,221 bytes；16列；运行前后SHA一致 | 是 |
| 逻辑ordinal | 0–13,979,591连续且一次分配 | 独立raw扫描逐条对照全部membership | 是 |
| 总覆盖 | 13,979,592 | 13,979,592 | 是 |
| treatment=0合计 | 2,096,937 | 2,096,937 | 是 |
| treatment=1合计 | 11,882,655 | 11,882,655 | 是 |
| 三份样本量 | 独立重算完全一致 | 8,387,273 / 2,797,762 / 2,794,557 | 是 |
| 整体及9个子序列digest | 主/独立实现逐项相等 | 全部一致，成员逐行比对无差异 | 是 |
| source四字段 | T0.4计数原样守恒 | 四字段0/1计数一致 | 是 |
| arm内占比保护线 | 与目标偏离≤0.005 | 六个arm×split均通过，未换seed | 是 |
| 人工与边界回归 | 正例通过、异常拒绝 | 最终45项通过 | 是 |
| gzip与不可变输出 | CRC完整、只读、不覆盖 | 一份gzip、0444；complete目录0555 | 是 |

25项真实运行检查全部通过；实际计数、9组QC率和11个文件/序列digest见[结果清单](../reports/criteo_manifest.md)及[机器清单](../data/criteo_split_manifest.json)。有限样本占比原样保留，标签率没有用于优化划分。

### 发布失败与恢复

主生成134.586秒、独立全量复核61.354秒，初次运行在发布前记录连续200.165秒。全部核验已通过后，因先将staging目录chmod 0555，本机rename返回PermissionError，未产生complete。原failed.json和日志保留，没有把该次发布失败隐藏为一次成功。

实际恢复命令为`.venv/bin/python -m uplift.split --run-id criteo-split-v1-01 --resume-validated`。修复仅将目录只读设置移到rename之后；补充只读目录实际发布与未完成staging禁止恢复的测试，最终45项通过。`--resume-validated`只接受该已记录的发布权限失败；重新核验raw完整SHA、原manifest/registry、契约、原验收摘要和membership压缩指纹后发布同一份文件。恢复核对2.032秒；这与首次运行计时分开，不相加冒充连续端到端性能。没有第二套真实membership或第二次划分，没有seed/阈值变更。

### 资源

输入3,248,115,221 bytes；membership逻辑字节1,132,420,922（未落地），实际gzip 576,697,968 bytes。首次运行产物树盘点576,743,300 bytes（收据写完前），总量远低于4 GiB。首次/恢复采样最低空闲558,789,193,728 bytes，高于150 GiB。最低空闲是检查点采样值，不宣称连续瞬时监测；峰值内存not_measured。未做性能比较或额外跑分。

原CSV运行前后SHA均为`e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`，bytes/mtime不变；T0.4 registry与data/manifest.json字节摘要不变。REES46数据未读取。真实membership、原始日志与恢复收据仅留`.local/t31`；Git提交独立元数据清单，不包含逐条row_id、features或标签记录。

## 复跑与test纪律

```sh
.venv/bin/python -m unittest tests.test_criteo_split tests.test_criteo_source -v
.venv/bin/python -m uplift.split --run-id criteo-split-v1-01
```

第二条是已运行命令；完成后同run ID再次执行必须报错，不覆盖。未来重建需单独授权及新run ID，不能更改算法/seed。失败记录及残留staging只留本地，不被登记为完成。只读权限用于防误写，本轮验证本地串行机制，不声称解决并发事务。

train以后可训练/探索，valid可作规则/模型选择，test只作预定最终评价。预声明例外是以后获授权按T3.2固定协议用全量conversion/visit做总体组间aggregate evaluation；不得利用test的任何切片表现选择T3.3特征、模型或阈值。seal是分析纪律和immutable membership，不删除raw标签、不声称本机无法读取。

0.85是公开文件观测比例/官方舍入参考，不是原实验精确分流概率；0.5pp是代码错误调查保护线，不是SRM检验。非均匀公开抽样不能恢复原广告主真实incrementality；exposure为处理后字段，不筛选exposure=1作RCT主分母。不与REES46连接用户。


收尾：117项汇总/指纹/忽略规则/状态核对通过，148个受保护旧跟踪文件字节不变；T3.2及以后任务段落与G0/G1勾选原样保留。盘点时`.local/t31`文件576,770,577 bytes，加14个安全交付文件整份大小的保守总量576,935,236 bytes，低于4 GiB；空闲558,814,765,056 bytes。后续只补少量文档和交付收据。只放行新的脱敏split manifest，整个data目录仍受忽略规则保护。
