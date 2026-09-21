# 离线A/A统计契约 v1

`rees46-aa-method-v1`，2026-09-21，人工测试及真实分组前冻结。唯一输入为T5.1 `cohort-oct-01` / `rees46-pre-oct01-14-post-oct15-28-v1`。所有84,165人保留，不按返回、购买、金额筛人；原结果不变。主指标为post_converted均值，辅助为post_purchase_amount均值。无真实干预、效应注入、CUPED或功效分析。

## 分配、重复和SRM

实验ID严格为 `rees46-aa-v1-0001` 至 `rees46-aa-v1-0300`，全部保存，固定展示0001。payload是UTF-8编码的 `rees46-aa-assignment-v1|` + experiment_id + `|` + cohort_key。ID限定上述ASCII格式，键限定64位小写十六进制，分隔符无歧义；不trim、不转原用户编号。SHA256前8字节按big-endian无符号整数解释，小于2**63为A，其余B。目标50:50，无强制配平；不同ID不承诺完全正交。cohort_key仅本地，不是可公开的匿名数据。

SRM对全部分配人数做Pearson chi-square，统计量 `(n_A-n_B)^2/(n_A+n_B)`，df=1，SciPy chi2.sf求p；p<0.001标记，是项目质量选择。空样本返回状态。标记运行保留统计结果，但不宜直接用于业务决策，不换种子。

## 两项正式统计

统一方向B−A，双侧alpha=0.05，95%CI。输出n_A/n_B、mean_A/mean_B、difference、SE、CI、p、单位、方法及状态。返回者比例、每位买家金额与前后差不属于本轮指标。

购买率：p_g=k_g/n_g，d=p_B−p_A，`SE=sqrt(p_A(1-p_A)/n_A+p_B(1-p_B)/n_B)`；CI为`d±norm.ppf(.975)*SE`，双侧p=`2*norm.sf(abs(d/SE))`。检验及区间均使用未合并Wald大样本近似，不混用合并方差。每组成功/失败格数均≥10才输出推断；稀疏格、空组或零方差有明确状态，不裁剪区间。d×100为百分点，d×10000为每万人差额；d/p_A为相对变化（p_A=0时NULL）。T3.2同类SE作为公式参照，本轮使用精确正态分位数且新增p值，不改旧实现或结果。

金额：全部用户原单位金额（含结构性0），样本方差s_g²使用ddof=1；`SE²=s_A²/n_A+s_B²/n_B`；`df=SE⁴/[(s_A²/n_A)²/(n_A−1)+(s_B²/n_B)²/(n_B−1)]`。CI=`d±t.ppf(.975,df)*SE`，p=`2*t.sf(abs(d/SE),df)`。使用SciPy分布，不将正态区间冒充Welch-t；人工与[官方ttest_ind(equal_var=False)](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html)独立对照。n<2、非有限或总方差为0时明确返回不可推断，常量不会伪造显著结果。

金额先由Decimal精确转整数百分之一原单位，逐值及总和核对；转float64用于方差/SE，检查回转整数一致与浮点均值误差。不删高金额用户、不截尾。分配内整数和始终守恒；原Parquet不改写。现有金额完整性失效即停止，不用好金额子集替代全队列。

## ratio-of-sums：仅人工方法核验

每用户一对(X,Y)，r=sum(X)/sum(Y)；Y≥0，允许单用户Y=0，总和0返回zero_denominator。方差 `sample_var(X−rY)/(n*mean(Y)²)`，等价于包含协方差的`[s_X²+r²s_Y²−2r*s_XY]/(n*mean(Y)²)`。两独立组差为r_B−r_A，SE为两方差和开根，采用正态delta CI/p。有限、非空、n≥2和正总分母是必要条件，不声称所有数据都适用。

预设人工A：X=[0,1,2,1,3,2,4,2,3,5,4,6]、Y=[0,1,2,1,2,2,3,2,3,4,3,4]，重复10次；B：X=[0,2,2,2,3,3,4,3,4,5,5,6]、同Y，重复8次。分别按用户成对重抽样6000次，seed=20260921、PCG64，与分组哈希隔离；不独立抽X/Y。记录bootstrap差值SD、delta SE及相对差；将6000次按30批各200次计算SD，以批间SD/√30给出bootstrap SE估计的近似Monte Carlo标准误。MC误差与delta线性近似差异分开解释，不设“必须小于10%”的机械通过条件。

## 校准摘要与解释

每指标计划300次，逐次保存状态/失败原因。主表含全部可计算运行（包括SRM），另列通过SRM者辅助表，分母分别标明。p<.05按正/负差分列；误报比例Wilson 95%区间由[binomtest.proportion_ci(method='wilson')](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html)计算。差值中位数及2.5%/97.5%经验分位数使用NumPy linear插值；另报CI覆盖0、失败数和p值区间频数。5%目标分别讨论，不把两指标当600次独立试验；本轮不增加“任一显著”业务指标。

这些是共享固定历史结果、依靠不同哈希ID分配的Monte Carlo重复，不是300次独立线上实验。Wilson区间是该近似重复机制下的有限次数不确定性；不要求等于5%或区间覆盖5%。经验差值范围不是单次CI，更不是将来真实效应范围。原假设下误报概率也不等于显著结果为假的后验概率。实施正确与近似校准表现分别验收，不根据真实结果重选方法或ID。
