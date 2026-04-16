# config/ INDEX

## 目的
存放所有配置文件，按产品和用途组织。

## 内容结构
```
config/
├── INDEX.md (此文件)
├── products/          # 产品配置
├── run_configs/       # 正式运行配置
├── market_packs/      # 站点/市场规则包
└── question_banks/    # 问题库配置
```

## 目录说明
| 目录 | 说明 | 文件数量 | 用途 |
|------|------|----------|------|
| products/ | 产品特定资料 | 多目录 | 真实产品属性、词表、维度表 |
| run_configs/ | 正式运行配置 | 多文件 | 上线运行入口配置 |
| market_packs/ | 市场规则配置 | 多文件 | 市场差异化规则 |
| question_banks/ | 问题库 | 多文件 | 类目问题与审核配置 |

## 命名规范
配置文件命名：`<country>-<product>-<purpose>.json`
- 国家代码：de, fr, it, es, en
- 产品代码：T70M, H88等
- 用途：run, regression, sample等

示例：
- `de-t70m-run.json`
- `fr-h88-regression.json`

## 使用指南
1. 新配置放入对应产品目录
2. 遵循命名规范
3. 正式运行入口统一放入 `run_configs/`
4. 临时配置不要长期保留，确认后删除或归档

## 相关链接
- [REPO_RULES.md](../REPO_RULES.md): 仓库规则
- [CLAUDE.md](../CLAUDE.md): 命名规范
- [data/](../data/): 数据文件目录

## 最后更新
2026-04-03: 初始创建
