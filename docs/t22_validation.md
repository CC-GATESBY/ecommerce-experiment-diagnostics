# T2.2 行为分析与阶段总结验收

**当前状态：T2.2 done（工程验收，本人解释未代验）。** 2026-09-17 closeout 已按新增明确授权补齐14个品类的整月去重users/buyers，并完成逐桶对账；详见文末“closeout”。T2.3未执行。

首次报告阶段历史：当时只获准小时事实查询，品类月人数暂存not_measured，因此整项in_progress。下述首次阶段结果与收据保持历史含义；本次只补缺口，不重新解释或重算既有金额、漏斗、小时结果。

## 输入和执行边界

实际项目目录保留末尾 U+0020 空格。起点与参考提交均为 `3d8ec29f8312d9ffdb9ed51593ea9d5f3f88939c`，开始时工作区干净，origin 为指定 private/main。没有 reset、改作者或重命名。

唯一 analysis scope 为 `rees46_oct_user5_analysis_v1`；数据 scope 为 `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`。只选 fact `month-v101-01`、metric `metrics-month-01`、funnel `funnel-month-01`，沿用 baseline_keep_all。日期为2019-10-01至31日UTC，路径 formal 起点仍为1–30日；固定用户目标抽样概率5%，不把样本推成总体或金额乘20。

先冻结 [behavior_analysis_contract.md](../reports/behavior_analysis_contract.md)，再测试、读取既有小汇总与生成图表。DuckDB仅读取已有31行日指标和433行 category_l1 日维度，没有重做T1.4核验。漏斗复用已发布四份CSV，对照原完成收据逐项检查；未运行漏斗SQL。

历史T2.1收据的 `lineage.funnel_run` 实际写为 `staging`，是元数据缺陷。本轮记录该实际值，以明确的 `funnel-month-01` 完成目录、成功 launch/validation、输入/scope身份及CSV/收据内容一致确认所选结果；没有改写旧收据、旧报告或宣称该字段本来正确。处理依据保存在本轮本地 prepare 收据。

## 核验结果

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 新增聚合单元、范围绑定和日期读取回归 | 39项通过，先于真实读取 | 39/39 | pass |
| 空输入与单类别的完整Markdown生成 | 2项通过，不崩溃、不生成NaN | 2/2（报告收尾补验） | pass |
| 小汇总/历史证据准备 | 每项与选定历史结果一致 | 894项通过 | pass |
| 小时SQL独立字面预期 | 5条人工记录；UTC1时3购买/2用户/6.25，23时1/1/0.00 | 完全一致，view不计入 | pass |
| 小时运行及不可变证据 | 唯一受控读取，全部断言通过 | 97项；1次物理事实加载；正常停止Spark | pass |
| 日指标 | 31个日期、选定字段逐值与T1.3相同 | 31/31一致，金额状态complete_observed | pass |
| V=U×R×M | 绝对1e-6、相对1e-10；仅口径检查 | 最大绝对误差5.820766091346741e-11 | pass |
| 漏斗 | 整体/逐日/价格桶/排除/购买审计保持T2.1内容 | 四份CSV与原收据、原本地结果一致 | pass |
| 品类金额和购买事件 | 11598630.22 / 37019 | 14个桶合计完全一致 | pass |
| unknown | T1.3已测金额1209130.91，购买事件8720 | 完全一致；分母保留unknown | pass |
| 品类整月去重用户和买家 | 月内跨日去重，不能相加每日人数 | 未测；仅有user_days/buyer_user_days | not_measured |
| 小时0–23 | 24桶；37019事件，11598630.22金额 | 完全一致；小时用户不相加 | pass |
| 独立标准库CSV复查 | Decimal/整数精确，比例沿既有容差 | 791项通过 | pass |
| 图数据 | 8张实际图的artist值/顺序与源CSV一致 | 8/8；源CSV与图像指纹留本地 | pass |
| 人工绘图 | 正常小汇总和空汇总均可绘图 | 各8张，16/16完成 | pass |
| 逐张视觉检查 | 标签、单位、UTC、分母、NA、无裁切误导 | 8/8实际图已打开检查 | pass |
| 最终文本重现 | 最终报告代码生成相同Markdown | 2/2逐字节一致，另存本地检查目录 | pass |
| 历史输入不变 | 1412个旧本地文件大小/mtime与113个旧受控文件SHA不变 | 一致；选定关键证据另核对指纹 | pass |

