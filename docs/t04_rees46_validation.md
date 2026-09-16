# T0.4 REES46 10 月文件验收

验证日期：2026-09-16。状态：**REES46 当前文件子任务 done；整个 T0.4 为 in_progress**。Criteo 来源验收为 `not_started`；G0 未勾选，T1.1 未开始。用户本人独立解释项未代验。

起点为 `085b89201151accdc984532b303cc4d62e4acfcc`，本地及远程 main 一致，工作区干净，仓库仍为 private。实际目录名末尾空格保留。没有重复执行 S0、T0.1、T0.2、T0.3，没有安装工具、变更依赖锁、重装环境或修改 Git 作者配置。

## 输入、输出和来源边界

run_id：`rees46-oct-20260916T104053Z-4e081494`。原发布入口、许可说明与 HTTP/API 证据类型见 [来源核对](data_sources.md)。Kaggle 目录版本为 8；本次实际文件来自其发布说明直接链接的 REES46 原域名压缩对象。该外链没有独立版本号，未与 Kaggle 文件逐字节比较，不能把外链对象宣称为已验证的 Kaggle v8 同一内容。

| 对象 | 实测字节数 | 记录数 / 范围 | SHA256 |
|---|---:|---|---|
| `2019-Oct.csv.gz` | 1,741,928,540 | gzip 全部字节已下载并通过 CRC | `8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147` |
| `2019-Oct.csv` | 5,668,612,855 | 完整行数、完整时间范围均为 `not_measured` | `fedd938409b5f836ec89b39c861b13dad99fc7cd9beb1fddd97a2d50488b5b80` |
| 工程样本 01 | 13,352,959 | 100,000 条数据记录；9 字段 | `fe2cd808172c853217201660a98a8c8600fb0230f5c89efda45a9a1a2fdae754` |
| 工程样本 02 | 13,352,959 | 与样本 01 内容一致，目录独立 | `fe2cd808172c853217201660a98a8c8600fb0230f5c89efda45a9a1a2fdae754` |

源表头：`event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session`。压缩包取得时间为 `2026-09-16T10:46:27.198947+00:00`，CSV 解压完成时间为 `2026-09-16T10:46:38.773774+00:00`。压缩包与解压文件的完整哈希均已再次独立核对，原始文件设为只读；SHA256 是内容追踪值，不是发布方认证。

样本范围为 **2019-10-01 00:00:00 至 04:28:27 UTC**，可解析 100,000 条，时间解析失败 0 条。这只是样本范围。规则是 CSV 解析器按源顺序取前至多 100,000 条数据记录，排除表头；所有字段保持字符串，保留空字段和重复候选，不做任何业务过滤、去重、补零、数值转换或时间清洗。CSV 固定为 UTF-8、LF、QUOTE_MINIMAL 序列化；字段值相同不要求引号包装字节与源 CSV 相同。

scope_id：`rees46_oct_head_d50b23d8c05613dfd1eb`；规则：`head_csv_records_v1;utf8;csv_strict;strings;header_once;LF;QUOTE_MINIMAL;max_records=100000`；脚本 SHA256：`1e257db68b05b63e5e6cb7ef04b8a66ca823112244728250be9fa6fe0dc0441e`。规则、父哈希、字段、实际规模、样本哈希和样本时间范围均登记在 [manifest.json](../data/manifest.json)。随机种子为不适用：这是顺序头部工程样本，不是随机样本。

## 下载和磁盘成本

单次源文件载荷下载 **1,741,928,540 bytes（1.622 GiB）**，完整传输耗时 332.596 秒；这不是 100,000 行的网络下载量。未下载 Kaggle 整包、11 月、其他月份或 Criteo。元数据请求及 HTTP/TLS 协议开销未做网卡层计量，不能把文件载荷字节数当作所有网络流量。

下载前空闲 581,133,991,936 bytes（541.22 GiB）。压缩文件、解压文件及两份上限 64 MiB 的样本共预留 7,544,759,123 bytes（7.03 GiB），小额元数据、收据和文件系统开销另计。实际 raw 加两份样本的内容总量为 7,437,247,313 bytes（6.93 GiB）；验证后文件系统空闲 573,679,390,720 bytes（534.28 GiB）。磁盘空闲变化会受系统其他进程影响，不冒充本项目的精确物理占用。

