# 首版阅读与最小复现手册

先从[README](../README.md)选择业务问题，再读报告、对应CSV与验收。数值定位用[result_registry.csv](result_registry.csv)：概率字段保留原0–1值，报告展示时乘100；金额按原字符串/Decimal，不改称收入。登记中的commit是该来源文件最后一次更新提交，不是本轮重新计算结果。

## 不需要真实数据的演示

`scripts/demo_synthetic.py`只用12条synthetic事件，复用T5.1人工构造辅助函数、生产固定窗口SQL与队列函数；另用独立的6人计数例子复用原proportions，验证稀疏时保留点估计但不给CI/p值。合计不足100条人工记录，没有调用真实快照选择器或主任务入口。

在仓库根目录执行。若项目路径末尾有空格，`cd`时用完整引号保留；下面命令使用当前目录，不写死任何个人路径。需要可用的Python 3.11及兼容wheel；不需Java、Spark、下载凭据或`.local`。

```sh
# 在有权限获取的代码副本根目录执行；本仓库仍为private。
demo_tmp=$(mktemp -d)
python3.11 -m venv "$demo_tmp/venv"
demo_py="$demo_tmp/venv/bin/python"
"$demo_py" - <<'PY' > "$demo_tmp/demo-requirements.txt"
from pathlib import Path
names = {'duckdb', 'numpy', 'PyYAML', 'scipy'}
lines = [s for s in Path('requirements.lock.txt').read_text().splitlines()
         if s.split('==')[0] in names]
assert len(lines) == 4
print('\n'.join(lines))
PY
"$demo_py" -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: --no-deps -r "$demo_tmp/demo-requirements.txt"
"$demo_py" -m pip --isolated check
"$demo_py" scripts/demo_synthetic.py
```

若只有已配置的项目解释器，可把建venv一行的`python3.11`替换成`".venv/bin/python"`；创建的是新的临时venv，不继承主环境site-packages。只安装锁内duckdb1.5.5、numpy2.4.6、PyYAML6.0.3、scipy1.17.1，无其他依赖升级、源码编译或全局安装。临时环境位置由mktemp返回，需要时由本人清理；此命令不删除项目文件。演示只向stdout输出，可自行重定向到临时目录，不写真实业务结果。

**实际隔离验证：passed，run_id=`t7-synthetic-isolated-01`。** 在单独临时目录中复制已提交Python/SQL与锁文件、加入演示入口，没有复制`.local`、Parquet或收据。以Python3.11.15创建无系统site-packages的venv，按上述四项版本安装官方wheel，pip check通过；去掉PYTHONPATH/PYTHONHOME后运行相同命令成功。平台macOS arm64。运行日志和临时目录路径只留本地；不把主环境能运行冒充隔离复现。

| synthetic检查 | 独立字面预期 | 实际 |
|---|---|---|
| 前置入组名单 | A/B/C | 相同 |
| 入组/返回/未返回/购买人数 | 3 / 2 / 1 / 1 | 相同 |
| 重复购买事件/买家数 | 2 / 1 | 相同，未去重 |
| 结果期才出现人数 | 2，不加入组 | 相同 |
| 全队列/返回者购买比例 | 1/3 / 1/2 | 相同 |
| 两组各3人、购买1/2人的推断 | sparse_cells；CI/p为null | 相同 |

这只验证人工案例的隔离环境复现，不验证私有真实数据、整个Spark环境或线上系统。稀疏门槛沿用既有统计契约，不代表小样本没有任何可用方法。

## 已有结果怎样追溯

| 主题 | 核心run | 阅读入口 |
|---|---|---|
| 十月事实、指标、独立核验 | month-v101-01 / metrics-month-01 / crosscheck-month-01 | [T1.1收尾](t11_closeout_validation.md)、[T1.3](t13_validation.md)、[T1.4](t14_validation.md) |
| 购物车资格与条件式设计 | cart-baseline-02 | [方案](../reports/next_experiment_design.md)、[T3.4](t34_validation.md) |
| Criteo公开基准 | criteo-itt-v1-02 | [摘要](../reports/criteo_business_summary.md)、[T3.2](t32_validation.md) |
| 双月、购买时间、商品构成 | review-03 / timing-01 / computers-mix-01 | [双月](cross_period_validation.md)、[时间核查](purchase_timing_validation.md)、[商品核查](computers_product_mix_validation.md) |
| 固定队列、A/A、效应模拟 | cohort-oct-01 / aa-oct-01 / injected-oct-01 | [T5.1](t51_validation.md)、[T5.2–4](t54_validation.md)、[T5.5](t55_validation.md) |

真实复跑另需合法来源文件、本机配置、绑定的成功收据与新run目录；本轮没有执行。旧文档中的历史成功命令不是一个无需私有输入的“全量一键运行”承诺；不要使用全套测试发现命令代替本次最小演示。

## 规模与引擎的准确说法

- 十月完整源覆盖扫描42,448,764条，正式固定用户样本2,114,081条；十一月源扫描67,501,979条，新增同规则样本3,340,951条。两月不重叠日期的样本事件合计5,455,032条；**双月去重用户数本轮未计算，不将月用户数相加**。源规模不是全用户指标处理规模。
- 十月事实/指标使用本地Spark（local[4]/4g/UTC），有DuckDB独立核验；十一月增量使用DuckDB，canonical小表nov-metrics-02引用nov-metrics-01解析证据。不是全流程所有数据均经Spark，也不是YARN分布式运行。
- 300次A/A是共享队列的离线重复；500次人工注入机制检查不是功效曲线。历史收据耗时仅说明执行范围，未完成T6受控对照，不计算加速比例。

实际环境与公开元数据见[依赖锁](../requirements.lock.txt)、[环境验证](t03_validation.md)、[十月规模记录](../reports/scale_baseline.md)、[双月验收](cross_period_validation.md)。不要为补技术表述自动安装Hadoop或增加月份。
