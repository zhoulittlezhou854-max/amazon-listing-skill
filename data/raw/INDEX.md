# raw/ INDEX

## 目的
存放原始输入数据，保持数据原样不可修改。

## 内容结构
```
raw/
├── INDEX.md (此文件)
├── de/               # 德国市场数据
├── fr/               # 法国市场数据
└── shared/           # 共享数据文件
```

## 目录说明
| 目录 | 说明 | 文件数量 | 数据来源 |
|------|------|----------|----------|
| de/ | 德国市场数据 | 多文件 | 德国Amazon数据 |
| fr/ | 法国市场数据 | 多文件 | 法国Amazon数据 |
| shared/ | 共享数据文件 | 1文件 | 跨市场数据 |

## 最新文件（2026-04-06）
| 国家 | 文件 | 用途 |
|------|------|------|
| DE | `de/DE/de_longtail_template_keywords.csv` | 新增的长尾模板词库，含 403 条 core/feature/scenario/adjacent 组合，补齐 L3 关键词槽 |
| FR | `fr/FR/fr_longtail_template_keywords.csv` | 新增的长尾模板词库，含 406 条法语/混合场景词，提供 `searches`、`purchase_rate`、`bid` 字段 |

## 数据规范
- 所有文件必须保持原始格式
- 不得修改原始数据内容
- 数据清洗应在 `processed/` 进行
- 大型文件应使用 `.gitignore` 排除

## 使用指南
1. 新原始数据放入对应国家目录
2. 跨市场数据放入 `shared/`
3. 记录数据来源和获取日期
4. 备份重要数据到 `archive/`

## 相关链接
- [data/INDEX.md](../INDEX.md): 数据目录总索引
- [processed/](../processed/): 处理后的数据

## 最后更新
2026-04-03: 初始创建
