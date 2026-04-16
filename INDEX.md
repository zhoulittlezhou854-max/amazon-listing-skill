# 根目录 INDEX

## 目的
Amazon Listing Skill 项目根目录，包含项目入口、配置和目录索引。

## 内容结构
```
amazon-listing-skill/
├── INDEX.md (此文件)
├── CLAUDE.md              # Claude代理规则和命名规范
├── REPO_RULES.md          # 仓库结构规则
├── REPO_INDEX.md          # 仓库结构索引
├── cleanup_candidates.md  # 清理候选项报告
├── README.md              # 项目说明文档
├── .gitignore             # Git忽略文件
├── requirements.txt       # Python依赖
├── .git/                  # Git仓库
├── .claude/               # Claude会话数据
├── main.py                # 主程序入口
├── context_indicator.py   # 上下文指示器
├── strategy_variants/     # 策略变体目录
│
├── modules/              # 核心业务模块
├── tools/               # 工具函数
├── config/              # 配置文件
├── data/                # 数据文件
├── output/              # 输出文件
├── docs/                # 文档
├── tests/               # 测试文件
├── archive/             # 归档文件
├── products/            # 产品配置目录
└── utils/               # 工具目录（空）
```

## 文件说明
| 文件 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| CLAUDE.md | Claude代理规则和命名规范 | 2026-04-03 | 8.5KB |
| REPO_RULES.md | 仓库结构规则 | 2026-04-03 | 7.3KB |
| REPO_INDEX.md | 仓库结构索引 | 2026-04-03 | 7.5KB |
| cleanup_candidates.md | 清理候选项报告 | 2026-04-03 | 11KB |
| README.md | 项目说明文档 | 2026-04-03 | 2KB |
| .gitignore | Git忽略文件 | 2026-04-03 | 1KB |
| requirements.txt | Python依赖 | 2026-04-03 | 0.5KB |
| main.py | 主程序入口 | 2026-04-03 | 38KB |
| context_indicator.py | 上下文指示器 | 2026-04-03 | 6.4KB |

## 目录索引
| 目录 | 说明 | 索引文件 |
|------|------|----------|
| modules/ | 核心业务模块 | [INDEX.md](modules/INDEX.md) |
| tools/ | 工具函数 | [INDEX.md](tools/INDEX.md) |
| config/ | 配置文件 | [INDEX.md](config/INDEX.md) |
| data/ | 数据文件 | [INDEX.md](data/INDEX.md) |
| output/ | 输出文件 | [INDEX.md](output/INDEX.md) |
| docs/ | 文档 | [INDEX.md](docs/INDEX.md) |
| tests/ | 测试文件 | [INDEX.md](tests/INDEX.md) |
| archive/ | 归档文件 | [INDEX.md](archive/INDEX.md) |
| products/ | 产品配置目录 | [INDEX.md](products/INDEX.md) |
| utils/ | 工具目录 | [INDEX.md](utils/INDEX.md) |

## 使用指南
### 新文件创建
1. 参考 `CLAUDE.md` 命名规范
2. 选择正确目录（参考目录索引）
3. 更新对应目录的 `INDEX.md`
4. 如需要，更新本文件

### 文件维护
- 定期运行清理检查
- 遵循仓库规则
- 保持索引文件更新

## 项目入口
- **主程序**: `main.py`
- **配置**: `run_config.json`
- **测试**: `run_stress_test*.py`

## 相关链接
- [CLAUDE.md](CLAUDE.md): 完整命名和规则
- [REPO_RULES.md](REPO_RULES.md): 仓库规则
- [REPO_INDEX.md](REPO_INDEX.md): 详细仓库结构

## 最后更新
2026-04-03: 初始创建，完成目录重组和索引