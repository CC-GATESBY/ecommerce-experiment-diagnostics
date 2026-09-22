# TARGET-01 验收与方法说明

本轮是Criteo corrected v2.1 train/valid上的固定简单规则开发评价。只使用f0/f1、原treatment和conversion，不读取test子群效果，不训练复杂模型。来源/身份/划分复用T0.4、T3.1，旧原始文件、membership、ATE、REES46及PRICE-01不改。

## 执行前固定

[配置](../config/targeting.json)在人工测试和真实读取前写入。规则版本criteo-targeting-rules-v1；f0/f1为预指定匿名变量，没有业务语义。train有限DOUBLE值使用DuckDB quantile_cont的Hyndman–Fan type 7精确25%/50%/75%分位点，重复点合并、等于最小/最大值的点去掉；右闭边界、尾档开至无穷。常量退化为一个档，两变量交叉最多16档。

每档train两臂均≥5,000才使用自身p0和delta；否则回退到train全体分数，不删人，不以购买次数或显著性决定采用。训练分数以整数计数的Fraction作精确排序，相等分数共享名次，避免浮点误差拆开真正并列。train未出现的交叉组合预建回退档，valid不重学边界或分数。

RANDOM按SHA256(UTF8("target-v1|20260921|"+row_id))升序；RESPONSE按p0_train降序；INCREMENTAL按delta_train降序。后两者并列用同一哈希；若完整哈希碰撞，再按row_id字符串排序。排序表达式无treatment/conversion。原row_id不公开，匿名特征不解释成收入、价格敏感或购物车用户。

容量10%/20%/30%/50%/100%，每个K=floor(c*N_valid)。唯一主比较是30% INCREMENTAL−RANDOM的G差，其余全是辅助。分数/边界/支持/排序及代码指纹在查询valid效果前保存为frozen_rules；本轮之后若基于valid改方案，应承认valid已参与开发，最终test须后续另行授权。

## 统计与单位

选中两臂各保留原始记录，以conversion数量/对应臂全部选中记录为p0_S/p1_S；delta=p1_S−p0_S。delta_pp=100delta；每万选中记录差额=10000delta；每万候选记录的容量标准化量G=10000*(K/N_valid)*delta。它不是实际新增购买预测、原广告主策略价值或优惠券ROI。

固定PCG64 seed=20260921、1,000次；以记录为单位、按原treatment两臂分别有放回抽样，臂总N保持。将全部15个规则×容量的联合选中bitmask与treatment、conversion交叉，按完整联合类型计数作多项式抽样；一次抽样供所有规则和策略差共用，保留重叠相关性。仅保存小型计数/重复汇总，不产生1000×数百万矩阵。

训练规则和valid名单固定，G使用原c_actual；不在重抽中重训或重选。95%区间为NumPy linear经验2.5%/97.5%分位数。分母0返回不可计算，不加小数；相应无效重复不补零。任何原选中臂成功或失败<10时保留点估计并标稀疏，不作强推断；全0区间不证明无风险。100%三名单一样，差及成对区间必须严格为0。

分层表另提供train和valid两臂n、conversion、率、差；复用既有两比例非合并Wald区间，最小成功/失败格<10不输出区间。分层及辅助策略区间为边际描述，无多重比较校正、不声称同时95%覆盖，不据“一个显著另一个不显著”判策略不同，不逐格识别“高增量人群”。主比较也仅支持本固定规则的valid条件评价。

公开非均匀抽样不恢复原广告主incrementality，不以0.85作已知分配概率，不做该比例的SRM/IPW。相同人数不等于相同真实预算；仅在每覆盖记录增量处理成本相同假设下才是同成本情景。广告曝光/点击计费与券兑付成本不同，不迁移为REES46发券名单。

## 实际运行与test边界

TARGET-01 **done（train/valid开发评价，本人解释未代验）**；T3.3完成有限f0/f1描述分层，复用本专题代码和报告，不另建同义模块。交付日期2026-09-22；run_id=`targeting-valid-01`，一次规则学习及valid评价成功，无换特征、分位/支持门槛、容量、seed或结果变量。起点private/main `9eaa397d7b4f75dfb30a646985c73a3592ad8f96`，工作区干净，根目录末尾U+0020保留。

来源绑定调用原`uplift.ingest_criteo.bind_source`：核对corrected源/收据/只读权限/bytes/header/完整SHA。CSV为3,248,115,221 bytes，SHA `e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef`。原membership gzip为576,697,968 bytes，压缩SHA和未压缩逻辑SHA分别与T3.1完全一致；原seed20260917不变。

此前无已验收train/valid特征缓存，仅raw、membership和总体汇总。一次标准库严格CSV语义扫描全部13,979,592条，与gzip的连续ordinal、row_id公式、原treatment及原split哈希逐条一致；引号内换行不计新ordinal。不使用DuckDB扫描顺序造身份。生成仅六列的11,185,035条train/valid TSV，再以显式schema装入本地DuckDB，原数据和membership不改。

train=8,387,273（control 1,257,688 / treatment 7,129,585）；valid=2,797,762（419,883 / 2,377,879）。另外2,794,557条test只核对结构/序号/成员身份及所属臂数量；本轮没有聚合test conversion，也不持久化它的特征/结果。CSV解析瞬时经过全部字段字节，源码身份前后完整哈希又读取全文件，**不是物理层未读取test，也不是只扫描train/valid字节**。文件前后SHA、大小和mtime都一致。旧QC与全量ATE已查看过，本轮没有重跑ATE或利用test分层学习。

