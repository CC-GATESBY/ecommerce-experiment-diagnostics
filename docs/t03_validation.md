# T0.3 专用环境与最小 Spark 验收

日期：2026-09-16。task_id：`T0.3`。状态：`done`（工程验收；本人独立解释未代验）。run_id：`t03-20260916T100642Z`。

## 范围与起点

起点为 `391ce22201e9e30d3ccefdfbca643b8960962bfa`，本地与远程 main 一致、工作区干净，仓库为 private。本轮只完成 T0.3 剩余部分；S0、T0.1、T0.2 不重复执行。真实项目目录末尾空格保留，没有 trim、重命名或另建项目。

`docs/environment.md` 保留 T0.2 的原始检测含义和内容。新版本仅用于项目 `.venv` 与本次启动进程，不代表全局默认环境变化。Git 作者显示名与 GitHub 活动登录名存在差异，仅记录；作者配置和历史未改变。

输入为脚本中明示的四行人工数据，加上两个 Python worker 探针元素，合计远低于 100 行。没有 REES46 / Criteo 数据，也没有 Hadoop、Hive、Docker 或云资源操作。PySpark 包含运行所需的客户端库，不代表安装或启动 Hadoop 集群。

## 实际安装与版本锁

| 组件 | 目标 | 实际 | pass |
|---|---|---|---|
| Python Driver / worker | 同一项目 Python 3.11 | 3.11.15；两项 worker 探针的解释器路径、prefix、完整版本均与 Driver 一致 | true |
| Java | JDK 17 | OpenJDK 17.0.19；Spark JVM 内实际读取该版本 | true |
| PySpark / Spark JVM | 两者均为 3.5.8 | 3.5.8 / 3.5.8 | true |
| py4j | 满足 PySpark 依赖 | 0.10.9.9 | true |
| PyYAML | 仅用于配置读取 | 6.0.3 | true |
| 依赖一致性 | 无破损依赖 | `pip check`：No broken requirements found. | true |
| 锁文件 | 从实际专用环境导出 | `pip freeze --all` 导出后与当前环境逐字节核对一致 | true |

`requirements.lock.txt` 包含实际环境的五项：pip 26.1.2、setuptools 82.0.1、py4j 0.10.9.9、pyspark 3.5.8、PyYAML 6.0.3。前两项来自创建虚拟环境时的工具链。未安装后续建模库，配置测试使用标准库 unittest。

执行的安装方式：关闭 Homebrew 自动更新、自动清理、关联软件升级及已安装目标的自动升级，安装 `python@3.11 openjdk@17` 及必要依赖；然后以项目 `.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple` 安装 `pyspark==3.5.8` 和 `PyYAML>=6,<7`。没有单独安装 Homebrew apache-spark。

Homebrew 实际新增两项目标软件、两项依赖，并更新 23 项必要依赖；与预览相比 openssl@3 无需更新。旧版本目录全部保留，50 项其他 Homebrew formula 的版本集合未变。必要依赖的链接可能指向新增版本，不宣称所有已有依赖完全未改变。

