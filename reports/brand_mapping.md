# 冻结品牌映射说明

指标版本 `rees46-metrics-v1`，scope `rees46_2019_oct_user5_fedd938409b5f836_20260916_v1`，来源run `month-v101-01`。规则 `rees46-brand-oct01-07-top200-v1`；参考期 2019-10-01 至 10-07 UTC，非缺失原品牌按合格事件数降序、原字符串 UTF-8 二进制升序排序。实际入选200，最多200；没有因后续结果重新排名。

有序映射内容 SHA256：`0269eb8ba2f91b9adca762f41a8a82707edc2e774f3edcfd167d1f9a885a407b`。内容为按brand_rank升序的映射行（原brand、reference_events、brand_rank、dim_value_key、dim_value_label），以UTF-8、JSON sort_keys=True、ensure_ascii=False、separators=(逗号,冒号)编码后哈希；指纹不是Parquet物理文件哈希。实际映射JSON与Parquet写后读回一致，仅保存在本地运行目录。

入选品牌键 `brand:<原字符串>`，其余非缺失品牌（包括参考期后新品牌）为 `bucket:other`，缺失为 `bucket:unknown`，显示标签独立。真实名称unknown/other不与保留桶冲突，不trim或改大小写。不把10月1–7日建立的映射称作事前线上映射；10月8日后完全使用冻结映射。

本文件不包含真实用户/session或品牌映射明细。未知品牌事件299,547条，其中购买2,841条、观测购买金额412669.39；保留在unknown桶。全部验收及局限见 [T1.3验收](../docs/t13_validation.md)。
