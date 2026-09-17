# T0.4 Criteo corrected v2.1 来源验收

核对日期：2026-09-17。范围仅为官方 corrected 文件的来源、完整结构、字段 domain 与不可变 raw 登记；不生成划分，不计算 ATE，不按 exposure 筛选，不进行特征探索。REES46 既有来源与产物独立保留。

## 来源与版本判定

权威语义入口：[Criteo Uplift Prediction Dataset — Criteo AI Lab](https://ailab.criteo.com/criteo-uplift-prediction-dataset/)。页面 erratum 说明，初版不同广告主的增量水平和特征分布存在差异，使模型可能借特征识别广告主而获得泄漏优势；后续发布 corrected / unbiased 文件，字段不变。本项目只接受 `criteo-research-uplift-v2.1.csv.gz`。

页面及 HF 卡的介绍段仍残留旧版 25M / 11 features 描述；修正版 key figures 是约 13,979,592 行，字段明细为 f0–f11 加四个二元字段。这些页面描述不代替实测，不使用旧版对象。

历史链接 `http://go.criteo.net/criteo-research-uplift-v2.1.csv.gz` 及 HTTPS 对应地址均出现 HEAD 404，但后补的 Range GET 均返回 206 和 2 字节 gzip magic；不能据此声称直链完全失效，也没有验证直链完整内容。鉴于元数据请求失败且响应不一致，本轮按允许的 fallback 选择可固定版本并核对精确长度/LFS摘要的官方 HF；保留上述差异，不再下载历史直链完整副本。最终来源为 [Criteo 官方 Hugging Face 文件](https://huggingface.co/datasets/criteo/criteo-uplift/blob/2424920019e49d52d72c13ac1143ec5d53af276b/criteo-research-uplift-v2.1.csv.gz)，仓库 commit `2424920019e49d52d72c13ac1143ec5d53af276b`。使用固定 commit 的 resolve 地址；没有下载个人重传或两个官方来源的完整副本。

下载前官方仓库 LFS 对象元数据与 HTTP HEAD 均给出 311,422,618 bytes；LFS SHA256 为 `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc`。这是来源一致性线索；下方 archive 实测来自本机重新计算。CDN HTTP ETag 与 LFS SHA 并非同一摘要，未把 ETag 当 SHA256。签名跳转链接不保存、不提交。

## 使用条款及解释边界

AI Lab 页面 CRITEO DATA TERMS OF USE 展示 Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International；[固定版本 HF 数据卡](https://huggingface.co/datasets/criteo/criteo-uplift/blob/2424920019e49d52d72c13ac1143ec5d53af276b/README.md) 标签为 `cc-by-nc-sa-4.0`，本次没有许可展示冲突。记录状态为 `confirmed_consistent`，仅用于本地非商业研究，不再分发 raw 或真实样本；未来商业使用或再分发需重新审查相应用途。

发布方要求引用：Diemert, Eustache; Betlei, Artem; Renaudin, Christophe; Amini, Massih-Reza. **A Large Scale Benchmark for Uplift Modeling**. AdKDD and TargetAd Workshop, KDD, 2018, ACM。原 BibTeX 随官方页面与固定版本数据卡保存在被忽略的本地 evidence 中。

数据来自广告 incrementality tests。公开文件经过非均匀 subsampling，无法恢复原广告主真实 incrementality；也不能改写成补贴业务效果。f0–f11 为匿名特征，不猜年龄、收入、设备等语义。`treatment` 表示处理分组；`exposure` 是处理后的实际曝光相关字段，不可将 exposure=1 作为后续 RCT 主分析分母。本轮只报告每列的边际计数，没有 treatment/control 效果比较。

## 检查实现与失败处理

`ingest/ingest_criteo_source.py` 使用固定文件身份。下载进入新的运行 staging，精确长度、实测 SHA、gzip 完整 EOF/CRC、全 CSV 核验与独立对账通过后才登记。压缩包与原字节 CSV 分别按内容 hash 发布到 `.local/t04/criteo_v2_1/raw/`，文件权限 0444、内容目录 0555；本地 registry 0444。不改 CSV，不生成真实样本。权限是本地防误写措施，不声称具有管理员不可绕过的存储锁。

主实现是 Python `csv.reader(strict=True)`，逐条检查 16 列，不以物理行数代替记录数。空字符串与纯空白分别计数；二元字段仅接受原字符串 `0`/`1`；f 字段仅检查可解析为有限浮点数，不赋予业务语义、不改写原值。空值、非法二元值、非有限/不可解析特征使本版来源放行失败，参考比例没有作为通过阈值。

独立实现不调用 `csv.reader` 或主摘要，以独立 CSV 状态机和计数器重读完整文件。只有排除引号后才能使用单行快速路径；引号、双引号转义及跨行字段独立处理。单记录上限 1 MiB，超限明确失败。独立核对 header、记录数、字段宽度和四字段 domain 计数，未用抽样替代全量核验。

人工测试初次发现 DuckDB CSV 读取未拒绝一个末尾未闭合引号输入；记录该失败后，将第二实现改为上述独立状态机。最终真实文件核验仅使用标准库，不运行 Spark/DuckDB，也未安装依赖或修改锁。原始失败测试日志仍保留本机。

失败/中断保存阶段、类型与可用进度，`.part` 或失败收据不能登记为完整；不删除失败文件。复用既有接入模块的内容去重：相同内容换名仍是同一输入，同名不同内容拒绝。再次执行已登记源时，核对本地内容后复用，不重复下载或累计。

网络文件载荷上限 1 GiB，新本地产物上限 8 GiB，保留 150 GiB。下载前按最多可用解压预算保守检查磁盘；下载、解压及两次扫描中检查预算。峰值内存未测，不为测量重跑。本轮不创建 train/valid/test 字段、不执行 T3.1/T3.2。

## 实测与验收

运行状态：`registered`；T0.4 `done`（工程验收，本人解释未代验）。
run_id：`criteo-v21-2026-09-17T095629.361727_0000`；获取时间：`2026-09-17T09:56:51.387219+00:00`。

| 对象 | 精确 bytes | 本机实测 SHA256 |
|---|---:|---|
| criteo-research-uplift-v2.1.csv.gz | 311422618 | `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc` |
| criteo-research-uplift-v2.1.csv | 3248115221 | `e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef` |

实测 header（顺序完全一致）：`f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, treatment, conversion, visit, exposure`。数据记录数 **13,979,592**（不含表头）；全部记录为16列。结构错误、每列空字符串、每列纯空白、每个 f 字段非有限/不可解析值、每个二元字段非法值均为0。原始 CSV 没有时间字段，时间覆盖记 `not_applicable`。

| 字段 | 0 | 1 | 实测速率（1/全部记录） |
|---|---:|---:|---:|
| treatment | 2,096,937 | 11,882,655 | 0.8500001287591225838350647143 |
| conversion | 13,938,818 | 40,774 | 0.002916680257907383849256830958 |
| visit | 13,322,663 | 656,929 | 0.04699200091104232512651299122 |
| exposure | 13,551,380 | 428,212 | 0.03063122299992732262858601310 |

与页面参考仅作一致性比较：行数差0；以下是实测率减页面参考率，均未作为修正数据的依据。

| 项目 | 页面参考率 | 实測−参考 |
|---|---:|---:|
| treatment | 0.85 | 1.287591225838350647143E-7 |
| visit | 0.046992 | 9.1104232512651299122E-10 |
| conversion | 0.00292 | -0.000003319742092616150743169042 |

exposure 页面未提供对应参考率，不虚构参考。三个已给比率按页面展示精度舍入一致。

| 检查 | expected | actual | pass |
|---|---|---|---|
| 官方对象长度/SHA | 固定commit的LFS值 | 311,422,618 bytes；实测archive SHA相同 | 是 |
| gzip完整读取 | EOF与CRC通过 | 完整解压3,248,115,221 bytes，无CRC错误 | 是 |
| header/宽度 | 16个指定字段；每条16列 | 两套解析器一致；13,979,592条均16列 | 是 |
| 全量独立计数 | 两套实现逐列相等 | 总行数、四字段0/1/invalid计数全部相等 | 是 |
| 缺失/有限值/二元domain | 无缺失、非法及非有限值 | 各字段均0异常 | 是 |
| 人工与既有接入回归 | 正反例按字面预期 | 42项测试通过（22项Criteo+20项原接入） | 是 |
| 重复/换名/异内容 | 不重计/不覆盖 | 人工测试通过；真实已登记输入再次校验SHA后直接复用，无下载、无新增raw | 是 |
| 失败与损坏 | 不得完成登记 | CRC/截断/短下载/结构错误/模拟失败均被拒绝 | 是 |
| raw隔离与权限 | 忽略；只读；无REES46改写 | 78项收尾核对通过，143个受保护旧文件不变，raw/registry被忽略 | 是 |

首次运行连续计时 115.573 秒（请求、下载、解压、两套扫描、内容登记到发布），其中文件传输 20.369 秒、主profile 68.104 秒、独立扫描 19.586 秒。这是本次验收运行计时，不是 ETL/性能比较。执行脚本当时SHA `68c11855bab18ca0f926e9b527a4514ee9c80c29e51f533b637e377934f95862`；之后仅补强已登记收据复用检查，真实profile实现与结果未重跑。

完整文件载荷 311,422,618 bytes，历史入口探测另4 bytes，总文件载荷311,422,622 bytes；HTTP/网页/API等开销未测。raw内容合计3,559,537,839 bytes。登记时source目录总文件量3,559,646,388 bytes；运行前可用563,046,313,984、运行后559,460,749,312 bytes，前后差3,585,564,672 bytes（含文件系统及同期活动，不冒充精确产物大小）。预算8 GiB、保留150 GiB均满足；最终含文档/测试的字节盘点另见本地audit。峰值内存与网络协议开销为 `not_measured`。

复核命令（使用既有专用环境）：

```sh
.venv/bin/python -m unittest tests.test_criteo_source tests.test_ingest -v
.venv/bin/python -m ingest.ingest_criteo_source --execute
```

第二条在本地 registry 存在时只核对既有 raw 并复用；没有完整登记时才获取固定官方文件，后续再次下载仍须符合当轮授权。源码、测试与脱敏profile可提交，完整页面、收据、失败日志和raw只留`.local/t04/criteo_v2_1/`。不改依赖锁。T0.4工程通过不自动勾选G0/G1；本人解释仍待本人完成。下一项仅建议T3.1稳定身份与60/20/20封存划分，本轮未执行。


收尾盘点（完成文档前的保守口径）：Criteo目录3,559,664,187 bytes，加整份10个安全交付文件共3,559,832,292 bytes，仍低于8 GiB；磁盘空闲559,414,861,824 bytes，高于150 GiB。文档后续补录与本地audit仅增加少量元数据。收尾42项单元/接入测试与78项登记、profile、历史保护检查均通过；REES46既有manifest字段/样本内容记录保持相等，未重读或重写REES46 raw。
