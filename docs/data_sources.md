# 数据来源与本轮使用范围

核对日期：2026-09-16。本页保留首次获取的来源与成本记录；随后完整源扫描及固定用户候选的新增实测见 [整月输入验收](t04_rees46_month_validation.md)。仅处理 REES46 多品类商店 2019 年 10 月。Criteo 来源验收尚未开始；没有获取其他月份，也不据此宣称整个 T0.4 完成。

## 发布链与条款

[REES46 原发布入口](https://rees46.com/en/datasets)的 Multi-category / Behavior events 条目链接到 [Michael Kechinov 的 Kaggle 数据集](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)。数据集标识为 `mkechinov/ecommerce-behavior-data-from-multi-category-store`，Kaggle ID 为 `411512`。

Kaggle 官方公共 API 的 [数据集元数据](https://www.kaggle.com/api/v1/datasets/view/mkechinov/ecommerce-behavior-data-from-multi-category-store)返回当前版本 **8**，版本说明为 Oct and Nov，创建时间为 `2019-12-09T20:43:39.273Z`。[文件列表](https://www.kaggle.com/api/v1/datasets/list/mkechinov/ecommerce-behavior-data-from-multi-category-store)包含指定的 `2019-Oct.csv`。页面介绍七个月的行为数据，而 Kaggle 当前版本的文件范围与外链文件范围应分别理解，不能以页面总体规模充当本次下载规模。

元数据中的许可名称是 **Data files © Original Authors**。发布说明允许免费用于作品、书籍和教育材料，并要求注明该 Kaggle 页面及 [REES46 Marketing Platform](https://rees46.com)。这不是经本项目验证的 CC0 或其他标准开放许可；本轮按该说明用于本地工程验证，GitHub 仅保留代码和脱敏元数据，不再分发原始记录或样本。

## 指定对象与大小依据

Kaggle 原作者的说明直接链接到 [REES46 自有域名上的 2019-Oct.csv.gz](https://data.rees46.com/datasets/marketplace/2019-Oct.csv.gz)。本轮选择这一原发布方对象，不使用第三方重新上传的数据。

| 信息 | 核对结果 | 证据类型 |
|---|---|---|
| 页面压缩大小文字 | `1.62Gb` | 发布者的近似标注，不作为精确测量 |
| 压缩对象大小 | 1,741,928,540 bytes | 原发布方 HEAD `Content-Length` |
| 压缩格式 | gzip 包装的 CSV；服务器 MIME 为 `application/octet-stream` | 文件名与 HTTP 元数据；完整 gzip 校验另见验收 |
| HTTP 内容编码 | 未设置 | 不经 HTTP 自动解压 |
| ETag | `"646b587b-67d3b85c"` | HTTP 对象指纹，不是发布方 SHA256 |
| Last-Modified | `Mon, 22 May 2023 11:56:43 GMT` | HTTP 元数据，不是事件时间或获取时间 |
| CSV 大小 | 5,668,612,855 bytes | Kaggle 文件 API 元数据；作为解压预期上限 |
| 压缩包与 CSV 的实测大小、SHA256 | 见 [清单](../data/manifest.json)及[验收](t04_rees46_validation.md) | 本机下载、解压和全字节哈希 |

**版本边界：** Kaggle 的目录版本 8 已核实，但 REES46 外链压缩对象没有提供独立版本号，也没有发布方 SHA256 可供比较。清单把它登记为 `publisher_unversioned_object; catalog_v8_context_only`，并保留 ETag、Last-Modified、获取时间及内容 SHA256。CSV 字节数与 Kaggle 元数据一致只能作为一致性线索，不能据此宣称外链与 Kaggle v8 文件经过逐字节比对。SHA256 用于以后识别同一内容，不冒充发布方真实性签名。

## 获取方式与成本

公共元数据和原发布方对象均可匿名访问；本轮未读取或使用 Kaggle 凭据，无需安装 Kaggle CLI。实际使用 Python 标准库 HTTPS 流式下载、gzip 解压和 CSV 解析，没有改变项目依赖锁。一次探测 Kaggle 单文件旧式 HEAD 路由返回 404，没有取得数据载荷；随后使用发布者明确列出的原始 gzip 链接。

预算为单个源文件下载不超过 8 GiB，新增磁盘不超过 25 GiB，下载与解压后至少保留 150 GiB 空闲。脚本先检查实际磁盘与服务器长度、ETag，并为两次不超过 64 MiB 的工程样本预留空间；本次计算上限为 7,544,759,123 bytes。传输只允许指定 HTTPS 对象，意外重定向、长度变化或磁盘余量不足都会停止。

取出 100,000 条样本仍须先传输完整压缩文件、解压完整 CSV；不能称为“只下载了 100,000 行”。下载载荷、解压字节数、样本字节数分别记账；HTTP/TLS 协议开销及元数据响应不等同于文件载荷，没有进行网卡总流量测量。

## 登记与样本边界

下载进入独立 staging，只有长度、SHA256、gzip CRC、解压大小及 CSV 表头验证成功才登记 raw。压缩包和 CSV 分开登记并相互引用哈希，raw 采用按哈希划分的只读文件路径。同一内容或改名同内容不增加输入条目，同名异内容直接报错；已有文件不覆盖。解压只允许指定目录中的 `2019-Oct.csv`，不信任 gzip 内嵌文件名。

样本是 CSV 解析器按源顺序取出的前至多 100,000 条**数据记录**，不含表头，不是随机样本。所有字段保持字符串值，保留空字段、重复候选及源顺序；CSV 引号和换行按固定 UTF-8/LF 格式重新序列化，没有业务过滤、去重、价格浮点转换或时间清洗。时间解析只计算样本覆盖范围和失败数量，不回写原值。

`engineering_sample` 仅用于后续获授权的工程调试。不能据此估计总体转化率、留存、长周期异动或 CUPED。首次获取阶段未进行完整 CSV 逐记录计数或全时间扫描，当时完整行数和时间范围为 `not_measured`；后续已授权补充扫描的实测另行登记，完整字节哈希与 gzip 校验本身仍不等于完整业务解析。