训练边界先写入[冻结文件](../reports/targeting/frozen_rules.json)，其SHA `3fae3c428d96aa607ed43d13996b2f0db08a34373334c082208bb9b4baebe5a2` 在valid评价前后相同。f0的25%分位点12.616364906986497等于最小值而删除，保留50%/75%点21.923943332541803 / 24.436236184073156。f1三个分位点同为最小值10.059654474774547，全部去掉；train有55个不同f1值，不能写成常量。最终3档均两臂支持足够，fallback人数0。valid不会重新分位。

训练分箱/分数不使用valid结果，名单先由冻结分数与哈希定义，之后才汇总valid conversion。valid两臂conversion 837/7,424与原划分QC对上。RANDOM、RESPONSE、INCREMENTAL共15组容量结果，15组策略差；52个完整联合类型足以重建全部结果。所有分母有效、所有bootstrap各1,000次有效；没有稀疏区间状态（选中两臂成功/失败均≥10）。另保留6行train/valid分层及其边际区间。

## expected / actual / pass

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 原身份、唯一划分 | 全部ordinal及原row_id/split吻合；逻辑SHA相同 | 13,979,592条逐一吻合；gzip/逻辑摘要通过 | pass |
| train/valid缓存 | 原split两臂N，只有六列、无test记录 | 11,185,035条；四臂计数精确一致；test=0 | pass |
| 真实valid记录唯一 | 2,797,762条不同row_id | 精确相同 | pass |
| 规则不依赖valid结果或treatment | 人工更改两者后规则/完整排序不变 | 完全相同；hash并列顺序与独立hash预期一致 | pass |
| 基础概率≠必然高增量 | 人工p0=.5组delta=.05，p0=.1组delta=.4 | 两规则排序相反 | pass |
| 重复点/常量/回退 | 合并边界，常量一档，未见组合/低支持保留全体 | 独立字面预期通过 | pass |
| 容量与嵌套 | floor(cN)，同容量三规则同人数，小容量包含于大容量 | 279,776 / 559,552 / 839,328 / 1,398,881 / 2,797,762；完整名次1至N且唯一 | pass |
| 原valid QC | control/treatment conversion 837/7,424 | 精确相同，不使用QC调规则 | pass |
| 联合bootstrap | 与逐记录两臂重抽的均值、协方差分布相符 | 人工各6,000次、不同算法/seed，差异在6倍估计Monte Carlo SE内；未要求逐次相同 | pass |
| 空臂/负增量/稀疏 | 不补小数、不截负值、不把全0区间当安全 | 人工点估计−1保留；空臂G=null、有效重复0；稀疏标记 | pass |
| 100%相同策略 | 差与成对区间全为精确0 | 三对比较全部0/[0,0] | pass |
| 真实RESPONSE/INCREMENTAL | 训练三组顺序相同应得到同名单 | 全valid名次差异0；各容量重叠=入选N | pass |
| 独立算术/计数 | 直接SQL对选中集合聚合，Fraction重算G及策略差 | 15组计数精确相同，数值差<1e−12 | pass |
| 输入及冻结规则不改 | raw/membership、配置及冻结边界前后相同 | 指纹和元数据一致；旧跟踪文件仅授权导航/状态修改 | pass |

5个人工测试方法通过（覆盖结构、分箱/回退、选择隔离、重抽分布与统计边界）；44项真实运行断言和49项独立小汇总复核通过。独立复核只读本轮已缓存的train/valid及小表，不再次扫描源文件，不重做划分。人工6,000次用于两种重抽实现的分布/矩比较，是数值方法测试，不是线上实验或策略功效曲线。

## 资源、复跑与范围

Python3.11.15，DuckDB1.5.5，NumPy2.4.6，既有SciPy1.17.1；无安装、锁文件或主环境改动。DuckDB4线程/2GB内存限额，临时目录上限3GB；本轮输出总预算8GiB、最低空闲150GiB。采样新产物高水位1,825,760,884 bytes（约1.7004GiB），最低空闲541,611,229,184 bytes（约504.4148GiB）。这是检查点采样，非连续峰值测量；峰值内存not_measured。TSV为1,260,777,670 bytes，数据库564,932,608 bytes，明细/ID/标签/日志均被忽略且不提交。

成功入口连续计时131.696秒，其中严格CSV与membership对齐约116.800秒；此计时含身份核验、缓存、分组、规则/全部valid评价及校验，不是受控性能基准。未启动Spark、云或新服务，未训练S/T/X-learner、森林或神经网络。用表替代图，没有为绘图安装工具。

```sh
.venv/bin/python -m unittest tests.test_targeting -v
.venv/bin/python -m uplift.targeting --run-id targeting-valid-01
```

第二条是已完成的历史命令；同ID重跑拒绝覆盖，不应为调参重复真实评价。入口仅写`.local/target01`，核验后才逐文件发布脱敏表和冻结规则。`--resume-cache`仅限已有完整缓存、无冻结规则且无完成收据的早期失败，不用于重排或重复查看valid；本次未使用。

最重要的未完成项是当前冻结方案的独立test评价与真实目标干预/成本证据，本轮均未执行。T3.3有限描述分层与TARGET-01开发评价可以完成，不代表E1复杂建模、E2最终test、G2或本人理解验收通过。本人应解释：同容量和同成本为何不同；相同名单的零策略差为何不是普遍等价证明；联合bootstrap为何必须保留跨策略重叠。