数字化检查计数代表断言，不代表独立统计样本或性能测试。完整原始结果只留 `.local/t22/`；没有收回事实明细或全部用户清单。FactReader原有31日质量/身份校验仍执行；新增小时SQL最多收回24行，复用同一缓存上下文并最终释放。

## 已观察到的结果

月去重用户151121、购买用户17121、购买事件37019，观测购买金额11598630.22；月人数引用T1.3收据，不相加日用户。日金额最低278736.72（31日）、最高546884.71（16日）、中位368832.94。16日U=11434、R=9.8653%、M=484.83；31日U=10079、R=7.1833%、M=385.00。U最大在15日，M最大在14日。极值不是异常，恒等式不是贡献拆解。

formal路径1341998：N_cart=30908、N_purchase=33324、N_three_step=15112；四个冻结比例为2.3031%、48.8935%、2.4832%、1.1261%。四种互斥类别为15112、18212、15741、1292933。右截尾40426、同秒不确定92单列。首次view价格带的view→purchase依次1.6549%、2.2241%、2.5063%、2.6568%，unknown零分母为NA；不能解释为价格因果。

Top1/5/10类别桶的金额占比75.4420% / 98.2874% / 99.9710%，含unknown。electronics为8750242.89；unknown为1209130.91，占10.4248%，排名第二。品类users/buyers跨日非可加，缺口不以“用户日”冒充通过。

UTC9时购买事件最多2788（7.5313%），小时内去重买家2011、金额908177.91；UTC23时最少125（0.3377%），买家95、金额39416.45。没有业务时区，不能解释当地作息或据此决定投放时段。

以上只是单月固定用户日志样本的描述性观察；不是平台转化、财务收入、永久流失、价格效果或策略收益。详细数字与分母见 [behavior.md](../reports/behavior.md)，业务阅读版见 [period_summary.md](../reports/period_summary.md)。

## 环境与资源

没有安装任何包或修改依赖锁。主分析使用原项目Python3.11.15、Spark3.5.8、Java17.0.19，local[4]/Driver4g/UTC/shuffle32，无Hive。Spark本轮只启动一次：同一进程先做5条人工SQL，再受控读一次真实事实作小时汇总。未重跑ETL、T1.3或T2.1，未读取任何原始/候选/工程CSV。

项目虚拟环境没有matplotlib。绘图仅复用本机已经存在的Python3.12.2/Matplotlib3.10.8环境，读取脱敏CSV；没有向该环境安装依赖，也未改变全局默认环境。字体与缓存均指向本轮本地目录。该绘图环境不在项目锁内，版本记录供复核，不宣称由现有requirements.lock自动覆盖。

- 小汇总准备0.223秒，来自prepare收据。
- 小时worker16.049秒；launcher17.469秒，包含进程启动/正常退出；两者重叠，不能相加。未测连续全流程耗时，不作历史性能比较。
- 小时阶段每2秒检查预算，11个检查点；采样新增文件高水位1524839 bytes，最低可用564219469824 bytes（约525.47 GiB）。这不是内存峰值，也不包含之后的全部图表。
- 收尾审查时 `.local/t22` 为4401897 bytes（含人工图、日志、预期、收据与最终报告复现副本）；最终累计交付审查另计全部共享代码/报告/图片，保留本地delivery收据。上限2 GiB，空闲下限150 GiB。
- 交付前审查检查点：本地新增与28个新增/修改共享文件的完整大小保守合计5700869 bytes（约5.44 MiB），可用564177469440 bytes（约525.43 GiB）；后续只有小型复核和Git交付收据，没有再次运行Spark或生成事实数据。
- 峰值内存 not_measured；没有为补测重跑或申请管理员权限。

## 运行与复查

从实际项目根目录运行并始终正确引用目录尾空格。`config/behavior.example.json` 的占位路径必须填到被忽略的 `config/behavior.local.json`，只绑定既有canonical run。prepare/hourly的run目录必须是全新目录；已存在不覆盖。历史版本的人工门槛只对匹配代码指纹有效。

```sh
.venv/bin/python -m unittest tests.test_behavior tests.test_analysis_scope tests.test_fact_access
.venv/bin/python -m unittest tests.test_behavior_report
.venv/bin/python scripts/behavior_analysis.py --config config/behavior.local.json --run-dir .local/t22/NEW_PREPARE_RUN
```