| Formula | 动作 | 本次新增的版本 |
|---|---|---|
| `ca-certificates` | 必要依赖更新，旧版本保留 | 2026-05-14 |
| `cairo` | 必要依赖更新，旧版本保留 | 1.18.4 |
| `fontconfig` | 必要依赖更新，旧版本保留 | 2.18.2 |
| `freetype` | 必要依赖更新，旧版本保留 | 2.14.3 |
| `gettext` | 必要依赖更新，旧版本保留 | 1.0 |
| `giflib` | 必要依赖更新，旧版本保留 | 6.1.3 |
| `glib` | 必要依赖更新，旧版本保留 | 2.88.2 |
| `graphite2` | 必要依赖更新，旧版本保留 | 1.3.15 |
| `harfbuzz` | 必要依赖更新，旧版本保留 | 14.2.1 |
| `jpeg-turbo` | 必要依赖更新，旧版本保留 | 3.2.0 |
| `json-c` | 新增 | 0.19 |
| `libpng` | 必要依赖更新，旧版本保留 | 1.6.58 |
| `libtiff` | 必要依赖更新，旧版本保留 | 4.7.2 |
| `libunistring` | 新增 | 1.4.2 |
| `libx11` | 必要依赖更新，旧版本保留 | 1.8.13 |
| `libxau` | 必要依赖更新，旧版本保留 | 1.0.12 |
| `libxext` | 必要依赖更新，旧版本保留 | 1.3.7 |
| `libxrender` | 必要依赖更新，旧版本保留 | 0.9.12 |
| `little-cms2` | 必要依赖更新，旧版本保留 | 2.19 |
| `mpdecimal` | 必要依赖更新，旧版本保留 | 4.0.1 |
| `openjdk@17` | 新增 | 17.0.19 |
| `pcre2` | 必要依赖更新，旧版本保留 | 10.47_1 |
| `pixman` | 必要依赖更新，旧版本保留 | 0.46.4 |
| `python@3.11` | 新增 | 3.11.15_3 |
| `sqlite` | 必要依赖更新，旧版本保留 | 3.53.3 |
| `webp` | 必要依赖更新，旧版本保留 | 1.6.0 |
| `xorgproto` | 必要依赖更新，旧版本保留 | 2025.1 |

默认 `python3` 仍为 3.12.3，Anaconda `python` 仍为 3.12.2，默认 Java 仍为 23.0.2；原注册 JDK 11 未被删除。`.zshrc`、`.zprofile` 的哈希与安装前一致。未使用 sudo、强制链接或全量 brew upgrade，也未执行安装提示中的系统 JDK 链接。

## 配置与隔离

- 模板 `config/local.example.yaml` 保留 null 路径，不能直接执行。实际 `config/local.yaml` 被 Git 忽略。
- `runtime.python_executable` 指向项目 `.venv/bin/python`；`runtime.java_home` 指向本机 JDK 17。启动器核对解释器所属环境、PySpark 安装位置及版本，使用该 `.venv/bin/spark-submit`。
- `compute.mode=local`、`storage.backend=local`；`master=local[4]`、Driver `4g`、shuffle 32、时区 UTC。内存在 JVM 启动参数中设置，未调用 `enableHiveSupport()`。
- 临时目录使用 `storage.temp_root`，人工 Parquet 输出使用 `storage.warehouse_root`。二者必须为现有、可写、不重叠的 `.local/` 子目录；外部路径或 symlink 逃逸会报错。T0.4 原始区与后续模拟区尚未实现，未据此增加业务模块。
- 空配置、未知/缺失字段、重复 YAML 键、错误类型、未填写或不存在的路径均报错；不回退到默认目录，不 trim 实际路径。
- 启动器使用独立空 Spark properties 文件，设置进程级 JAVA_HOME、Python 与 Spark 路径，并清除可能造成环境混用的继承覆盖项。Driver 绑定本机回环地址，UI 关闭。

## expected / actual / pass

两次独立运行分别为 `t03-smoke-01`、`t03-smoke-02`，每次 23 项实际断言均通过。

| 检查 | expected | 两次 actual | pass |
|---|---|---|---|
| master | local[4] | local[4] | true |
| Driver 配置 / 实际 JVM 最大堆 | 4g / 4,294,967,296 bytes | 4g / 4,294,967,296 bytes | true |
| shuffle / session timezone | 32 / UTC | 32 / UTC | true |
| catalog | in-memory，无 Hive | in-memory | true |
| 临时路径 / Python worker 配置 | 启动前取自本机配置 | 与各自配置及 run ID 一致 | true |
| 输入 / Parquet 读回行数 | 4 / 4 | 4 / 4 | true |
| schema（含 nullable） | id int、category string、amount decimal(10,2)、event_time timestamp；均 nullable | 输入、Parquet 读回均一致 | true |
| 四行读回内容 | 按 id 排序后逐行相同 | 相同 | true |
| SQL 分组聚合 | A：2 行、0.30；B：2 行、3.40 | 与独立字面预期完全一致 | true |
| Decimal 总和 | 3.70，精确值 | 3.70 | true |
| UTC 处理 | 四个时刻依次为 2026-09-16 00:00、00:30、00:00、01:00 UTC | 完全一致；包含 +10:00、Z、-01:00 输入 | true |
| Python worker | 两个探针均与 Driver 同解释器、prefix、版本、PySpark | 全部一致 | true |
| 正常停止 | 两次 spark.stop() 均成功 | 两份收据 spark_stopped=true | true |
| 重跑隔离 | 两个独立输出，第一次所有文件哈希不变，保留文件不变 | 全部满足 | true |
| 已有 run ID | 报错且不覆盖 | 退出码 2，原文件哈希不变 | true |
| 配置边界 | 17 项 unittest 通过 | 17/17；覆盖各必填字段等 subtests | true |
| 实际依赖锁 / pip check | 锁与当前环境一致、无依赖冲突 | 一致、无冲突 | true |

