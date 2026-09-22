# TARGET-02 验收记录

状态：**done（冻结简单规则的test留出评价完成，本人解释未代验）**。run=`targeting-test-01`，2026-09-22；一次成功评价，无真实失败/重评估、无重新训练或改方案。正向结果与工程完成分别判断，不代替E1模型训练、完整E2模型评价、T7.3、G2或真实实验验收。

## 先冻结，再评价

实际目录末尾U+0020保留；起点`645306c099bddd46e55963ee858f8f5552df88c4`，工作区干净、origin为指定private/main。[协议](targeting_holdout_protocol.md)在真实读取前落盘；SHA256 `ea2d41dd4d4fd0239d9b0b8b99d8c30056f3200e9a3ed13568b3d8f6058b5527`。本地`protocol_before_test.json`保存协议/入口/测试代码/旧配置指纹及时间，关闭后才调用原来源绑定。

原[冻结规则](../reports/targeting/frozen_rules.json)SHA `3fae3c428d96aa607ed43d13996b2f0db08a34373334c082208bb9b4baebe5a2`、原配置SHA `324cf7a4c7e527480c5fc02116759c58969ac09ad5e0f41a10099958d6133228`，与TARGET-01完成收据及已提交代码指纹一致。`load_frozen`只读这份规则，指纹不符拒绝；未修改旧`uplift/targeting.py`及测试，不调用`train_rules`或分位查询。

薄适配`apply_test`从test的row_id/f0/f1生成不含标签的`selected_ranks`，按原右闭边界、训练名次、哈希及row_id碰撞次序排序；之后才关联原treatment/conversion。没有把test重命名成valid。共同的`joint_table`和`evaluate`原样复用，规则/五个容量/1,000次重抽/稀疏和空臂方法均不变。

## 输入与物理范围

唯一corrected来源与原`criteo-split-v1-01` membership，未生成新划分。CSV实核3,248,115,221 bytes，SHA `e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`；membership gzip 576,697,968 bytes，SHA `a03f1ba4e8a1465dd0998f295e1a190e2e61d25e82c605f340af5bbc7549e7e1`，原逻辑SHA和test/两臂序列SHA均精确吻合。

之前只有train/valid缓存，本轮严格CSV对齐扫描13,979,592个逻辑记录，保留原ordinal重数；其他split检查结构、身份及所属臂人数，不转换/保存其特征或conversion。只提取原test的2,794,557条：control 419,366、treatment 2,375,191；conversion分别813、7,295，与原test QC一致。

新TSV仅`row_id,f0,f1,treatment,conversion`五列，298,233,909 bytes；SHA `cffdb2bbbd2fa084b9b2cd92c8d87ea0b47ecc7dc8f7b36ad51e367dc03dd8cd`，分析数据库213,921,792 bytes，均只留被忽略目录。原始CSV全文件字节身份核对在前后各读取一次，因此不是“只物理读取test”，也不称整个过程只有一次文件遍历。原test整体QC及全量ATE此前已查看，本轮只增加冻结规则的首次test策略评价。

## expected / actual / pass

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 原来源/membership | 来源SHA、连续逻辑ordinal、原row_id与split、各臂人数一致 | 全13,979,592条对齐；逻辑SHA、test/两臂序列SHA一致 | pass |
| test规模与原QC | 2,794,557；两臂n=419,366/2,375,191，conversion=813/7,295 | 精确一致，100%选中全体 | pass |
| 冻结加载 | 不调用训练，错字节指纹拒绝 | 人工mock训练禁止调用；变更规则文件被拒绝 | pass |
| 名单不依赖标签 | 修改人工test的conversion或treatment后，完整排序不变 | 与独立bisect/hash排序一致；排序表无两字段 | pass |
| 同容量/嵌套 | K=floor(c×实际N)，三规则相同K，完整名次1至N | 279,455 / 558,911 / 838,367 / 1,397,278 / 2,794,557，均精确 | pass |
| 相同定向规则 | 完整排序相同，各容量重叠=K，策略差及区间为0 | 全部一致；100%三规则同样精确0差 | pass |
| 联合重抽与主比较 | 原方法保留共同成员；唯一30% INCREMENTAL−RANDOM主比较 | 50个完整联合类型；15组结果/15组差完整；各1,000次有效，无失效重复 | pass |
| 负差/稀疏/空臂 | 保留负数，少成功/失败标记；空臂不补小数 | 人工全量G=−5,000且稀疏；空臂G=null、有效重复0 | pass |
| 直接计数/算术 | 独立SQL逐选中集合计数，Fraction复算G及差 | 15组两臂n/成功数精确；G及15组差误差<1e−12 | pass |
| 原规则/数据不变 | 原raw、membership元数据及SHA、协议/旧配置/代码前后相同 | 一致；旧train/valid结果不重算，原脱敏CSV不改 | pass |

先行4个新人工测试及5个直接相关TARGET-01回归通过；后者保留已实现的联合类型与逐记录重抽分布/矩人工比较。真实入口97项检查通过。没有重跑T3.1划分、T3.2 ATE或TARGET-01真实评价；本轮没有test分层效果表、最优容量选择或新特征探索。

测试/统计输入是原conversion，不改变treatment。校验只判实现与完整性，不要求正区间。有效重复不等于平台校准：当前区间条件于冻结规则和发布样本，辅助区间非同时覆盖，不含成本、发布抽样或跨期风险。

## 资源与运行

既有Python3.11.15 / DuckDB1.5.5 / NumPy2.4.6 / SciPy1.17.1，未安装、下载、启动Spark或改依赖锁。DuckDB4线程、2GB内存限额，临时目录限额2GB；本轮总产物上限4GiB，最低空闲150GiB。入口完成时采样新产物高水位512,204,969 bytes（0.4770GiB），最低空闲541,725,151,232 bytes（504.5209GiB），不把检查点采样当连续峰值。报告/收尾小文件另行纳入最终预算核对；峰值内存not_measured。

连续入口84.942秒，其中CSV/membership对齐75.889秒；这是本次具体任务计时，不是性能基准，也不与TARGET-01计算规模不同的耗时作加速比较。

```sh
.venv/bin/python -m unittest tests.test_targeting_holdout tests.test_targeting -v
.venv/bin/python -m uplift.targeting_holdout --run-id targeting-test-01
```

第二条是已完成的历史命令；同run ID拒绝覆盖。没有自动重试/调参选项，不应再换ID反复查看test。失败将写独立失败收据，不能登记为complete；真正缺陷复验应记录已看过结果及修复原因。

本地证据位于`.local/target02/targeting-test-01/`：评价前协议、缓存完成、排序先于评价、完成收据、五列缓存、数据库及联合类型；原始日志/记录ID/标签均不提交。对外只逐文件发布[结果CSV](../reports/targeting_test/coverage_comparison.csv)、[策略差CSV](../reports/targeting_test/policy_differences.csv)和[业务报告](../reports/targeting_holdout_review.md)，两表与成功run字节相同。

收尾核对报告中的人数、概率/百分点、G、成对区间、原valid引用及链接全部通过；所有旧跟踪文件中仅授权的README/TASKS变更，其余指纹不变。本地与共享新增总量低于0.48GiB，空闲仍高于504GiB。展示核对最初将精确零的`0 [0,0]`误要求为四位小数；修正核对器的等值格式判断并保存记录，未修改数据、报告数值或重跑真实评价。

未解决的是业务迁移与成本证据，不是需通过调参补救的工程缺口。本人仍需解释：G的分母为何不是实际新增客户；两种定向同名单为何只算一种证据；随机留出支持为何仍不能批准优惠券部署。任务到此停止。