本次已执行的小时命令如下，仅记录复现入口，**本轮不得再运行**：

```sh
.venv/bin/python scripts/run_behavior_hourly.py --runtime-config config/local.yaml --config .local/t22/behavior-month-01/prepare.json --synthetic-gate .local/t22/unit-gate.json --run-dir .local/t22/hourly-month-01 --budget .local/t22/budget.json
```

新生成的安全CSV经核验后置于reports；漏斗CSV直接引用原件。绘图入口 `scripts/plot_behavior.py --input-dir reports --funnel-dir reports --output-dir NEW_LOCAL_FIGURE_DIR`，用已经存在且版本已记录的Matplotlib解释器；MPLCONFIGDIR/XDG_CACHE_HOME指向`.local/t22/render-cache`。独立复核入口：

```sh
.venv/bin/python scripts/check_behavior.py --prepared .local/t22/behavior-month-01/prepare.json --hourly .local/t22/hourly-month-01/complete/validation.json --render .local/t22/real-figures/render_validation.json --output .local/t22/NEW_CHECK_RECEIPT.json
```

Markdown写出脚本为 `scripts/write_behavior_report.py`，消费这些已审查CSV和prepare收据，使用排他创建；最终代码在另一检查目录重现两份报告，不覆盖既有输出。验收记录、真实配置、日志和所有机器路径均被忽略。

## 首次阶段状态与待办（历史）

已完成的报告与核验结果可审阅；整项不提前done，剩余项明确为品类月去重人数的范围决定。若认可仅报告用户日须由用户确认口径；若需要月去重则须另获category事实聚合授权，不能用现有日汇总推造。T2.3、T4.1–T4.4仍not_started，Criteo/T0.4和全项目G0/G1保持原状态，本人解释不代验。下一项唯一建议为T2.3一页业务决策备忘录，本轮没有执行。

## 2026-09-17 closeout：品类整月去重

起点与参考提交均为 `8151c602cf8b8788c29a58d0c77cad6b80c61de1`，工作区干净、private/main无冲突。唯一scope、fact/metric/funnel run及baseline_keep_all不变。本轮明确授权一次category_l1事实聚合，执行run为 `category-month-01`，收据在被忽略的 `.local/t22_closeout/category-month-01/complete/`。

`scripts/close_behavior_categories.py` 从已冻结的 `sql/metrics/event_dimensions.sql` 原样提取category_key/category_label两个CASE表达式，并先核对该文件指纹与T1.3完成收据一致。完整ASCII格式、首段、大小写、空白和typed unknown语义均未变；没有运行品牌、价格带、first_seen或T1.3构建SQL。新查询仅按scope×category_key×category_label做月内COUNT DISTINCT，金额仍显式Decimal(38,2)、只计amount_eligible。FactReader保留全部event_eligible行为作用户分母。

Spark先运行22条人工记录（3条基础、8条跨品类扩展、11条格式边界，各自独立），全部字面预期通过后才访问真实事实。复用同一个FactReader上下文，count/amount分别验门禁，物理Parquet加载1次；真实分析只接收14个品类聚合，无用户ID或事实明细。原FactReader内部日期质量/身份检查继续执行，未改成跳过。

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 基础人工electronics | 月users=2、buyers=1；逐日users相加=3 | 2 / 1 / 3 | pass |
| 人工跨品类重叠 | 各品类users之和4、总体用户2 | 4 / 2 | pass |
| 人工unknown | users=1、buyers=1、3事件、2购买、金额7.00 | 完全一致 | pass |
| 人工跨日买家 | electronics月买家1、逐日买家相加2 | 1 / 2 | pass |
| 格式边界 | 不trim、不改大小写；非法完整字符串归unknown；真实unknown字符串不碰撞 | 11条符合独立字面预期 | pass |
| 新聚合/合并单元 | 8项通过 | 8/8 | pass |
| 报告和原汇总回归 | 18项通过，含新增人数渲染、三条观察不变、拒绝错误收据/改金额后复用图 | 18/18 | pass |
| 真实返回范围 | 14桶，唯一事实加载 | 14桶 / 1次 | pass |
| 每桶event_records | 与T1.3已验证日category表可加总值一致 | 14/14精确相等 | pass |
| 每桶purchase_events/amount | 与既有category_concentration逐桶一致 | 14/14整数及Decimal精确相等 | pass |
| 全桶守恒 | 2114081事件 / 37019购买 / 11598630.22金额 | 完全一致 | pass |
| unknown金额 | 1209130.91，桶保留 | 1209130.91，月users=75652、buyers=5201 | pass |
| CSV修订范围 | 仅users/buyers/monthly_distinct_status三列 | 14行其他字段与顺序逐值不变 | pass |
| 金额排名及Top1/5/10 | 原排名，75.4420369% / 98.2874264% / 99.9710302% | 原CSV字符串完全相同 | pass |
| 真实运行检查 | 包含人工SQL、逐桶/月守恒、不可变保护 | 88项通过（含8项人工SQL断言） | pass |
| 独立CSV与旧图数值复查 | 全部通过，旧图artist输入不变 | 792项通过 | pass |

