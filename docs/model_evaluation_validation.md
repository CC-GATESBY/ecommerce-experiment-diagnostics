# MODEL-EVAL-01 验收记录

状态：**done（冻结模型的旧test追加公开基准评价；本人解释未代验）**。2026-09-24，run=`model-eval-test-01`。起点`f2475315129376c081dc3867623adaa4435f1504`，指定public/main、工作区干净，真实目录末尾U+0020保留。唯一真实运行成功；没有fit、partial_fit、重训、调参、重选候选或缺陷后的真实重评。

## 评价前约束与证据身份

[协议](model_evaluation_protocol.md)及[配置](../config/model_evaluation.json)在新test特征/评分/业务结果前保存，本地`protocol_before_data.json`关闭后才绑定源文件。协议SHA256为`31f243a8686876142774a3392e062555e0787fd19497a79acbd740c9295f10da`。原v4 E2以面积为主的范围在执行前调整为30%响应−简单的直接G差；Qini另用本版1%网格、floor人数、实际K/N定义，只作辅助点估计，不混用原规划的ceil约定或G命名。

原test已用于TARGET-02，E1是在已知此前结果后开发。本轮没有全新独立确认性质，原报告不回写。E1成功收据、四角色收据、模型SHA/参数/迭代、历史方法及输出指纹全部一致；四模型仍为响应150、S150、T-control129、T-treatment150轮，运行入口对训练调用设禁止保护。

corrected CSV实核3,248,115,221 bytes，SHA256 `e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`；原membership gzip为576,697,968 bytes，SHA256 `a03f1ba4e8a1465dd0998f295e1a190e2e61d25e82c605f340af5bbc7549e7e1`。来源/划分成功证据、逐ordinal身份与逻辑SHA通过，缓存前后字节SHA相同，收尾大小/mtime仍一致。

旧test缓存只有f0/f1，因此顺序解析完整13,979,592条源记录及membership，其他split只核对结构/身份/臂人数，不转换或保存其特征、conversion。新cache只留原test的row_id、十二DOUBLE特征、treatment、conversion，共452,718,746 bytes。源指纹核对还额外读取前后全文件字节，不能称整个流程只扫描test字节或只有一次文件遍历。visit/exposure未用于本轮。

## expected / actual / pass

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 原test身份/QC | N=2,794,557；control/treatment n=419,366/2,375,191；conversion=813/7,295 | 逐ordinal、test与两臂身份序列、计数全部一致 | pass |
| 四模型身份/无训练 | 与uplift-valid-01收据SHA、参数、迭代相同；禁止训练 | 4/4一致，训练调用0；人工错SHA在反序列化前拒绝 | pass |
| S/T及标签隔离 | S同x设t=0/1；T两模型差；真实t/y不进排序；负值保留 | 五份排序先保存后评价；S负分10,620条、T负分304,874条；人工标签/处理变化不改选人 | pass |
| 同容量/并列/嵌套 | 每策K=floor(cN)，原完整hash与row_id并列规则 | 五策均为279,455 / 558,911 / 838,367 / 1,397,278 / 2,794,557 | pass |
| 原随机/简单基准 | 完整排序、每个容量计数和G与TARGET-02相同 | 全部排序身份digest精确一致；10组旧点估计/计数逐项相同 | pass |
| 联合重抽 | 五策×五容量共同抽样、原实际c不变、seed20260924 | 2,282个类型（上限12,500）；25组结果及20组差各1,000次有效，无失效重复 | pass |
| 独立计数/算术 | 直接选中掩码计数与压缩联合类型一致；Fraction复算G与差 | 整数精确；金额无关，G及差浮点误差<1e−12 | pass |
| Qini与面积 | 人工累计Q=[0,0,1,0.5,0]、面积0.375；无control不可用 | 人工字面预期一致；真实505点整数与Fraction Q一致，五面积独立有理数积分误差<1e−9 | pass |
| 两种随机参照 | 实测RANDOM不强行等于L；负值/稀疏保留 | RANDOM面积−28.1339；随机/简单1%前缀4/9个control转化已标稀疏；真实无缺control点 | pass |
| 100%同集合 | 全QC一致，所有直接策略差及区间0 | 五策G均11.32691237596033，4个差及区间精确0 | pass |
| 不可变/发布 | 原raw、membership、规则、模型、valid/test历史证据不改；只发布小表 | 原证据指纹不变；四共享CSV与成功run逐字节一致 | pass |

5个小型人工测试在真实读取前通过，入口再次执行同一门槛；覆盖禁止训练、条件预测/负值、并列与顺序无关、标签隔离、重叠同名单零区间、空臂、稀疏和负差、手算Qini、流式身份对齐、保留重复逻辑记录及拒绝覆盖。最初人工夹具的source摘要格式不合法，已在真实读取前改为合法synthetic摘要；没有真实失败或重新评分。真实收据114项核验通过，另有来源、模型、身份和冻结断言；不把数量当业务成果，也不要求模型必须胜出。

## 资源、产物与实际命令

既有Python3.11.15、NumPy2.4.6、SciPy1.17.1、DuckDB1.5.5、scikit-learn1.8.0；依赖锁未改，无安装、下载、Spark或云。四分类器依次加载，batch=65,536，计算线程最多4；旧test数据库只读，DuckDB内存限额512MB。

连续主入口143.260秒：缓存阶段93.194秒（内部解析/对齐86.682秒）、评分/排序/原名单核对44.623秒、评价4.065秒；其余为人工门槛、验证与轮询，不作性能比较。每2秒采样进程树RSS最高1,379,549,184 bytes（1.285 GiB）；这是采样高水位，整棵进程树瞬时峰值not_measured。全机Swapouts累计增加340，不能归属本任务；未触发7.5GiB或持续交换停止条件。

运行采样新增本地高水位620,499,194 bytes（0.578 GiB），最低空闲537,747,193,856 bytes（500.816 GiB），另预留256MiB用于文档/收尾，低于6GiB、空闲高于150GiB。模型未复制，新预测、排名、缓存、资源采样与日志均在被忽略的`.local/model_eval/model-eval-test-01/`。未保存1,000×数百万矩阵，没有新图或绘图依赖。

```sh
.venv/bin/python -m unittest tests.test_uplift_metrics -v
.venv/bin/python scripts/run_model_evaluation.py --run-id model-eval-test-01
```

第二条是本轮已完成命令，不是要求继续跑：既有run和共享目录拒绝覆盖，固定run ID不接受新ID轮询结果。监控需要本机只读`ps`/`vm_stat`权限；不可用则停止，不跳过预算。没有真实数据与原模型时仅能运行人工测试，不能宣称复现完整公开基准。

四份公开CSV为[容量结果](../reports/model_evaluation/coverage_comparison.csv)、[成对差](../reports/model_evaluation/policy_differences.csv)、[Qini网格](../reports/model_evaluation/qini_grid.csv)、[面积](../reports/model_evaluation/qini_area.csv)，共25/20/505/5行。完整精度、稀疏、失败状态保留；原valid仅引用。业务判断和条件式迁移说明合在[主报告](../reports/uplift_additional_evaluation.md)，不另造重复报告。

MODEL-EVAL-01完成；E2只登记旧test追加评价子项，首次独立确认条件未满足。E3登记本次条件式迁移说明，不表示真实业务迁移或上线；T7.3/G2及本人解释不代验。后续只提出目标业务处理前特征、随机干预和成本证据要求，不继续查询旧test、调参或训练。
