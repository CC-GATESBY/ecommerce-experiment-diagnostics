# T1.5 十月首版范围冻结

2026-09-17：**done（10月首版范围冻结；本人解释未代验）**。analysis_scope版本 `rees46_oct_user5_analysis_v1`，本轮收据run `freeze-oct-v1`。实际项目目录末尾一个空格保留；起点 `539c6cb7fd0fec2176a78b52db7c9a52864737c5`，原工作区干净。没有重新执行整套ETL或扩大输入。

## 唯一输入与快照

[analysis_scope.yaml](../config/analysis_scope.yaml)是首版用途的范围声明；机器路径由本机配置解析。原manifest及候选身份不回写，不建立另一套登记平台。

| 项目 | 冻结值 |
|---|---|
| source_id | rees46_multicategory_2019_oct |
| 数据scope_id | rees46_2019_oct_user5_fedd938409b5f836_20260916_v1 |
| series_id | rees46_fixed_users_20260916_v1 |
| candidate_sha256 | 5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b |
| 原kind | user_sample_candidate，保持不变 |
| fact / metric / crosscheck run | month-v101-01 / metrics-month-01 / crosscheck-month-01 |
| 解析 / 指标 / 日期规则 | rees46-events-v1.0.1 / rees46-metrics-v1 / rees46-date-quality-v1 |
| 品牌映射 | rees46-brand-oct01-07-top200-v1 |
| 重复处理 | baseline_keep_all |
| 声明观察范围 | [2019-10-01T00:00:00Z, 2019-11-01T00:00:00Z) |
| 候选实际首末事件 | 2019-10-01T00:00:23Z / 2019-10-31T23:59:56Z，引用原采样收据 |

实际首末事件与声明观察边界分别保存；最后一条事件不是上游完整性的证明。全月候选为151,121用户、2,114,081事件、282,405,091 bytes，这些来自已有成功收据，不是本轮重扫结果。抽样采用原 `rees46-user-sample-v1`、种子20260916、SHA256前64位阈值规则；目标用户概率5%，实际事件比例4.98031226539364%，两者不混称。全源不同用户数未测；样本金额不能直接乘20当成已核验平台金额。

范围绑定层要求canonical run；month-v101-02仅保留历史复验，其他metric/crosscheck run与多个快照均拒绝。复用既有 `select_snapshot`，旧登记语义和旧本机复验配置未改。

## 按用途冻结时间边界

| 用途 | 首版允许范围 | 尚未完成或限制 |
|---|---|---|
| 日指标、描述性分析 | 10月1–31日UTC，31天count/amount均经既有门禁和独立结果核对 | 固定用户候选内的日志指标；不是平台总体或财务收入；缺品牌/品类仍按原规则保留unknown |
| 24小时顺序漏斗准备 | 起始view完整日为[10月1日00:00,10月31日00:00)，即1–30日 | 31日仍作结果观察数据且保留总体指标；未生成漏斗SQL或路径数量。右边界不完整与未转化须分开；同秒、缺view、超长session留给T2.1冻结 |
| 探索性历史准备 | offsets=[7,14,21,28]，min_history_points=3；按count/amount分别评估 | 只检查日期存在和对应用途质量，没有计算MAD、阈值、告警或贡献；3–4点是项目设计，不保证统计可靠性 |
| 离线实验准备 | 前置[10月1日,10月15日)，结果[10月15日,10月29日)，均UTC | 两窗口不重叠且在观察范围内。队列以后仅依赖前置期合格用户确定；151,121不能直接作为实验样本量；未生成队列表 |

原v4双月扩展目标保留。首版明确为“10月固定用户样本”，11月和更多用户都是以后另行授权的可选扩展，不属于本轮完成条件。后续用途需要当前月份无法提供的历史或未来观察时，应限制日期或标不适用，不改阈值制造可用结果。

## 历史可用性实际核对

[history_readiness.csv](../reports/history_readiness.csv)有62行：31天×count/amount两种用途，包含历史日期、数量、min3/full4、状态和原因。历史日期按偏移7/14/21/28天列出，未把观察范围外日期补为0；缺日或金额被阻断的历史点不会被对应列计入。

| 目标日期 | 日历独立预期点数 | 实际count / amount点数 | pass |
|---|---:|---|---|
| 10月1–7日 | 0 | 每日0 / 0 | true |
| 10月8–14日 | 1 | 每日1 / 1 | true |
| 10月15–21日 | 2 | 每日2 / 2 | true |
| 10月22–28日 | 3 | 每日3 / 3 | true |
| 10月29–31日 | 4 | 每日4 / 4 | true |

