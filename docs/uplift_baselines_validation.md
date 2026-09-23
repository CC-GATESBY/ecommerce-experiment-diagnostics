# E1 有限模型开发验收

状态：**done（有限基线训练＋valid开发比较；非最终模型确认，本人解释未代验）**。run=`uplift-valid-01`；2026-09-23冻结协议，完成收据UTC为2026-09-23T14:01:44Z（本地2026-09-24）。起点`21a5c78c74fe58876d571d937978d1e65f7990e9`，工作区干净，实际目录末尾U+0020保留，指定origin为public/main。一次成功正式运行，无调参、换seed或缺陷后的重新评价。

## 输入与实现

corrected来源CSV为3,248,115,221 bytes，SHA256 `e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`；原membership gzip为576,697,968 bytes，SHA256 `a03f1ba4e8a1465dd0998f295e1a190e2e61d25e82c605f340af5bbc7549e7e1`。原来源/membership完成证据、逻辑SHA、三个split身份序列与两臂规模均通过。旧缓存只含f0/f1，本轮新建train/valid十二列FLOAT64 memmap；不加载外部模型。

| 原split / 内部分区 | control记录 / conversion | treatment记录 / conversion |
|---|---:|---:|
| train全体 | 1,257,688 / 2,413 | 7,129,585 / 21,992 |
| fit | 1,132,296 / 2,161 | 6,417,220 / 19,797 |
| early_stop | 125,392 / 252 | 712,365 / 2,195 |
| valid | 419,883 / 837 | 2,377,879 / 7,424 |

原test的2,794,557条仅在顺序扫描中核对结构、ordinal、row_id、split及原treatment，不转换/保存/汇总其特征或conversion，也不打开TARGET-02 test缓存。完整CSV扫描及前后字节指纹读取都会经过test字节，不能说只物理读取train/valid。原raw与membership前后大小、mtime、SHA一致；未重分配处理或删除负标签。

内部哈希、所有模型参数、资源试跑、30%容量、固定排序和bootstrap在[协议](uplift_baselines_protocol.md)与[配置](../config/uplift_baselines.json)先冻结，本地`protocol_before_data.json`保存六个方法/环境文件与九个历史文件的指纹，结束全部不变。原冻结简单规则SHA `3fae3c428d96aa607ed43d13996b2f0db08a34373334c082208bb9b4baebe5a2`不变。旧valid数据库只读，用原排序名单的完整身份序列hash对照新名单，不仅比较总人数。

## expected / actual / pass

| 核验 | expected | actual | 结果 |
|---|---|---|---|
| 来源、split与字段隔离 | 原13,979,592条身份对齐；仅train/valid十二特征 | 全部一致；人工test使用不可转数值/标签字符串仍通过，未建test缓存 | pass |
| 显式早停 | 仅train哈希留出，不触发库的默认重新切分 | fit 7,549,516、early 837,757；两臂两标签均有支持；人工禁止内部train_test_split调用仍通过 | pass |
| 特征和S/T机制 | 十二DOUBLE；S仅条件列改变，T分原臂 | 白名单拒绝其他字段；S双条件预测、负差保留，T训练人数精确如上 | pass |
| 名单与结果隔离 | valid标签/实际处理不是评分输入 | 人工变更标签/处理不改变评分；五份真实名单在评价字段加载前保存 | pass |
| 资源试跑 | ≤100,000 fit，≤10迭代，只验接口 | 100,000 fit / 10,000 early；10迭代，保存加载相同；未用效果调参 | pass |
| 模型加载复现 | 四分类器每条valid预测逐值一致 | 2,797,762条×各条件全部相同；只加载本run自建且SHA匹配模型 | pass |
| 同容量与旧简单基准 | 每策floor(.3N)=839,328；原名单/计数/G不变 | 五策均一致；RANDOM与FROZEN_SIMPLE身份序列及结果精确对上 | pass |
| 预测及策略算术 | 独立log公式、直接计数与Fraction算G一致 | 九个logloss、五策两臂计数与G均通过；浮点差<1e−12 | pass |
| 成对不确定性 | 共同抽样保留五份名单重叠、固定种子、失败状态 | 115联合类型，1,000×5结果全部有效；人工负差/稀疏/空臂和同名单零差保留 | pass |
| 不可变保护 | 方法、旧结果、raw/membership不改 | 冻结指纹、raw/membership metadata一致；旧TARGET/POWER/COST结果未重算 | pass |

