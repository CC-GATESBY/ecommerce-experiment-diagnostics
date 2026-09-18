# 10–11月固定用户样本：来源、范围及比较规则

本轮用户授权新增同一REES46多品类商店2019-Nov文件；原十月scope、事实、指标、T4案例和收据保持原样。新analysis_scope为`rees46_oct_nov_user5_analysis_v1`，观察区间`[2019-10-01,2019-12-01)` UTC，主口径`baseline_keep_all`。授权不是全平台/全用户分析，也不批准后续月份。

## 官方来源与版本边界

2026-09-18实际访问[REES46原发布页](https://rees46.com/en/datasets)，其Multi-category条目指向[原作者Kaggle目录](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)。官方API当前目录版本8，说明Oct and Nov；该目录说明明确提供[2019-Nov.csv.gz原发布方链接](https://data.rees46.com/datasets/marketplace/2019-Nov.csv.gz)。没有使用其他商店或第三方重传。

HEAD返回200，Content-Length=2,890,421,023 bytes，ETag=`"646b57e5-ac48531f"`，Last-Modified=`Mon, 22 May 2023 11:54:13 GMT`。Kaggle文件元数据的CSV字节数为9,006,762,395。网页2.69Gb是近似文字，HTTP长度是远端对象元数据，本机下载/解压和全文件扫描另有实测；三者不混用。外链对象没有独立版本号或发布方SHA签名，目录v8只是上下文，不声称外链已与Kaggle文件逐字节比对。

许可官方标签仍为`Data files © Original Authors`；发布说明允许免费用于作品、书籍和教育材料，要求注明Kaggle来源和[REES46](https://rees46.com)。不改称CC0，raw和用户样本仅保留本地，不再分发。当前说明里“Only one kind of event: purchase”与同页的多行为枚举不一致，事件类型以实际完整扫描为准，不照抄为实测。

只下载一份11月gzip，不重下十月、不取12月；gzip完整读到EOF核验CRC，CSV与gzip按SHA建立父子关系。独立登记见`reports/cross_period/source_manifest.json`，不追加到绑定旧证据的`data/manifest.json`。SHA用于内容追踪，不是真实性签名。

## 抽样与计算

直接复用`rees46-user-sample-v1|20260916|`+原始user_id的UTF-8 SHA256，前64位整数小于`(5*2**64)//100`入选。月份、日期、结果不进入哈希；没有十月ID白名单，11月新出现且符合规则的ID自然入选。保留所有选中记录、原始字符串和顺序，空/纯空白ID单独计数。5%是目标用户概率，不是事件比例，也不把金额乘20当全平台真值。

解析复用T1.4已核验的`sql/validation/parse.sql`，契约仍为`rees46-events-v1.0.1`、Decimal(18,2)、UTC；标准库oracle独立流式生成预期，以双向EXCEPT ALL核对原九字段、全部派生字段/标记及重复重数。新品格式/ID失败先停止，不静默扩展契约。日期规则调用原`rees46-date-quality-v1`：计数与金额分开放行。

只持久化必要的11月解析/用户日工作表及小型日、品类日结果；复用`rees46-metrics-v1`的计数、金额和category完整字符串规则。没有品牌排名、first_seen、漏斗、实验、Criteo或商品细切片。DuckDB在既有环境运行，内存2GB、线程4，临时空间上限12GiB；是资源限制，不是实测峰值。旧十月通过原canonical快照选择器、原独立核验和已审查manifest兼容读取两个小表。

## 读取11月业务结果前固定

配置`config/cross_period.yaml`已在11月来源扫描结束、指标计算前冻结；本地保存其副本和指纹。原T4过去7/14/21/28日、至少3个合格点、median/MAD/1.4826、|score|>3且相对变化至少10%的规则不变。缺日、阻断、零基线、MAD=0保留明确状态，不补0、不加极小数。每个日期只使用过去历史；10月25日仍只用10月4/11/18，11月只是后续观察。

固定展示全部61日、10月4日起全部9个周五、11月全部30个日期；不按结果剔除日期。品类只重点看electronics、computers及解释覆盖所必需的unknown。自身变化用同一组历史日期的品类日均金额；大盘变化也用该组日期的总体日均金额，两者相减为相对大盘变化的百分点差。它与median检测差不同；贡献大不等于相对表现差，更不等于根因。月度使用31/30日的日均，不直接比较不等天数的月总额。品类份额与覆盖使用可加总金额/计数合计为分母，不平均日比率。

所有新增物理产物和临时文件累计不超过40GiB，下载载荷不超过4GiB，保留至少150GiB；预算检查失败停止并保留未完成记录。原文件不覆盖，重复source执行按内容核对复用；样本和计算run排他创建。
