# 本地数据清单

机器可读记录见 [manifest.json](manifest.json)，来源及条款见 [data_sources.md](../docs/data_sources.md)，首次获取历史见 [T0.4 REES46 验收](../docs/t04_rees46_validation.md)，本轮完整覆盖与固定用户候选见 [整月输入验收](../docs/t04_rees46_month_validation.md)。Git 只允许本目录的这两份清单，不收录原始文件或真实样本；没有解除整个 `data/` 的忽略规则。

## 字段与状态

- `files`：压缩包和解压 CSV 各一条，以完整文件 SHA256 识别内容，保留文件名、字节数、获取时间、来源、版本边界、格式和解析状态。
- `parent_archive_sha256` / `extracted_csv_sha256`：连接 gzip 与 CSV。SHA256 不是原发布方的真实性签名。
- `observed_filenames`：相同内容曾出现的名称。同内容改名只增加名称记录，不新增内容；同名异内容报错，需复核。
- `full_record_count`、`full_time_range`：只有完整逐记录扫描才能填实测值。首次获取时为 `not_measured`；本轮 CSV 完整扫描后补充为 42,448,764 条及完整 10 月可解析时间范围，前一状态保存在候选记录内。gzip 不另作 CSV 记录计数。
- `engineering_samples`：每次样本的父哈希、规则、脚本 SHA256、`scope_id`、实际数据记录数、字段、样本哈希、样本时间范围与解析失败数。
- `user_sample_candidates`：按冻结 5% 用户哈希规则得到的整月输入候选，记录源覆盖、样本用户与事件数、规则、脚本版本、资源、核验结果和限制。31 天覆盖表及源每小时计数以提交的 reports CSV 引用；全量源不同用户数保持 `not_measured`。
- `local_relative_path`：仅保存相对项目根目录的本地定位信息；真实路径由被忽略的接入配置确定。文件不在 GitHub。

gzip 在完整解压并通过 CRC 后才可登记；CSV 首次获取的 `header_parsed_only` 仅核对表头和头部样本。本轮补充了完整 CSV 结构与覆盖扫描，仍不代表金额、会话和业务质量门禁通过。失败/未完成下载或扫描保留为 staging 中的部分文件和失败收据，不登记为有效完整输入或候选。

## 安全复跑

从实际项目根目录运行，保留目录名末尾空格。复用已通过验收的 `.venv`，不需要额外依赖。首次在新机器准备时，复制 `config/ingest.example.json` 为被忽略的 `config/ingest.local.json`，填写三个已存在、互不包含的 `.local/` 子目录；模板的 `null` 路径不能直接运行。服务器对象或预算发生变化时先重新核对，不修改已登记 raw。

```sh
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" ingest/ingest.py check --config config/ingest.local.json
".venv/bin/python" ingest/ingest.py acquire --config config/ingest.local.json
".venv/bin/python" ingest/ingest.py sample --config config/ingest.local.json --run-id rees46-oct-head-03
```

`acquire` 先核验已有登记文件的完整哈希；存在且一致时不再下载。样本必须使用新的 run ID；已存在的目录会报错，不覆盖上一轮文件。上面最后一条是未来获授权时的复跑示例，不会自动执行。

实际本机配置为 `config/ingest.local.json`；本地注册表为 `.local/t04/registry.json`；staging、raw、样本分别位于 `.local/t04/staging/`、`.local/t04/raw/`、`.local/t04/samples/`。人工测试在 `.local/t04/synthetic-tests/` 中使用 `synthetic` 标注并与真实数据隔离；原始日志在 `runs/t04-rees46-20260916/`。这些位置均被 Git 忽略。

## 使用限制

原 `engineering_sample` 为源文件开头最多 100,000 条 CSV 数据记录，表头不计数；不是随机样本。源顺序、原始字符串值、空字段和重复候选均保留。格式重新序列化不改变 CSV 字段值，没有过滤、去重、补零、浮点转换或时间清洗。

`engineering_sample` 只能证明接入与工程读写行为，不可支持总体转化率、留存、长周期异动、CUPED 或业务因果结论。新 `user_sample_candidate` 按用户选择并保留本源文件内全部记录，但没有通过正式分析验收；两类样本不合并。

整月候选与收据位于 `.local/t04/user-samples/rees46-oct-user5-20260916/`，配置为被忽略的 `config/user_sampling.local.json`。规则、失败处理和模块启动方法见 [analysis_sampling.md](../docs/analysis_sampling.md)。用户级 SQLite 校验索引、样本与日志均留本机；公开覆盖表只含日期、小时和计数。

历史（REES46候选准备阶段）：Criteo 来源验收暂后移未取消，整个 T0.4 和 G0 不得提前勾选。下一步先用旧头部工程样本验证 T1.1，通过后再获授权处理整月用户候选，尚不执行 T1.5 正式扩量。


## 独立 Criteo corrected v2.1 登记

新增 `additional_sources.criteo_uplift_v2_1_corrected`，不并入旧REES46的 `files`、`source_id` 或样本数组。顶层旧run/来源/measurements仍描述REES46历史获取；新增对象单独记录Criteo的run、版本、源URL、官方commit、许可证据、gzip/CSV关系及全文件实测profile。

两份raw为同一官方内容的压缩/解压对象，分别登记精确bytes/SHA，`parent_archive_sha256` 与 `extracted_csv_sha256` 双向关联。CSV的13,979,592条不含header；16列是实际核验值。没有时间字段，时间覆盖为 `not_applicable_no_timestamp_field`。HF SHA是官方对象一致性线索，本机 SHA 均独立重算，不是发布方签名证明。

raw 位于 `.local/t04/criteo_v2_1/raw/<sha256>/`，文件0444、hash目录0555；本机完成收据另存registry与运行staging。仅全量CRC/结构/domain/独立核验通过才发布；失败保留`.part`和失败记录。相同内容换名不重复登记、同名不同内容拒绝；已登记源再执行只核对并复用，不重复下载或累计。

`task_status`及Criteo子项现为`done_engineering_user_explanation_pending`，REES46原文件与样本记录未改；本人解释未代验，G0/G1不自动完成。Git只保留脱敏元数据和[完整验收说明](../docs/criteo_source_validation.md)，raw、真实样本、原日志、官方页面快照与本机收据仍被忽略。没有train/valid/test字段，T3.1未执行。
