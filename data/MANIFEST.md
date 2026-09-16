# 本地数据清单

机器可读记录见 [manifest.json](manifest.json)，来源及条款见 [data_sources.md](../docs/data_sources.md)，本轮 expected/actual/pass 见 [T0.4 REES46 验收](../docs/t04_rees46_validation.md)。Git 只允许本目录的这两份清单，不收录原始文件或真实样本；没有解除整个 `data/` 的忽略规则。

## 字段与状态

- `files`：压缩包和解压 CSV 各一条，以完整文件 SHA256 识别内容，保留文件名、字节数、获取时间、来源、版本边界、格式和解析状态。
- `parent_archive_sha256` / `extracted_csv_sha256`：连接 gzip 与 CSV。SHA256 不是原发布方的真实性签名。
- `observed_filenames`：相同内容曾出现的名称。同内容改名只增加名称记录，不新增内容；同名异内容报错，需复核。
- `full_record_count`、`full_time_range`：只有完整逐记录扫描才能填实测值。本轮均为 `not_measured`，不复制网页规模。
- `engineering_samples`：每次样本的父哈希、规则、脚本 SHA256、`scope_id`、实际数据记录数、字段、样本哈希、样本时间范围与解析失败数。
- `local_relative_path`：仅保存相对项目根目录的本地定位信息；真实路径由被忽略的接入配置确定。文件不在 GitHub。

gzip 在完整解压并通过 CRC 后才可登记；CSV 本轮只核对表头与样本前缀的可解析性。`header_parsed_only` 不代表整月全部记录已经正确解析。失败/未完成下载保留为 staging 中的 `.part` 和失败收据，不进入 `files`。

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

样本为源文件开头最多 100,000 条 CSV 数据记录，表头不计数；不是随机样本。源顺序、原始字符串值、空字段和重复候选均保留。格式重新序列化不改变 CSV 字段值，没有过滤、去重、补零、浮点转换或时间清洗。

`engineering_sample` 只能证明接入与工程读写行为，不可支持总体转化率、留存、长周期异动、CUPED 或业务因果结论。Criteo 来源验收仍未完成，整个 T0.4 和 G0 不得因此勾选。
