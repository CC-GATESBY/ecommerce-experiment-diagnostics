# Criteo 稳定身份与封存划分清单

状态：T3.1 done（工程验收，本人解释未代验）；run `criteo-split-v1-01`。唯一corrected v2.1源含13,979,592条；source_id `criteo_uplift_v2_1_corrected`。原T0.4 manifest/registry及raw未改。

契约见 [criteo_split_contract.md](../docs/criteo_split_contract.md)，机器清单见 [criteo_split_manifest.json](../data/criteo_split_manifest.json)。row_id由源SHA和从0开始的逻辑ordinal生成；重复内容不合并。seed固定20260917，两个arm各自以整数hash阈值按60/20/20概率划分；不强制精确比例、不重新分配treatment。

| treatment | split | n | 组内占比 | conversion rate | visit rate | exposure rate |
|---|---|---:|---:|---:|---:|---:|
| all | train | 8,387,273 | 59.996551% | 0.002909765784 | 0.046974147616 | 0.030586580406 |
| all | valid | 2,797,762 | 20.013188% | 0.002952717208 | 0.046983982197 | 0.030620545994 |
| all | test | 2,794,557 | 19.990262% | 0.002901354311 | 0.047053611717 | 0.030775897575 |
| 0 | train | 1,257,688 | 59.977386% | 0.001918599844 | 0.038311568529 | 0.000000000000 |
| 0 | valid | 419,883 | 20.023634% | 0.001993412451 | 0.037755755770 | 0.000000000000 |
| 0 | test | 419,366 | 19.998979% | 0.001938640710 | 0.038314980232 | 0.000000000000 |
| 1 | train | 7,129,585 | 59.999933% | 0.003084611517 | 0.048502262053 | 0.035982178486 |
| 1 | valid | 2,377,879 | 20.011344% | 0.003122110082 | 0.048613491267 | 0.036027484998 |
| 1 | test | 2,375,191 | 19.988723% | 0.003071331948 | 0.048596512870 | 0.036209719555 |

all的占比分母为完整文件；0/1为各arm记录数。三个rate为对应分组1标签数/该组n，未比较处理效果。**label rates are predeclared split-QC summaries, not split optimization targets.** 完整精度与分子见 [CSV](criteo_split_summary.csv)。

守恒：train+valid+test=13,979,592；treatment=0合计2,096,937，treatment=1合计11,882,655。source conversion=40,774，visit=656,929，exposure=428,212，与T0.4一致。0.85仅是公开文件观测/舍入参考，不做原实验SRM声明。

| 摘要对象 | SHA256 |
|---|---|
| 全membership逻辑TSV（含header） | `cd2be515cf162a69e3483a3c353186f52f2d9da7fdcdc4c41830b741dd410cb2` |
| gzip | `a03f1ba4e8a1465dd0998f295e1a190e2e61d25e82c605f340af5bbc7549e7e1` |
| row_id序列 train | `162949a23b198404a702f7d2b1e554e4f8b006e285737d3c9a0930c4f750ab50` |
| row_id序列 valid | `5acfe20ce5efabf2037077a05ce835d74b3f9763b7551059c1f05956f2f41a39` |
| row_id序列 test | `f6e5709a08cf998a8284de6043949e12cdf1b27ed7867a86b79281bb0caffb9b` |
| row_id序列 0/train | `8764b041cbc634374a0cd9e244a987669a9b266e182764e75784ffd33d09ff53` |
| row_id序列 0/valid | `d06b88a6e81f6456276e1bf34067ae226a6be41e422777e6891040b6b2906818` |
| row_id序列 0/test | `c6d69c1e004a469d5f84e31eb15944c14d695b6818326e9aba74ed73f1e3884e` |
| row_id序列 1/train | `e63c4bf753a3653cd1be57f3c80b7a347b186239b9ef69b3ed61c52ce2422031` |
| row_id序列 1/valid | `bf4e0aae6f5bf7a978f340753764199d4501f751f0011cc8d95795c883c876d3` |
| row_id序列 1/test | `d16e37e91ae4ccf5335d601ae53853fb8411ff50f2ac0b0d934f7ea904c09c50` |

逻辑字节1,132,420,922仅流式计算，没有落地未压缩副本；实际gzip为576,697,968 bytes。序列SHA按源ordinal排列的`row_id + LF`逐条更新，不含header。gzip固定mtime=0、level=6、空文件名，当前Python/zlib环境下人工跨进程字节复现通过。

train用于以后获授权的训练/探索；valid用于选择；test封存为预定最终评价。T3.2全量总体aggregate evaluation是预先声明例外，不能据test切片表现选T3.3变量或调模型。seal不删除raw标签、不声称本机用户无法读取。

失败留痕：两套全量核验通过后，初次目录发布因提前设只读而失败。修正发布顺序、补测试、重核同一产物指纹后发布，没有重划、复制membership或更改seed。详细检查与资源见 [T3.1验收](../docs/t31_validation.md)。T3.2–T3.4未执行，总G0/G1不自动勾选。
