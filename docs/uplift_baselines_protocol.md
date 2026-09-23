# E1 有限模型开发协议

2026-09-23，版本`criteo-uplift-baselines-v1`，run `uplift-valid-01`。本协议及[配置](../config/uplift_baselines.json)在真实缓存/训练/valid模型结果前固定。目标是判断模型相对原简单规则是否增加选择价值，不保证模型胜出。

## 数据和训练

唯一corrected Criteo来源、row_id、原treatment及60/20/20 membership不改。只转换并持久化train/valid的f0–f11 DOUBLE、conversion、treatment、row_id与ordinal；身份不作为特征。旧缓存只有f0/f1，因此本轮补建12列typed memmap，不声称已有全特征缓存。顺序对齐raw CSV与membership时，test只检查字段宽度、原treatment、ordinal/row_id/split；其特征、conversion、visit、exposure不转换、不汇总、不缓存。物理扫描会经过test字节，已有TARGET-02 test明细缓存不打开。

train内用SHA256(`e1-early-stop-v1|20260923|`+row_id)前8字节大端整数，小于floor(2^64/10)进入early_stop，其余fit。不使用标签/处理决定成员。三个逻辑模型共享该名单，T按原臂分别取子集。fit与early_stop都须有两类标签和双臂支持；数量与原split QC核对，不欠采样、不配平、不使用class_weight。

基学习器和全部参数固定于配置。四个分类器按RESPONSE_MODEL、S_LEARNER、T_CONTROL、T_TREATMENT依次训练、保存、释放；显式调用`fit(X_fit,y_fit,X_val=X_early,y_val=y_early)`，不让valid参与分箱、树训练或早停，不合并train重训。原简单规则使用完整train，模型只用fit学习、early_stop停步，这是训练使用差别，不声称严格同训练过程下算法优劣。

RESPONSE混合原两臂，用12特征预测响应；不是自然无干预购买率。S只多一列treatment；valid分别构造t=0、t=1预测，差为排序分数。T分别训练两臂模型后对同一个x预测，两概率之差排序。S/T排序不依赖valid实际处理或标签；保留负分数、常量和并列，不强迫异质性出现。

仅用一个资源试跑：在fit中按独立`e1-resource-pilot-v1|20260923|`哈希最小100,000条（不使用标签）取样，训练一个S形式分类器最多10轮；early_stop按同一试跑哈希最多10,000条。只验证资源、双条件预测与保存/加载，不用其效果调参数或作模型成果。正式训练使用全部冻结fit/early_stop范围。

## 预测、名单和策略价值

valid factual logloss按实际处理取预测概率；不对uplift分数计算logloss。fit全体conversion均值、fit两臂各自均值为两个常数参照，每个模型都报告整体/分臂表现。RESPONSE主要参照全体常数，S/T主要参照分臂常数。低logloss本身不证明增量排序更好。

固定30%容量，K=floor(.30 N_valid)，五策为RANDOM、FROZEN_SIMPLE、RESPONSE_MODEL、S_LEARNER、T_LEARNER。前两者直接应用旧冻结规则；简单规则将原RESPONSE/INCREMENTAL同名单合并为一套。模型分数降序，所有策略并列沿用SHA256(`target-v1|20260921|`+row_id)升序，完整hash碰撞再按row_id。名单先生成并核对容量，然后读取valid两臂和conversion评价；不按臂配额、不删除未购买者。

G=10000×(K/N_valid)×(p1_S−p0_S)，仍称每万候选记录的容量标准化组间差额。三个模型各相对FROZEN_SIMPLE为预声明主要开发比较，相对RANDOM只作背景。按原treatment臂、记录单位、完整五策联合选中bitmask×conversion计数做多项式bootstrap，复用TARGET实现；PCG64 seed20260923、1,000次、linear经验95%区间，固定名单和原实际容量。空分母不补零，原成功/失败单元<10标稀疏；不隐藏负差或失败。这些边际开发区间不对“挑中最大者”提供统一95%保证，也不包含学习过程不确定性。

旧valid对账要求RANDOM/简单规则的名单、两臂计数和G不变。本轮五策联合重抽的种子及联合类型与TARGET-01不同，区间不要求逐字相同。保存各模型与简单规则、响应与S/T的交集人数/K；不把名单差异本身当进步。不新增Qini、十档效果、全覆盖曲线或特征解释。

## 环境、资源和选择纪律

使用现有Python3.11/macOS arm64；预检最新1.9.1会新增narwhals/cloudpickle，选择支持显式早停的稳定1.8.0官方wheel及joblib1.5.3/threadpoolctl3.7.0，NumPy/SciPy等既有版本保持。以安装后真实freeze更新锁，pip check通过；签名与人工调用共同确认X_val/y_val生效。参考[官方1.8接口](https://scikit-learn.org/1.8/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)，不是仅凭文档假定。

最多4个计算线程，单阶段子进程依次执行，分批预测与memmap避免Python大列表。每2秒抽查进程树RSS，达到7.5 GiB即停止，为8 GiB目标留余量；当RSS>6 GiB且连续3次采样系统Swapouts增加时停止并记录，不能把系统级交换计数冒充进程专属值。新增产物≤15 GiB（含安装增量余量），空闲≥150 GiB。RSS采样高水位不是瞬时峰值；另记录系统提供的子进程最大RSS，不申请管理员权限。

真实模型及预测只存`.local/e1/`，只加载本次自建且SHA匹配的模型。错误保留失败证据，不为更好结果重训；确需修复先记录影响及已看到的结果。若资源不够，停止而不删减正式train。原raw、membership、TARGET结果与POWER/COST不修改，不启动Spark/云。

所有模型按实际完成与结果分别报告。若无清楚的额外价值，保留简单方案；若有，最多保留一个开发候选，仍需单独讨论后续评价性质。TARGET-02已经使用过原test，本轮不是新独立留出评价，不自动开展E2/E3、CUPED或继续调参；T7.3/G2本人待验。
