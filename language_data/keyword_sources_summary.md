# Language Data Catalog

## Directory Structure

```
language_data/
├── DE/
│   ├── H88_DE_ABA_Merged.csv
│   ├── H88_DE_出单词表.csv
│   ├── T70M_DE_ABA关键词表_数据表.csv
│   └── T70M_DE_出单词表_数据表.csv
├── FR/
│   ├── H88_FR_ABA.csv
│   ├── H88_FR_出单词.xlsx        ← 无法读取（缺少 openpyxl/pandas）
│   ├── T70M_FR_ABA关键词表_数据表.csv
│   └── T70M_FR_出单词表_数据表.csv
└── H88_全维度表格_评论未合并.csv
```

> 注：`H88_FR_出单词.xlsx` 为 Excel 格式，当前环境未安装 openpyxl/pandas，无法解析。

---

## DE / 德国

### 1. DE/H88_DE_ABA_Merged.csv

| Field | Value |
|---|---|
| 行数 | 49 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `型号` |
| 关键列 | `关键词`、`月搜索量`、`PPC 价格`、`建议竞价范围`、`SPR`、`标题密度`、`点击集中度`、`转化集中度` |
| 说明 | ABA 合并数据，含搜索量和PPC信息 |

### 2. DE/H88_DE_出单词表.csv

| Field | Value |
|---|---|
| 行数 | 46 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `国家`、`型号` |
| 关键列 | `关键词`、`标签`、`AC推荐词`、`月搜索量`、`购买率`、`SPR`、`标题密度`、`商品数`、`评分值` |
| 说明 | 出单词表，含AC推荐词和转化率数据 |

### 3. DE/T70M_DE_ABA关键词表_数据表.csv

| Field | Value |
|---|---|
| 行数 | 30 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `国家`、`型号` |
| 关键列 | `关键词`、`月搜索量`、`PPC价格`、`SPR`、`标题密度`、`点击集中度`、`转化集中度` |
| 说明 | T70M产品的ABA关键词表 |

### 4. DE/T70M_DE_出单词表_数据表.csv

| Field | Value |
|---|---|
| 行数 | 22 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `国家`、`型号` |
| 关键列 | `关键词`、`AC推荐词`、`月搜索量`、`购买率`、`SPR`、`标题密度`、`商品数`、`评分值` |
| 说明 | T70M产品的出单词表 |

---

## FR / 法国

### 5. FR/H88_FR_ABA.csv

| Field | Value |
|---|---|
| 行数 | 72 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `型号` |
| 关键列 | `关键词`、`月搜索量`、`PPC价格`、`SPR`、`标题密度`、`点击集中度`、`转化集中度` |
| 说明 | H88法国ABA数据，搜索量最大（72行） |

### 6. FR/H88_FR_出单词.xlsx

| Field | Value |
|---|---|
| 行数 | 无法读取 |
| 说明 | Excel格式，缺少 openpyxl/pandas，无法解析 |

### 7. FR/T70M_FR_ABA关键词表_数据表.csv

| Field | Value |
|---|---|
| 行数 | 67 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `国家`、`型号` |
| 关键列 | `关键词`、`月搜索量`、`PPC价格`、`SPR`、`标题密度`、`点击集中度`、`转化集中度`、`关键词翻译` |
| 说明 | T70M法国ABA关键词表，含翻译字段 |

### 8. FR/T70M_FR_出单词表_数据表.csv

| Field | Value |
|---|---|
| 行数 | 24 |
| Keyword 列 | `关键词` |
| Country/Model 列 | `国家`、`型号` |
| 关键列 | `关键词`、`标签`、`AC推荐词`、`月搜索量`、`购买率`、`SPR`、`标题密度`、`商品数`、`评分值` |
| 说明 | T70M法国出单词表 |

---

## 全维度表 / Cross-Country

### 9. H88_全维度表格_评论未合并.csv

| Field | Value |
|---|---|
| 行数 | 1772 |
| Keyword 列 | **无**（此为评论/属性数据，非词表） |
| Country 列 | `Country` |
| 关键列 | `ASIN`、`Country`、`Data_Type`、`Field_Name`、`Content_Text` |
| 说明 | 跨国家的全维度数据，含多个国家的评论和属性文本。Country 字段可区分 DE/FR 等国家数据 |

---

## 列名速查对照

| 列名 | 含义 |
|---|---|
| `关键词` | 搜索关键词（主要） |
| `关键词翻译` | 关键词的翻译（仅部分DE/FR表有） |
| `月搜索量` | 月搜索量 |
| `购买率` | 转化购买率 |
| `SPR` | 搜索量与购买比 |
| `标题密度` | 标题中关键词密度 |
| `PPC价格` / `PPC竞价` | PPC竞价 |
| `AC推荐词` | Amazon Choice 推荐词 |
| `型号` | 产品型号（DE/FR 各自独立型号） |
| `国家` | 国家代码（出现在全维度表及部分出单词表） |
| `Country` | 国家（出现在全维度表） |
| `Data_Type` | 数据类型（review/attribute等） |
| `Field_Name` | 字段名 |
| `Content_Text` | 文本内容 |

---

## 数据可用性总结

| 产品 | 国家 | ABA词表 | 出单词表 | 合计行数 |
|---|---|---|---|---|
| H88 | DE | 49 | 46 | 95 |
| H88 | FR | 72 | (xlsx无法读) | ≥72 |
| T70M | DE | 30 | 22 | 52 |
| T70M | FR | 67 | 24 | 91 |
| H88 | 全维度 | — | — | 1772（评论/属性） |

**可立即用于关键词提取的文件（keyword列存在）：**
- DE: 4个文件全部可用，共 **147** 行关键词
- FR: 3个CSV可用（xlsx不可读），共 **163+** 行关键词
- 全维度表为评论/属性数据，非词表