人工输入金额为 0.10、0.20、2.35、1.05。分组与 Decimal 预期独立写成常量，未用被测 SQL 的结果生成预期值。collect 仅用于至多四行人工结果及两个探针，不为后续事实表放开集中收集限制。

本地测量的 smoke 内部运行耗时为 t03-smoke-01：5.744355 秒、t03-smoke-02：8.143418 秒；范围包括 SparkSession 创建、断言与停止，不包括包安装和启动器进程开销。该数字仅是运行记录，不是性能基准或扩量能力证据。

初始配置测试发现 macOS 临时目录逻辑路径与物理路径别名的规范化差异，已修复父目录解析，保留真实末尾空格；修复后 17 项配置测试及两次 smoke 均通过。初始失败记录原样保留在本地，不隐瞒为首次全过。

## 复跑方法

以下命令从实际 `<PROJECT_ROOT>` 执行。已有 `.venv` 无需重建；新环境需先确认 Python 3.11 / JDK 17 已安装且获得安装授权：

```sh
"$(brew --prefix python@3.11)/bin/python3.11" -m venv ".venv"
".venv/bin/python" -m pip --isolated install --index-url https://pypi.org/simple -r "requirements.lock.txt"
```

实际配置应逐项填写：Python 为 `<PROJECT_ROOT>/.venv/bin/python`，Java home 为 `$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home` 的实际结果，temp_root 和 warehouse_root 分别为 `<PROJECT_ROOT>/.local/t03/temp`、`<PROJECT_ROOT>/.local/t03/warehouse`。先创建两个目录，再在仅本地的 `config/local.yaml` 填入完整路径；不要把占位符原样保存。已有配置不得直接覆盖。

```sh
".venv/bin/python" -m pip --isolated --no-cache-dir check
".venv/bin/python" -m unittest discover -s tests -v
".venv/bin/python" "scripts/run_smoke.py" --config "config/local.yaml"
```

不提供 run ID 时自动生成唯一值。输入种子不适用：人工输入完全固定。再次运行使用同一输入，各次 Parquet、日志和收据分别保存到配置输出根下；已有 run ID 会拒绝。锁文件固定 Python 包实际版本，操作系统与 Homebrew formula 版本另由本报告记录，不声称它能完整锁住系统环境。

## 本地证据与发布边界

原始记录位于 `runs/t03-20260916T100642Z/`；两次运行位于 `.local/t03/warehouse/t03-smoke-01/` 和 `t03-smoke-02/`。每次包括 launch.json、spark.log、validation.json 与 Parquet；配置、输入/输出范围、版本、每项断言、耗时和配置 SHA 均有记录。这些路径下的内容、虚拟环境与实际 local.yaml 均不提交。脱敏摘要及实际锁文件提交到现有 private 仓库。

本人独立解释项保持未勾选。T0.4 未运行，G0 尚未通过。当前没有未解决的 T0.3 工程失败；本验收不证明业务口径、真实数据质量或全量性能。下一轮任务由用户指定，不自动下载数据。

需要本人理解的三点：项目专用解释器如何与 Driver / worker 对齐；为什么 4g JVM 堆不等于总进程内存；四行 smoke 能验证基本运行链路但不能证明业务 ETL 或全量性能。

方法依据：[Spark 3.5.8 支持环境](https://spark.apache.org/docs/3.5.8/)、[spark-submit 与启动参数](https://spark.apache.org/docs/3.5.8/submitting-applications.html)。运行结果以本轮实际收据为依据。
