# Criteo 稳定身份与封存划分契约

冻结日期：2026-09-17；本契约在真实划分前写入。仅执行 T3.1；不计算 ATE、显著性、异质性或特征统计，不根据划分结果改规则。

## 输入及身份

唯一来源 `criteo_uplift_v2_1_corrected`，版本 `corrected_v2.1`；从 `data/manifest.json` 精确定位已完成登记的只读 CSV。预期 3,248,115,221 bytes、13,979,592 条数据记录；运行前重新核对身份、长度、完整 SHA256 和 header。raw 与 T0.4 registry 不改写、不下载副本。

源 SHA256（下文 S）：`e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`。

header 顺序：`f0,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,treatment,conversion,visit,exposure`。

`row_identity_version=criteo-row-id-v1`。严格 CSV 解析后，表头不计入，第一条逻辑数据记录 ordinal=0，之后每条加1。引号内换行不增加 ordinal；空文件、仅表头、字段宽度错误、非法 treatment 或 QC 二元标签均失败，不发布 complete。

```text
row_id = SHA256(UTF8("criteo-row-v1|" + S + "|" + decimal(ordinal))).hexdigest()
```

decimal 为非负整数十进制、无前导零（零写0）。row_id 不使用任何字段内容；相同内容的两条记录因 ordinal 不同仍是不同观察单位。源字节身份变化意味着身份命名空间变化，必须重新验收来源。不得使用 Python hash、Spark 分区序号或只对整行内容取哈希。

## 固定分层划分

`split_version=criteo-stratified-hash-split-v1`；`split_seed=20260917`。没有运行时换 seed 或调阈值选项。

```text
payload = "criteo-split-v1|20260917|t=" + treatment + "|" + row_id
h = unsigned_big_endian_uint64(SHA256(UTF8(payload)).digest()[0:8])
TRAIN_THRESHOLD = (3 * 2**64) // 5 = 11068046444225730969
VALID_THRESHOLD = (4 * 2**64) // 5 = 14757395258967641292
h < TRAIN_THRESHOLD                 -> train
TRAIN_THRESHOLD <= h < VALID_THRESHOLD -> valid
VALID_THRESHOLD <= h                -> test
```

treatment 原字符串0/1用于分层，让两个arm分别使用相同60/20/20概率规则；这是分析数据划分，不是重分配原实验 treatment。conversion/visit是结果，exposure是处理后字段，均不得参与划分；f0–f11也不参与，以免特征处理变化改变成员身份。

有限样本比例无需精确60/20/20。冻结工程保护线：任一 arm 内任一 split 偏离目标超过0.5个百分点即停止调查，不换seed、不移动记录。这不是SRM检验；0.85只是公开文件的观测/官方舍入参考，不验证原广告实验随机分流是否合格。

## Membership 与摘要序列化

仅写 `.local/t31/<run>/staging/split_membership.tsv.gz`；完整核验后原子重命名为 `complete/`。已存在 run 拒绝覆盖。UTF-8、LF；逻辑表头严格为 `source_record_ordinal\trow_id\ttreatment\tsplit\n`，四列按源 ordinal 排序。gzip固定 `mtime=0`、`compresslevel=6`、空文件名；不生成完整未压缩中间文件。

overall logical digest 对含表头的全部未压缩 TSV 字节计算SHA256；compressed digest 对完整gzip字节计算SHA256。每个split及每个treatment×split的序列digest，都按源ordinal顺序更新 `UTF8(row_id + "\n")`，不含表头，不依赖集合或字典遍历顺序。SHA256是记录身份的抗碰撞表示；工程上逐条核对源ordinal、身份公式、成员归属与全序列digest，不维护14M身份集合。

预先固定QC：全量四个二元字段0/1计数；按split和treatment×split的n、conversion/visit/exposure count及rate；arm内split占比。rate分母是对应分组全部记录。**label rates are predeclared split-QC summaries, not split optimization targets.** 不计算组间效果，不因标签率差异挑seed、选特征或断言泄漏。

## 独立核验与封存纪律

主实现使用标准库csv解析；第二实现使用T0.4已验证的独立CSV状态解析器，再独立写出ordinal、row_id、hash阈值判断与摘要序列化。第二实现从raw独立重算，不以主summary作expected；同时顺序读回gzip的每一条，核对四字段及连续ordinal。两套总数、arm×split计数、overall及全部子序列digest必须相等，源四字段计数须与T0.4一致。三个split是连续源记录身份的一次且唯一分配；完整源身份始终是(S, ordinal)，不因重复内容合并。

人工数据验证字面公式、重复内容、跨行字段、阈值两侧、源SHA变化、标签改变不影响划分、可复现gzip、失败隔离与拒绝覆盖。真实只生成一份membership，独立复算验证同种子结果，不为跑分生成第二份产物。未测峰值内存写not_measured；只用小计数器/摘要状态，新增上限4 GiB、保留至少150 GiB，适量记录扫描进度及采样到的最低空闲磁盘。

- train：以后获授权可用于训练与探索。
- valid：以后获授权可用于模型/规则选择。
- test：封存用于预定最终评价，不能用于选特征、模型、切片、调参或改seed。
- 预声明例外：T3.2以后获授权，可按既有固定协议使用全量conversion/visit做总体treatment-control aggregate evaluation；该例外不授权test切片探索，更不能据其表现选择T3.3的f变量或模型。

seal指immutable membership与分析纪律，不删除raw中的test标签，也不声称阻止本机用户读取。Criteo公开数据的非均匀抽样不能恢复原广告主真实incrementality，不可解释为补贴效果；exposure=1不可作为RCT主分析分母。
