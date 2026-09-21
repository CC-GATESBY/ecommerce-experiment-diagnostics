# T5.5 已知效应注入验收

状态：**done（已知效应模拟与单次评估；非真实策略效果，本人解释未代验）**。日期2026-09-21；起点提交`4124b2d4d30a8a85d6cca30334b99e2f5075501a`。真实运行`injected-oct-01`，只包含同分组的S0/S1；没有重跑300次A/A、选择种子或要求显著才能通过。

## 输入与执行

实际项目根目录末尾U+0020保留，工作区起初干净，本地/远程main一致且private。输入固定为`cohort-oct-01`、`rees46-pre-oct01-14-post-oct15-28-v1`。检查完成状态、12项历史验收、28日计数许可、scope/窗口/来源与文件指纹；DuckDB一次投影只读取cohort_key、post_converted、scope_id，上限84,166行以发现超量，实际84,165。未查询user_id、金额、post_active，未按结果筛选。

原数值文件SHA256：`d361a8660b7e8f4bd40bc4bc5b7a54e2bf4c74343990fcf338c7d22d9a266e97`。身份文件仅核对指纹，不查询其列；两个文件及原完成收据运行前后相同。原事实、用户日、原CSV、Criteo、11月与购物车数据未读取；原A/A代码、报告和依赖锁未更改。

在真实执行前保存`config/injection.json`、`docs/injection_contract.md`及代码指纹。人工门槛先通过，再一次读取二元队列。PCG64生成两场景潜在结果后，唯一新前缀/ID分配一次。Y0只读，Y1另建；本地文件名明确含`simulated_potential_outcomes_NOT_BUSINESS`，不回写指标层。

## expected / actual / pass

| 检查 | expected | actual | pass |
|---|---|---|---|
| 全队列与原购买标记 | N=84,165；sum(Y0)=4,812；不筛未返回者 | 84,165 / 4,812；投影无筛选条件 | 是 |
| 字面U边界 | Y0=[0,1,0,0]，delta=3/16、U=[.1,.9,.25,.2] → [1,1,0,1] | 相同，U=q不翻转；原1不翻回0 | 是 |
| S0与非法输入 | S0不变；负数、非有限、越界delta、p0=1正向注入拒绝 | 均符合；不裁剪q | 是 |
| 构造/分组时序 | 两次潜在结果构造后才调用一次分组；改变Y0不改变分配 | 调用顺序及结果无关性人工核验一致 | 是 |
| 可复现与旧接口 | 逆序、同键/seed、跨进程一致；旧AA仍拒绝新ID | 一致；新适配只允许预定一个ID | 是 |
| 人工注入率 | 100人/500次；平均K期望8；MC SE=.12；预设±6SE | 平均K=7.918；z=−0.6833；平均delta=.07918（目标.08） | 是 |
| 正常统计复用 | 原proportions及SRM公式不变；不以p或覆盖验收 | 两场景可计算，p=.0826/.0712；SRM=.7590 | 是 |
| 独立公式核验 | 整数/Fraction、标准库NormalDist/erfc重算 | A/B均值、差、SE、CI、p、tau和误差一致 | 是 |
| 同组增量恒等式 | S1估计−S0估计=flips_B/n_B | 精确两侧均241/42038 | 是 |
| 原输入/隔离 | 原Y0及原文件指纹不变；用户级模拟只留本地 | 不变，`.local/t55/`被忽略 | 是 |

7项新增人工测试与3项直接相关旧回归通过。新测试包含固定分组内翻转的字面例子：A、B各4人，原各1个购买，B潜在新增2个时估计增量为1/2；不依赖分组后基准率设定效应。人工500次只验证二项生成机制，不执行显著性评估，不是队列功效曲线。

真实摘要的独立核验不调用原统计函数：从输出人数/购买数用Fraction计算差与tau，以标准库NormalDist及erfc算SE/CI/p；浮点一致标准rel_tol=1e-12、abs_tol=1e-15。增量恒等式使用Fraction完全精确，无浮点容差。CSV保留原始概率及百分点/每万人尺度，不因报告显示四位小数而改写估计。

## 资源、产物及复跑

Python3.11.15 / NumPy2.4.6 / SciPy1.17.1 / DuckDB1.5.5，均已有，无安装与锁文件变化，无Spark或云资源。本地新增约3.6MiB（含一个约3.54MiB压缩模拟数组及日志/收据），加共享代码文档远低于512MiB；执行后空闲约509.75GiB。记录的一对模拟计算约0.165秒；含人工门槛、指纹、单次投影和发布准备的入口计时约1.152秒，并非性能基准；峰值内存not_measured。

本地完整证据位于`.local/t55/injected-oct-01/complete/validation.json`，记录列投影、资源、代码/输入/数组指纹、精确恒等式和独立预期/实际；实际路径与用户级内容不提交。脱敏结果CSV SHA256为`9e5cf16cd273e9e7741c9b5c64b08ea091a6fb52aebaf1b3ee389a06bb62b9fc`。

人工与受影响回归：

```sh
.venv/bin/python -m unittest tests.test_inject tests.test_aa.AssignmentTests tests.test_aa.StatisticsTests.test_binary_literal_formula_and_units -v
```

入口（在项目根目录，路径必须保留末尾空格）：

```sh
.venv/bin/python scripts/run_injection.py --run-id injected-oct-01
```

该ID已经存在，再执行会拒绝覆盖；本轮未重复运行真实场景。以后确需复验时使用新的本地run目录名，固定config中的实验ID、seed和两场景不变。失败保留staging/failure，不发布complete。预算同时为共享文档预留16MiB，最终实际字节在本地审查收据记录。

结果本身与实现通过分开：两场景本次CI均包含各自tau，S1虽正向但未达到5%门槛；这些不是工程通过条件。不证明长期覆盖、无偏性、功效或真实策略收益。T5.6/T5.7、T4.5及全项目门槛未代勾；本人解释项继续未验，下一项优先T7。
