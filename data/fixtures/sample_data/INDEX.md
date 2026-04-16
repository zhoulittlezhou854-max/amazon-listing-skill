# sample_data/ INDEX

## 目的
存放样例测试数据，用于功能演示和基础测试。

## 内容结构
```
sample_data/
├── INDEX.md (此文件)
├── aba_merged.csv          # 合并的ABA数据
├── attribute_table.txt     # 属性表
├── images/                 # 图片目录
├── keyword_table.csv       # 关键词表
└── review_table.csv        # 评论表
```

## 文件说明
| 文件 | 说明 | 大小 | 格式 |
|------|------|------|------|
| aba_merged.csv | 合并的ABA数据 | 171B | CSV |
| attribute_table.txt | 产品属性表 | 352B | 文本 |
| images/ | 样例图片目录 | 目录 | 图片 |
| keyword_table.csv | 关键词表 | 209B | CSV |
| review_table.csv | 产品评论表 | 437B | CSV |

## 使用指南
- 用于功能测试和演示
- 数据量小，适合快速测试
- 可作为新数据模板

## 测试场景
1. 数据加载测试
2. 预处理流程测试
3. 报告生成测试
4. 图片处理测试

## 相关链接
- [fixtures/INDEX.md](../INDEX.md): fixtures目录索引
- [tests/](../../../tests/): 测试文件目录

## 最后更新
2026-04-03: 初始创建