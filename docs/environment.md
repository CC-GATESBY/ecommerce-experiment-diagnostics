# 本地主环境检查

任务：T0.2。run_id：`bootstrap-20260916T085801Z`。实际命令、返回码和耗时见 [环境快照](../runs/environment_snapshot.txt)。快照采集于 2026-09-16 09:00:00 UTC，即墨尔本 19:00:00。

主环境选定为本地 Mac，后续计算计划为 Spark local，存储计划为本机独立目录。当前仅完成只读检查，计算环境尚未就绪。

## 实测资源

| 项目 | 实际结果 | 检查方式 |
|---|---|---|
| 操作系统 | macOS 15.7.3，build 24G419 | `sw_vers` |
| CPU / 架构 | Apple M2 Pro，arm64，Mac14,10；12 物理核 / 12 逻辑核 | `uname -m`、`sysctl` |
| 物理内存 | 17,179,869,184 bytes = 16 GiB | `sysctl -n hw.memsize` |
| 项目所在卷可用磁盘 | 570,911,920 KiB，约 544.46 GiB；随其他进程变化 | `df -k .` |
| `python3` | 3.12.3；Homebrew Python 3.12 | 版本命令与 `sys.executable` |
| `python` | 3.12.2；Anaconda | 版本命令与 `sys.executable` |
| `python3.11` | PATH 未找到；已检查的 Homebrew 固定位置也未找到 | PATH 与目录检查 |
| 默认 Java | Oracle JDK 23.0.2 arm64 | `java -version` |
| 已注册 JDK | Oracle 23.0.2、Amazon Corretto 11.0.29；未列出 JDK 17 | `/usr/libexec/java_home -V` |
| Spark / PySpark | PATH 未找到 `spark-submit` / `pyspark`；两个已检查的 Python 均无 PySpark 包 | 命令查找与包元数据检查 |
| Hadoop | PATH 与已检查的 Homebrew 固定位置未找到 | 命令与目录检查；未启动服务 |
| Git / GitHub CLI | Git 2.50.1 (Apple Git-155)；gh 2.96.0 | 版本命令 |

以上“未找到”仅覆盖所列 PATH、解释器与固定安装位置，不是对全机所有虚拟环境的穷尽搜索。没有为了检查而安装包或启动 Spark / Hadoop。

## 与 v4 建议版本的差异

| 组件 | v4 建议起点 | 本轮观察 | 后续处理 |
|---|---|---|---|
| Python | 3.11 | 默认命令分别为 3.12.3 / 3.12.2 | T0.3 再确认专用环境；本轮不改变默认解释器 |
| JDK | 17 | 默认 23.0.2，另有 11.0.29 | T0.3 再确认项目 JDK 与绑定方式 |
| Spark / PySpark | 3.5.8 且版本一致 | 运行版本 unavailable | 后续安装授权与兼容性核验后，从真实安装记录精确版本 |

本轮没有验证上述实际 Python / Java 组合能否运行目标 Spark，也没有锁定依赖。`requirements.lock.txt`、`config/local.yaml`、Spark smoke 和配置测试均 `not_run` / 未生成。不能根据本页宣称 T0.3 或 G0 已通过。

## 主环境与资源预算

- 当前范围是本地小批量；全量处理以后由用户决定。
- `local[4]`、Driver `4g`、32 个 shuffle 分区、512 MiB 受控收集预算、150 GiB 磁盘保护线均来自 v4 规划，尚未应用或实测。
- JVM 堆之外还有 Python、操作系统和其他进程开销；16 GiB 物理内存不等于 Spark 可全部占用的内存。实际峰值、任务耗时、数据磁盘放大率均 `not_run`。
- “计算方式”说明任务在哪里运行；“存储后端”说明数据在哪里保存。读到 HDFS 不代表作业运行在 YARN；后续配置须分别声明。
- 原始数据、仓库输出、临时目录和模拟区尚未配置。当前不创建这些数据目录，也不执行格式化或数据清理。

## 云资源

MRC 状态为 `unverified`：没有提供有效项目、配额、登录后资源或用途授权证据；本轮未登录核查、未创建实例、未上传数据。它不阻塞本地路径。Spartan 未核验，未作为并行主环境维护。

## 后续唯一优先任务建议

在本轮仓库工作收尾后，下一轮由用户明确启动 T0.3 剩余部分：确认专用 Python / JDK / Spark 组合及安装范围，再执行小型 Parquet 写入、读回、聚合和配置缺失检查。本轮不实施这项建议，也不推进 T0.4 下载。

本人理解核查仍待进行：区分本机与云配额、计算与存储，以及 JVM 堆与总进程内存。文档不代替用户的解释验收。
