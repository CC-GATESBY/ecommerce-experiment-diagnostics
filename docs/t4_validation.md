# T4.1–T4.4：单一业务诊断案例验收

2026-09-18，`diagnosis-oct-02`。T4.1筛选、T4.2恒等式拆解、T4.3维度贡献/JS、T4.4案例与备忘录分别达到工程要求，本人解释未代验。业务结论见[10月25日案例](../reports/case_observed_change.md)：先做限定的electronics商品构成核对，尚不足以直接调整价格、流量或优惠。

## 来源与范围

起点01661f9151d94c73e8a006fbbd94c22693bde049，实际目录保留末尾U+0020，初始工作区干净、private/main与远程一致。唯一analysis_scope为rees46_oct_user5_analysis_v1，metric_run=metrics-month-01，fact_run=month-v101-01，baseline_keep_all；原范围、输入、membership、指标和历史收据不改。

复用select_snapshot，增加可选的明确表名子集（原默认行为不变），只核对并打开agg_daily_metrics、agg_daily_dim的两个Parquet文件，分别31/6,879行。完成/独立核验收据、来源契约、品牌映射指纹、原日期门禁及history_readiness共同核对；选定文件SHA与T1.4 protected_hashes一致。没有扫描用户日、事实、路径、原始CSV或Criteo明细，没有调用Spark。旧完整manifest哈希仅复用T3.4已经审查的精确Criteo追加兼容，不放宽其他证据或创建新登记。

执行SQL仅为两个明确文件列表上的`SELECT * FROM read_parquet(?) LIMIT n+1`，n取完成收据并再限定31/6,879。完整SQL、文件参数、15个小型证据/选定文件指纹仅保存在本地validation.json；来源路径不写入提交报告。历史比较使用2019-10-04、11、18，当前日25日，UTC；没有查询新的业务切片。

## 固定规则与实际结果

[config/anomaly.yaml](../config/anomaly.yaml)及报告方法段在真实查询前写入并保留本地冻结副本；阈值、窗口、选择规则没有随结果改变。回顾性探索，不是前瞻盲测。无币种/损失容忍依据，绝对金额仅排序展示，不补v4可选商业绝对阈值。

| 项目 | expected | actual | pass |
|---|---|---|---|
| 过去同星期历史 | 仅−7/14/21/28天、≥3个可用点，缺失不补零 | 62行count/amount readiness逐项一致；21天不足、10天可评估 | true |
| 选择分支 | 优先向下候选最大金额减少，并列日期升序 | 唯一候选2019-10-25；中位数差−52,663.86、−12.4945%、score −6.4398 | true |
| 人工检测边界 | 不使用未来；不足/缺日/阻断/零基线/MAD有状态；无候选描述性分支 | 12项本轮小汇总/选择器测试通过 | true |
| U/R/M恒等式 | 同组历史mean(U/B/V)导出R/M；非正/近零拒绝相应份额 | 实例残差2.7756e−17，低于1e−12；人工负贡献/抵消通过 | true |
| 日期×维度完整性 | 31×4组的事件/购买事件/Decimal金额均守恒，缺整维度不得补0 | 全部一致，键唯一，unknown/other保留 | true |
| outer join金额差 | 每维度精确等于V−历史均值 | 4维度均−66,768.456666…；用原整数分值×历史天数作独立精确核对 | true |
| 金额份额与JS | 新增/消失/unknown保留；全零/近零不造百分比；JS为base2散度 | 人工通过；真实4维度与独立熵公式差<1e−12 | true |
| 品类覆盖 | 历史合计的比率，不平均日比率 | 事件+0.6888pp、购买事件−1.3675pp、金额−1.7384pp | true |
| 图表及文本 | 与输出CSV、独立算术核对一致 | 3张图数据Artist核对且逐图检查，无裁切；报告核心数字一致 | true |
| 旧入口/证据 | 原选择器默认语义、T2.3初稿及证据保留 | 4项选择器原单元回归、12项v1备忘录回归通过；v1与原文件SHA相同 | true |

独立算术检查使用选定收据里的小型日汇总、CSV中的原历史金额总和和整数分值，不调用生产拆解函数作为预期；图的源值与Artist数据核对另行记录。未做第二套事实ETL，也不把两次相同小表计算称作独立来源验证。

首次人工测试有一处手写score小数录入错误；按−90/(1.4826×20)=−7500/2471精确分数纠正，算法与阈值未动，全部人工通过后才查询真实小表。首次真实尝试完成数值结果后，因项目.venv无matplotlib在可选绘图处退出；失败staging保留。修正为绘图依赖缺失只标not_rendered后，用同一参数复验小表完成，五张CSV及case_summary与首次数值产物字节一致。随后以现有绘图解释器仅读取本轮安全汇总生成图；一次修正坐标留白和日期标签，没有重跑真实分析或改数字。

## 交付与不可变保护

筛选31行、分解5行、四维度贡献222行、维度分布摘要4行、覆盖3行；真实用户/session标识均不在输出。图为3张独立PNG；原T2.2图片和T3.4方案不变。[备忘录v1](../reports/business_decision_memo_v1_t23.md)是原文逐字节副本，原evidence CSV不变；原T2.3校验器/测试只把读取指针改到v1。新v2注明具体修订证据与行动顺序，旧结论没有被抹掉。

DuckDB使用项目Python3.11.15 / DuckDB1.5.5，threads=2、memory_limit=512MB、临时上限128MB，内存数据库；这些是限制配置，不是进程峰值实测。绘图仅复用已存在Python3.12.2 / Matplotlib3.10.8和Arial Unicode MS，缓存只写本轮.local目录；未安装包、不改锁或全局环境。

成功分析记录0.239秒（含人工测试与身份核验、两小表读取和计算；不含后来独立绘图），不作为性能基准。该检查点.local/t4为185,853 bytes，空闲557,319,176,192 bytes；最终图及文档另计后仍远低于1 GiB，保留150 GiB。最终资源与原文件核验收据保存在.local/t4。峰值内存not_measured，不为补齐测量重跑。

一个分析入口`scripts/run_diagnosis.py`，计算函数集中于`anomaly/diagnose.py`。在本机既有配置与冻结副本存在的项目根目录，人工复核可运行：

```sh
.venv/bin/python -m unittest tests.test_diagnose tests.test_idempotency.IdempotencyUnitTests tests.test_business_memo -v
# 后续另获授权时，只读同一小表并使用新run ID：
.venv/bin/python scripts/run_diagnosis.py --run-id diagnosis-oct-NEW
```

绘图模式为同一入口的`--render-summary .local/t4/<run>/complete`，只读本轮汇总，输出目录排他创建，已有图不覆盖。独立核对及渲染收据、冻结原稿、失败记录均留.local/t4。没有未解决工程阻塞；因果、上游漏数、窗口first_seen及只有3–4点历史的限制保留。T4.5、T5、定向投放、同商品价格扩展和全项目门槛没有提前完成；本人解释项不代勾。