先行6个本轮人工测试及5个直接相关TARGET回归通过（入口再次执行作为运行门槛）。人工验证包括DOUBLE边界、完整哈希碰撞时row_id顺序、常量/负分数和保存加载；没有重跑TARGET、POWER、COST等历史真实任务。统计通过不要求模型胜出；本次三个模型整体及分臂logloss均优于对应常数，策略差结果见[模型报告](../reports/uplift_model_card.md)，与工程通过分开判断。

## 环境、资源和复跑范围

仅项目`.venv`新增官方wheel：scikit-learn 1.8.0、joblib 1.5.3、threadpoolctl 3.7.0。先做受旧锁约束的依赖解析；1.9.1会增加其他依赖，因此选择已支持显式X_val/y_val的1.8.0，不是按模型结果选择版本。Python3.11.15、NumPy2.4.6、SciPy1.17.1、DuckDB1.5.5保持，`pip check`通过；锁文件来自真实安装环境，增量只有这三包。没有LightGBM/XGBoost、新绘图库、全局修改、管理员操作、Spark或云资源。

| 正式分类器 | 迭代数 | fit调用秒数 | 包括准备、保存与全valid两遍预测的子进程秒数 |
|---|---:|---:|---:|
| RESPONSE_MODEL | 150 | 33.032 | 39.175 |
| S_LEARNER | 150 | 32.211 | 44.049 |
| T_CONTROL | 129 | 4.190 | 8.442 |
| T_TREATMENT | 150 | 27.549 | 33.930 |

连续主入口326.895秒，包括测试门槛、缓存、试跑、正式训练/复验、评价和轮询；不能把各时间当受控性能基准。4计算线程、四分类器串行；每2秒采样进程树RSS最高1,776,386,048 bytes（1.6544 GiB），子进程系统记录最大RSS为1,878,966,272 bytes（S，1.7499 GiB）。前者是采样高水位，后者是单进程系统最大驻留值；整个进程树的瞬时峰值not_measured，不能把输入矩阵大小当峰值。

运行采样新增本地文件高水位2,091,482,058 bytes（约1.948 GiB），最低空闲538,461,093,888 bytes（501.481 GiB）。环境安装及文档另预留256 MiB，整体低于15 GiB，空闲高于150 GiB。全机Swapouts累计增加98,916，不能归属本进程；未出现RSS接近7.5 GiB或RSS>6 GiB并持续交换的冻结停止条件，不宣称全机没有交换。

```sh
.venv/bin/python -m unittest tests.test_uplift_models tests.test_targeting -v
.venv/bin/python scripts/run_uplift_baselines.py --run-id uplift-valid-01
```

第二条是本轮已完成的唯一真实运行命令；已存在run或共享输出拒绝覆盖，不应为了重复看结果删除它们。资源监测需本机能够只读运行`ps`与`vm_stat`；受限沙箱中不可用时应停止，不绕过预算。模型在同一次运行内已逐值复验保存加载后的完整valid预测，未另开真实训练。

本地`.local/e1/uplift-valid-01/`保留协议、缓存、试跑、四模型及其预测、选中标记、评价和完成收据；ID/数组/模型/原始日志全部被忽略。只公开三个小型CSV、协议/配置、实现、测试和报告。E2/E3、新模型test、CUPED未执行；原test已用过TARGET-02，后续评价需单独明确性质。T7.3/G2与本人解释仍待验。