## expected / actual / pass

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 指定来源 | 原发布入口 → 指定 Kaggle 标识 → 原域名同月对象 | REES46 → mkechinov 指定数据集 → 2019-Oct.csv.gz | pass |
| 下载预算 | 唯一月文件，≤8 GiB | 1 个源文件，1.622 GiB；一次成功传输 | pass |
| 新增数据预算 | ≤25 GiB | 预留 7.03 GiB；raw 加两份样本内容 6.93 GiB | pass |
| 磁盘余量 | 下载、解压后 ≥150 GiB | 验证后 534.28 GiB | pass |
| 文件长度、解压 | 与已核对元数据一致；gzip CRC 成功 | gzip 1,741,928,540 / CSV 5,668,612,855 bytes；CRC pass | pass |
| 原始区 | 压缩/解压分别登记；不覆盖 | 两条输入，哈希关系完整；0444；重新 acquire 无下载 | pass |
| 样本行数、表头 | ≤100,000，表头不计入 | 两次各 100,000 条，9 个字段 | pass |
| 字段与顺序保留 | 与源前缀逐字段相同 | 两次均与独立读取的源前 100,000 条完全一致 | pass |
| 样本可复现 | 同输入同规则，内容 SHA256 一致 | 两份样本及 scope_id 一致，独立目录，无覆盖 | pass |
| 样本时间登记 | 只报样本范围与失败数 | 00:00:00–04:28:27 UTC；失败 0 | pass |
| 内容登记边界 | 重复、改名同内容去重；同名异内容拒绝 | 3 项 synthetic 测试通过 | pass |
| CSV 边界 | 引号、逗号、跨行字段、空字段、短输入、重复候选保留 | synthetic 字段值逐项比较通过；异常列宽拒绝 | pass |
| 未完成下载 | 不得登记为完整输入 | 短下载、网络失败、超长下载、篡改内容均拒绝 | pass |
| 解压保护 | 越界、损坏、超长、已存在目标拒绝 | synthetic 测试通过 | pass |
| 配置失败 | 缺失/非法/未填写直接失败 | 配置单测通过；缺失及模板命令均 exit 1 | pass |
| 原配置回归 | 原有 17 项测试继续通过 | 17/17；接入 synthetic 20/20；总 37/37 | pass |
| 真实产物独立核验 | 字节、哈希、字段、顺序、范围及只读属性一致 | 34/34 检查通过 | pass |
| Git 排除与旧文件 | 本地数据不提交；旧环境与规划保留 | 9 类排除路径通过；14 个受保护的已跟踪文件哈希未变 | pass |
| 全文件行数/时间覆盖 | 未完整解析不填实测 | `not_measured` | pass（范围约束） |
| Criteo / G0 / T1.1 | 不提前完成或越级 | not_started / 未勾选 / not_started | 未执行 |

20 项接入测试均使用独立 `synthetic` 小文件；真实文件只做下载、解压、字节校验、表头检查及头部工程样本。没有运行 Spark、整月 ETL、事实 Parquet、指标、漏斗或实验模块。这不是性能基准或业务成果。

## 复跑与证据位置

从实际项目根目录执行，保留末尾空格；本轮专用环境沿用 T0.3。接入配置独立于 Spark 配置，不引入 raw_root 到旧校验模块。

```sh
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" ingest/ingest.py check --config config/ingest.local.json
".venv/bin/python" ingest/ingest.py acquire --config config/ingest.local.json
".venv/bin/python" ingest/ingest.py sample --config config/ingest.local.json --run-id rees46-oct-head-03
```

本轮实际使用的样本 run ID 为 `rees46-oct-head-01` 和 `rees46-oct-head-02`，最后一条只是后续复跑示例。新样本要使用未存在的 run ID；已有产物不会覆盖。已登记且校验一致的 raw 会直接复用。脚本输出返回码 0 表示该步骤通过；配置或输入失败返回非零。

提交文件：`config/ingest.example.json`、`ingest/__init__.py`、`ingest/ingest.py`、`tests/test_ingest.py`、`docs/data_sources.md`、`data/MANIFEST.md`、`data/manifest.json`、本验收文档，以及 README、TASKS 和本地范围文档的必要状态说明。

本地保留且不提交：`config/ingest.local.json`；`.local/t04/` 中的 staging、raw、两份真实样本和收据；`runs/t04-rees46-20260916/` 中的源元数据、原始日志、独立核验与收尾收据。14 个保护文件包括原环境快照文档、依赖锁、T0.3 脚本、配置测试和 v4 规划；本机 Spark 配置哈希也未变。没有改动全局环境、作者身份或旧历史。

未完成项：Criteo 修正版标签、字段和来源条款验收；REES46 全文件行数与全时间范围未测，未来有实际需要及授权时另做。当前工程样本不能支持总体转化、留存、长周期异动或 CUPED。

需要本人理解的三个要点：1）目录版本、HTTP 对象指纹与本地 SHA256 各能证明什么；2）100,000 条头部样本仍可能需要下载、解压完整源文件；3）重复运行保证内容可复现，不会让头部样本具有总体代表性。

下一轮唯一优先任务：**T0.4 的 Criteo 来源验收子任务**，范围与下载预算由用户另行指定。本轮到审核提交与 private/main 同步为止，不进入 T1.1。最终 Git SHA 在本地收尾收据及交付回复中核对，避免将尚未产生的提交写为已同步。