真实跨日对照：electronics有31个观察日期，**月users=84077，sum(daily users)=156714；月buyers=9902，sum(daily buyers)=15196**。这是跨日用户重叠，既不要求两者相等，也不把差值叫异常。unknown相应为75652 / 131131和5201 / 6886。完整14桶的月人数与用户日同时保存在[category_concentration.csv](../reports/category_concentration.csv)，Top10表见[behavior.md](../reports/behavior.md)。各品类用户集合还会交叠，不能相加得到全月151121用户。

原CSV只补三列，状态为 `measured_from_fact_monthly_distinct`；原user_days/buyer_user_days、金额、排名、份额、unknown和质量状态不变。behavior只新增品类人数表/粒度说明，period_summary只更新结尾缺口状态，三条核心观察逐字保持。八张PNG均不依赖人数列，**没有重新渲染**。旧渲染收据绑定的是修订前CSV全文件SHA；复核器通过可选 `--category-closeout` 校验新旧SHA、成功收据及仅三列变更，再检查所有原图值/排序和图像SHA，不改写旧收据或假称全CSV指纹没变。

资源沿用Python3.11.15 / Spark3.5.8 / JDK17.0.19、local[4]/4g/UTC。本轮一次Spark启动，worker21.917秒，launcher23.440秒（区间重叠，不相加）；没有重复跑分，峰值内存not_measured。每2秒预算检查共14次，包含4 MiB共享文档预留的采样输出高水位4756533 bytes，最低空闲564095328256 bytes（约525.35 GiB）。收尾检查点新增本地文件489566 bytes，远低于512 MiB，空闲564084695040 bytes；最终交付收据另记录全部本轮文件的保守累计。

旧本地1470个文件的大小/mtime保持不变；141个原跟踪文件在真实运行结束时SHA全部不变，交付前仅豁免本次明确审查的报告/代码/状态修订。原事实、指标、漏斗、小时结果、八张PNG、冻结SQL及旧收据只读；未读取真实CSV、重跑T1.3/T2.1/小时聚合、装依赖或查询其他切片。

实际运行入口（记录复现方式，本轮不再执行）：

```sh
.venv/bin/python -m unittest tests.test_category_closeout -v
.venv/bin/python scripts/close_behavior_categories.py --runtime-config config/local.yaml --config config/behavior.local.json --synthetic-gate .local/t22_closeout/unit-gate.json --run-dir .local/t22_closeout/category-month-01 --budget .local/t22_closeout/budget.json
.venv/bin/python -m unittest tests.test_behavior_report tests.test_behavior -v
.venv/bin/python scripts/check_behavior.py --prepared .local/t22/behavior-month-01/prepare.json --hourly .local/t22/hourly-month-01/complete/validation.json --render .local/t22/real-figures/render_validation.json --category-closeout .local/t22_closeout/category-month-01/complete/validation.json --output .local/t22_closeout/independent-report-checks.json
```

人工门槛收据记录8项通过及生产/测试/冻结表达式指纹，任何修改需重新人工验证；512 MiB/150 GiB预算由启动器检查。已有run拒绝覆盖；失败结果保留staging与差异，只有对账全部通过且Spark正常停止才发布complete。共享CSV的补齐在成功后进行，并逐列检查；用户级数据、配置、路径和日志不提交。

T2.2的工程要求现均满足，状态done（工程验收，本人解释未代验），无未解决工程缺口。T2.3及T4仍not_started，Criteo/T0.4和全项目G0/G1保持原状态。下一项唯一建议T2.3一页业务决策备忘录，本轮停止于此。