两种用途分别有 **10天满足至少3点（22–31日）**、**3天满足完整4点（29–31日）**。22–31日只标 `history_available_not_evaluated`，并未放行已校准的异常检测。1–21日为 `insufficient_history`。合格日期的历史计数布尔只表示数量；若当前日期质量被阻断，状态仍为 `current_date_unavailable`，不能因有4个历史点而放行当前日。

## 本轮验证与保护

| 检查 | expected | actual | pass |
|---|---|---|---|
| 新配置/日历测试 | UTC半开窗口、越界/重复日期、错误scope/run、未完成证据、历史缺日/金额阻断、漏斗24h起点、实验重叠均拒绝或按字面计数 | 18项单元通过 | true |
| 复用接口回归 | 原快照选择器多路径/通配符拒绝等单元仍通过 | 4项原单元通过；没有跑人工Spark | true |
| 完成证据 | fact、metric、crosscheck均通过，来源/契约/窗口一致 | 成功状态和原检查全部核对 | true |
| 唯一指标指纹 | 与T1.4核验时的选定快照相同 | 67个Parquet指纹一致，含200行品牌映射所在文件 | true |
| 日期与用途 | 已登记gates、T1.3、T1.4日汇总一致，31天无缺日/重复 | 全部一致 | true |
| 实际小表读取 | 日指标31行，scope/日期/count/amount/记录数一致 | 31行通过；事实和用户日未查询 | true |
| 四表行数证据 | 两份已验收收据一致 | 151121 / 322660 / 31 / 6879 | true |
| 历史数量 | 独立日历预期min3=10、full4=3 | count、amount均10 / 3 | true |
| 既有本地文件 | 原文件不改写 | 1,230个历史文件大小/mtime/inode未变；13个配置/收据/绑定证据内容指纹核对 | true |

数据表层面本轮只实际打开31行日指标Parquet；其他指标文件仅核对指纹/元数据，事实仅核对登记、完成收据、大小与布局。未读原始/候选CSV，未重算候选或完整源SHA链。没有启动Spark、安装依赖、改锁或修改旧manifest/质量规则/覆盖表/事实/指标/核验结果/历史报告。原内容完整性仍继承T1.1–T1.4证据，而非声称本轮重新验证全部数据。

本轮范围校验耗时0.215秒，仅含轻量收据/小表/日历核对，不是ETL或性能基准。校验后本地新增目录约0.30 MiB，文档与代码另不足0.1 MiB，远低于512 MiB；校验收据记录空闲565,605,404,672 bytes（约526.76 GiB），高于150 GiB。峰值内存未测。最终文件审查另保存本地收据，不把卷空闲变化当作项目准确占用。

原分阶段输入输出、计时范围、内存/磁盘测量局限和真实布局见 [scale_baseline.md](../reports/scale_baseline.md)。四表平铺、66个Parquet文件共7,227,509 bytes；不是日期物理分区。本轮没有为了改善布局重新写表。未测连续端到端耗时，不累加各阶段时间，不比较Spark与DuckDB加速比例。

## 运行入口与总门槛

共享配置为 `config/analysis_scope.yaml`。被忽略的 `config/analysis_scope.local.json`只绑定现有metrics/crosscheck配置与选定crosscheck完成收据，真实机器位置不进入共享配置。现有snapshot selector不变。以下在实际项目根执行；run目录必须不存在：

```sh
.venv/bin/python -m unittest discover -s tests -p test_analysis_scope.py -v
.venv/bin/python -m unittest discover -s tests -p test_idempotency.py -v
.venv/bin/python scripts/validate_analysis_scope.py --run-dir .local/t15/freeze-oct-NEW
```

成功后在独立 `complete/etl_baseline.json` 保存本机证据、文件清单和资源记录；失败留staging且不能作为完成收据。默认累计本轮目录上限512 MiB、空闲至少150 GiB。复跑仅做同范围轻量核对，不隐式启动Spark或扩量。

| 原门槛 | 已有证据 | 剩余/本轮处理 |
|---|---|---|
| G0：T0.1–T0.4与Spark smoke | T0.1–T0.3、REES46来源/覆盖通过 | Criteo来源验收仍未完成；全项目G0保持未勾选 |
| G1：T1.1–T1.4样本核验 | REES46分数据线的解析、质量、指标、独立核验、重跑/边界证据齐全 | 明示REES46分数据线满足；不将其他数据线视为已验证，全项目G1保持未勾选 |
| T1.5首版 | 单月用途范围、足够历史的日期、布局和证据整理通过 | done；双月/更多用户未执行且不属首版条件；本人解释仍未代验 |

无未解决工程阻塞；上述月份、历史点、上游完整性和抽样外推限制仍存在。范围批准不等于T2.1漏斗、T4诊断或T5实验已完成。下一项唯一建议：**T2.1 行为覆盖与顺序漏斗**，本轮停止。
