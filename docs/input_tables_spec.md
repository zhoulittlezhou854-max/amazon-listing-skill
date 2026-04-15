# 输入表规范

## 四张必需表

### 1. attribute_table
- 文件格式：CSV
- 必填列：`Field_Name` `Value` `Source`
- 缺失处理：缺失时跳过该属性，不报错

### 2. keyword_table
- 文件格式：CSV
- 必填列：`keyword` `search_volume` `tier`
- 缺失处理：缺失时使用 ABA 数据兜底

### 3. review_table（竞品多维表）
- 文件格式：CSV
- 必填列：`ASIN` `Bullet_1`~`Bullet_5` `BSR_Rank` `ASIN_Role`
- 缺失处理：缺失时 benchmark 使用默认范本

### 4. aba_merged
- 文件格式：CSV
- 必填列：`keyword` `search_volume` `click_share`
- 缺失处理：缺失时关键词分层降级为 L2/L3
