# config/ INDEX

## 目的
存放所有配置文件，按产品和用途组织。

## 内容结构
```
config/
├── INDEX.md (此文件)
├── products/          # 产品配置
└── samples/           # 样例配置
```

## 目录说明
| 目录 | 说明 | 文件数量 | 用途 |
|------|------|----------|------|
| products/ | 产品特定配置 | 5目录 | 不同产品的运行配置 |
| samples/ | 样例配置 | 1文件 | 配置模板和示例 |

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
3. 样例配置放入 `samples/`
4. 旧配置归档到 `archive/`

## 相关链接
- [REPO_RULES.md](../REPO_RULES.md): 仓库规则
- [CLAUDE.md](../CLAUDE.md): 命名规范
- [data/](../data/): 数据文件目录

## 最后更新
2026-04-03: 初始创建