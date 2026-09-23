# COST-01 人工成本与需求条件验收

2026-09-23；起点`05f68d6befd9a6fc8072e61fa21d0035751870d5`；run_id=`cost01-synthetic-01`，版本`cost01-fixed-fee-v1`。状态：**done（人工成本与需求条件分析；非真实利润或税务核定，本人解释未代验）**。仓库public/main；目录末尾空格保留。

输入仅为[冻结配置](../config/cost_scenarios.json)，所有数值为人工假设。仅读PRICE-01及购物车方案文档以保留边界；没有打开REES46/Criteo明细、事实、会话、路径、队列、membership或test，没有借用其购买率。未启动Spark/DuckDB、安装依赖、bootstrap或显著性检验；简历三条主项目及旧分析结果保持原样。

## 官方背景：有限核对，非完整税务规则验收

所有来源访问日期为**2026-09-23**。`policy_context=verified_limited`，`actual_goods_applicability=assumed_not_determined`；f=3仍是政策启发情景，不是实测完整税负。以下记录的是本次实际能核对的内容，不以旧版本推定掌握全部现行规则。

| 官方标题 / 入口 | 发布或版本日期 | 本次可支持的内容与限制 |
|---|---|---|
| [Ensuring fairness and safety: €3 customs duty for low-value parcels](https://commission.europa.eu/news-and-media/news/ensuring-fairness-and-safety-eur3-customs-duty-low-value-parcels-2026-06-29_en) | 2026-06-29 | 官方检索返回标题、日期及正文；直接打开返回HTTP 429。未把直连失败写成已完整抓取；类别而非件数的解释由下列可访问官方材料复核 |
| [Council gives final green light to new customs duty rules for small parcels](https://www.consilium.europa.eu/en/press/press-releases/2026/02/11/council-gives-final-green-light-to-new-customs-duty-rules-for-small-parcels/pdf/) | 发布2026-02-11；更新2026-02-12 | 临时€3按不同税则类别征收，2026-07-01至2028-07-01安排；不是每包固定收费，与处理费区分 |
| [EU Customs Reform](https://taxation-customs.ec.europa.eu/customs/eu-customs-reform_en) | 动态页；最新新闻标2026-09-21 | 当前页面保留低价值临时€3安排，并另述handling fee。本轮不计算处理费、不穷尽后续实施安排 |
| [Importation and Exportation of Low Value Consignments — The EUR 3 temporary customs duty](https://taxation-customs.ec.europa.eu/document/download/053e5b4e-f0be-4f20-9a23-3e3b659a6676_en?filename=Customs+Guidance+on+EUR+3+customs+duty.pdf) | 文件标Version of 2 June 2026；入口新闻2026-06-08 | 定义涉及税则分类、描述和按申报要求提供的来源；按申报项而非数量。内在价值≤150；6月原制度说明含IOSS/邮政范围，不能外推为所有真实货物均适用。只读有关章节，未穷尽各类例外 |
| [Questions & answers — EUR 3 customs duty guidance](https://taxation-customs.ec.europa.eu/document/download/8350b1aa-935a-4b80-a349-385b36292fbe_en?filename=Questions+and+answers+on+3+EUR+Guidance+MS+and+Economic+operators_clean15062026.pdf) | 文内版本2026-06-30；入口新闻2026-06-19 | 文内日期不同于链接文件名及入口首次发布日期，分开记录；不按旧文件名宣称最新完整规则已验收 |
| [VAT Rates](https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-rates_en) | 页面未标发布日期 | 欧盟框架下各成员国税率和适用类别有区别；本轮不选一个统一VAT率 |
| [Taxable amount](https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/taxable-amount_en) | 页面未标发布日期 | 进口计税金额可涉及关税及附加费用，不可把新增3H视为全部税负。VAT可抵扣性是模型假设，未验证实际企业资格 |

模型限定假设一票包裹、同一来源国且处于适用范围；H为给定收费类别，不由electronics/computers标签推定。S不是已核定海关内在价值。无错误归类、低报、拆包建议。原文解释性指导不能替代法规；本轮输出是经营情景附录。

## 计算与比较口径

- 标准库Decimal，50位有效精度；配置用十进制字符串。单篮子金额和五档r乘积均精确；循环小数门槛按50位输出，不截断到金额分位。空比例表示不适用，不是0。
- 27篮子、6方案：`synthetic_baskets.csv` 27行；`strategy_comparison.csv` 162行；双参照`demand_thresholds.csv` 324行。H、m和销售额交叉网格完整，没有按结果筛场景。
- 两个参照的p_ref相同且固定，r=1。四个改变价格/商品的行动各跑五档r；加上两个固定参照，每篮子22行，`demand_sensitivity.csv`共594行。不能一边把ABSORB定义为p_ref，一边在同一比较中下调其概率。双参照表中REFERENCE/ABSORB之间的比例只是算术门槛，不表示它们实际改变需求。
- r是概率之比，可大于1，负数/非有限值拒绝；主网格仅包含1/.95/.90/.80/.70。r>1门槛另列可行性上界p_ref≤1/r；p_ref未测，不宣称门槛一定能达到。主案例额外的0.75只执行用户预指定算术检查，不扩展网格或换主案例。
- 参照贡献非正时不做比例比较；策略贡献非正且参照正时明确标不能靠增加购买恢复正贡献。提价保持C0，增购同时增加商品/履约成本；不使用浮点金额、不生成真实利润排名。

## expected / actual / pass

| 检查 | expected | actual | 结果 |
|---|---|---|---|
| 主案例六贡献 | 8、2、5、8、4、1 | 完全一致 | pass |
| 全额转嫁双参照 | 对REFERENCE下降容忍0；对ABSORB为75% | 0 / 0.75 | pass |
| 主案例r=.75 | 贡献6；较ABSORB +4，较REFERENCE −2 | 完全一致 | pass |
| f=0及H差 | 不发生新增费用；固定收入成本下H+1贡献−f | f=0四个不增购方案均8；H+1少3 | pass |
| 商品/履约成本 | 提价C=28；增购C=35、L=5 | 完全一致 | pass |
| 非正贡献、非法输入 | 比例空并有状态；非法m/S/H/r拒绝 | 字面边界测试通过 | pass |
| 独立完整核对 | 全162方案、324门槛、594需求行 | 标准库Fraction独立公式一致；金额精确，门槛小数与分数误差<1e−48 | pass |
| 同配置跨进程 | 四CSV字节一致；已有目录拒绝覆盖 | 独立子进程一致且拒绝覆盖 | pass |
| 本人理解 | 独立解释两个参照、概率分母和真实成本缺口 | 未代验；T7.3/G2不勾选 | pending |

仅运行`tests.test_cost_scenarios`的12项直接相关人工测试，全部通过；未重跑历史任务。独立Fraction复核仅读本轮人工CSV，不调用生产计算函数。报告表格复读本轮CSV；不绘图、不引入其他环境。

## 复跑与产物边界

在实际项目根目录执行（路径末尾空格不得trim）：

```sh
.venv/bin/python -m unittest tests.test_cost_scenarios -v
.venv/bin/python scripts/cost_scenarios.py --config config/cost_scenarios.json --output-dir .local/cost01/replay
```

创建本地父目录`.local/cost01`后运行；`replay`必须不存在。首次正式人工输出使用`--output-dir reports/cost_analysis`，已有结果拒绝覆盖。复跑CSV可与提交的四CSV逐字节对照；不需要下载凭据、私有输入或额外依赖。Python实际3.11.15，纯标准库，原锁未改。

四CSV合计180,293 bytes，配置SHA256为`51b47d1d763caab9e8fd599c4e65a58795ed6aa4e6fd816b615abd428931181c`。本轮新增代码、文档、人工表和本地核验文件合计低于1 MiB，低于128 MiB预算；运行后磁盘可用约505.53 GiB。收据、文件指纹及原始运行输出只留`.local/cost01/`；耗时不是性能基准。仅公开代码、人工配置/汇总和文档，无真实用户或包裹数据。

未知项仍为真实商品适用范围、税费承担、净成本和各方案购买响应。建议只用于决定下一份取证材料，不能批准真实提价、增购、报关或预算。本轮停止，不进入新数据、政策模型或其他技术模块。
