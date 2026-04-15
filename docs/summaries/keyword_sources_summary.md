# Language Data Catalog

## Directory Layout (2026-04-06)

```
data/raw/
├── de/
│   └── DE/
│       ├── H88_DE_ABA_Merged.csv
│       ├── H88_DE_出单词表.csv
│       ├── T70M_DE_ABA关键词表_数据表.csv
│       ├── T70M_DE_出单词表_数据表.csv
│       └── de_longtail_template_keywords.csv   # ← 新增长尾模板词库 (403 行)
├── fr/
│   └── FR/
│       ├── H88_FR_ABA.csv
│       ├── H88_FR_出单词.xlsx                 # 仍需 pandas/openpyxl 解析
│       ├── T70M_FR_ABA关键词表_数据表.csv
│       ├── T70M_FR_出单词表_数据表.csv
│       └── fr_longtail_template_keywords.csv   # ← 新增长尾模板词库 (406 行)
└── shared/
    └── H88_全维度表格_评论未合并.csv
```

> `H88_FR_出单词.xlsx` 仍为 Excel 格式，如需解析请在本地安装 `pandas` 或 `openpyxl`。

---

## DE / 德国数据源

| # | 文件 | 行数 | 关键字段 | 说明 |
|---|---|---|---|---|
| 1 | `data/raw/de/DE/H88_DE_ABA_Merged.csv` | 49 | `关键词`、`月搜索量`、`PPC 价格`、`SPR` | H88 ABA 合并数据，含高搜索量+PPC 信息 |
| 2 | `data/raw/de/DE/H88_DE_出单词表.csv` | 46 | `关键词`、`标签`、`AC推荐词`、`购买率` | H88 出单词表，带 AC 推荐词与转化率 |
| 3 | `data/raw/de/DE/T70M_DE_ABA关键词表_数据表.csv` | 30 | `关键词`、`月搜索量`、`PPC价格`、`SPR` | T70M ABA 词表 |
| 4 | `data/raw/de/DE/T70M_DE_出单词表_数据表.csv` | 22 | `关键词`、`AC推荐词`、`购买率`、`SPR` | T70M 出单词表 |
| 5 | `data/raw/de/DE/de_longtail_template_keywords.csv` | 403 | `keyword`、`cluster_type`、`searches`、`bid`、`notes` | **新增模板词库**，覆盖 core/feature/scenario/adjacent 多类长尾表达，含简易流量/竞价字段，供 L3 词槽或冷启动模板调用 |

---

## FR / 法国数据源

| # | 文件 | 行数 | 关键字段 | 说明 |
|---|---|---|---|---|
| 6 | `data/raw/fr/FR/H88_FR_ABA.csv` | 72 | `关键词`、`月搜索量`、`PPC价格`、`SPR` | H88 ABA 词表 |
| 7 | `data/raw/fr/FR/H88_FR_出单词.xlsx` | — | `关键词`、`购买率`、`AC推荐词` | 需 Excel 解析，尚无法在 sandbox 直接载入 |
| 8 | `data/raw/fr/FR/T70M_FR_ABA关键词表_数据表.csv` | 67 | `关键词`、`月搜索量`、`PPC价格`、`关键词翻译` | T70M ABA 词表，附翻译列 |
| 9 | `data/raw/fr/FR/T70M_FR_出单词表_数据表.csv` | 24 | `关键词`、`标签`、`购买率`、`SPR` | T70M 出单词表 |
| 10 | `data/raw/fr/FR/fr_longtail_template_keywords.csv` | 406 | `keyword`、`cluster_type`、`root_word`、`searches`、`notes` | **新增模板词库**，含法语/法英混合长尾组合（feature/scenario/positioning），提供 `searches`、`purchase_rate`、`bid` 估值字段以便 Tiering |

---

## Shared / 跨站评论数据

| # | 文件 | 行数 | 说明 |
|---|---|---|---|
| 11 | `data/raw/shared/H88_全维度表格_评论未合并.csv` | 1772 | 跨国家评论/属性原文，`Country` 列可筛选 DE/FR；用于负面洞察、FAQ、痛点抽取 |

---

## 列名速查

| 列名 | 含义 |
|---|---|
| `keyword` / `关键词` | 搜索词本体 |
| `search_volume` / `月搜索量` / `searches` | 搜索流量（模板词库用 `searches`） |
| `purchase_rate` | 购买率（模板词库） |
| `bid` / `avg_cpc` | 建议竞价 |
| `cluster_type` | 模板词库的语义分类（core / feature / scenario / adjacent） |
| `root_word` | 模板词的核心词根，用于派生组合 |
| `tags` / `标签` | 语义标签或 AC 推荐标记 |
| `SPR` | 搜索量/购买比 |
| `AC推荐词` | Amazon Choice 推荐词 |
| `Country` / `国家` | 数据所属国家 |

---

## 数据可用性概览

| 国家 | ABA 行数 | 出单词行数 | 模板行数 | 备注 |
|---|---|---|---|---|
| DE | 49 (H88) + 30 (T70M) | 46 (H88) + 22 (T70M) | 403 | 模板词库用于补齐 L3 长尾，含 `cluster_type`/`notes` 方便自动挑选场景词 |
| FR | 72 (H88) + 67 (T70M) | 24 (T70M) + H88 xlsx* | 406 | `H88_FR_出单词.xlsx` 仍需 Excel 解析；模板词库提供法语/混合长尾 |
| Shared | — | — | — | 1772 条评论/属性行，为两国共用 |

`*` 需安装 `pandas` 或 `openpyxl` 后方可解析。

---

## 使用提示

- `tools/country_vocab.load_country_vocab` 现已直接读取 `data/raw/...` 路径，并会把 `de/fr_longtail_template_keywords.csv` 作为 `source_type="template"` 注入 `RealVocabData`，供 `keyword_utils.extract_tiered_keywords`、`writing_policy`、`copy_generation` 等模块提取 L3 长尾词。
- 模板词库中的 `cluster_type` + `root_word` 字段可用于在写作策略中快速定位 “feature / scenario / adjacency” 场景，`notes` 提供生成逻辑（如 `generated scenario long-tail`）方便排查。
