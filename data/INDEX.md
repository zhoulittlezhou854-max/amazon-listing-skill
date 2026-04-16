# data/ INDEX

## 目的
存放所有数据文件，按处理阶段严格分层。

## 内容结构
```
data/
├── INDEX.md (此文件)
├── raw/               # 原始数据（不可修改）
├── processed/         # 处理后的数据
├── fixtures/          # 测试数据
└── archive/           # 归档数据
```

## 目录说明
| 目录 | 说明 | 文件数量 | 用途 |
|------|------|----------|------|
| raw/ | 原始输入数据（含 DE/FR 真实词表） | 多文件 | 数据输入，不可修改 |
| processed/ | 处理后的数据 | 0 | 中间处理结果 |
| fixtures/ | 测试夹具数据 | 5文件 | 单元测试和集成测试 |
| archive/ | 归档数据 | 0 | 历史数据归档 |

## 数据分层规则
1. **raw/**: 原始数据，来自外部源，不可修改
2. **processed/**: 清洗、转换后的数据，可重新生成
3. **fixtures/**: 小型测试数据，用于自动化测试
4. **archive/**: 不再使用但需要保留的历史数据
5. **真实国家词表**: `data/raw/<country>/<COUNTRY_CODE>/` 目录下同时存放 `.csv` 和 `.xlsx` 文件；例如 `data/raw/fr/FR/H88_FR_出单词.xlsx`（FR order_winning 主数据源） 和 `data/raw/de/DE/H88_DE_ABA_Merged.csv`。
6. **XLSX 支持**: `tools/data_loader.py` 统一使用 openpyxl 解析 Excel，因此提交新的 FR/DE 词表时无需额外转换，只需放入上述路径即可。

## 使用指南
- 新数据应放入正确层级
- raw/ 数据必须保持原始状态
- processed/ 数据应有生成脚本
- 大型数据不应提交到git，使用.gitignore

## 相关链接
- [REPO_RULES.md](../REPO_RULES.md): 仓库规则
- [CLAUDE.md](../CLAUDE.md): 命名规范
- [config/](../config/): 配置文件目录

## 最后更新
2026-04-03: 初始创建，数据文件重组
