# Repository Index

This document captures the filesystem layout of `amazon-listing-skill` as of **2026-04-07** and compares it with the canonical expectations in `REPO_RULES.md`.

## Current Repository Structure

```
amazon-listing-skill/
├── .DS_Store                   # macOS artifact（建议后续删除）
├── .claude/                    # 历史 AI 会话缓存
├── README.md
├── REPO_RULES.md
├── REPO_INDEX.md
├── cleanup_candidates.md
├── CLAUDE.md
├── INDEX.md
├── requirements.txt
├── .pytest_cache/              # pytest 最近生成的缓存
├── archive/
│   └── legacy/
│       ├── README.md                  # 新增：说明 legacy 目录只读
│       ├── output_de*/output_fr*      # 历史输出与评分报告
│       ├── python_scripts/            # 早期脚本快照
│       └── strategy_variants/         # 已退役策略样本
├── config/
│   ├── run_configs/                   # H91/T70 等产品的执行配置
│   └── products/
│       ├── H91lite_US/
│       ├── H91POR_US/
│       ├── T70_real_DE/
│       ├── T70_real_FR/
│       └── samples/
│           └── FR_sample/             # 仅保留 demo，用于文档示例
├── data/
│   ├── raw/
│   │   ├── de/DE/                     # DE 真实词表、ABA 等
│   │   ├── fr/FR/                     # FR 真实词表、ABA 等
│   │   └── shared/
│   ├── fixtures/
│   │   └── sample_data/               # 旧 sample_data 迁入 fixtures
│   └── archive/                       # 历史数据快照
├── docs/
│   ├── prd/
│   ├── audits/
│   ├── summaries/
│   └── knowledge-base/
├── main.py
├── modules/                           # 业务核心模块
├── tools/                             # 预处理/加载工具
├── output/
│   ├── runs/                          # 现行输出（H91/T70 回归）
│   └── reports/
├── tests/
└── config/…（其余文件同上）
```

## Notable Components

- **archive/legacy** now aggregates *all*历史输出（`output_de*`, `output_fr*`）、旧脚本以及 `strategy_variants/`，并通过 `README.md` 标注“只读快照”。
- **config/products** 是唯一的产品输入来源；`products/` 根目录已被清空，demo 样本统一放在 `config/products/samples/`。
- **data/fixtures/sample_data** 承载旧的 sample_data，用于单元测试或文档示例；真实词表仍在 `data/raw/<country>/<COUNTRY_CODE>/`。
- **output/** 目录仅保留 `runs/` 与 `reports/`，所有 legacy 输出已搬入 `archive/legacy/`。

## Alignment vs. Canonical Structure

| Canonical 要求 | 当前状态 | 备注 |
| --- | --- | --- |
| `config/` 下集中管理产品/配置 | ✅ | `config/products/`、`config/run_configs/` 已对齐；demo 样本归档至 `config/products/samples/` |
| `data/fixtures` 承载示例数据 | ✅ | `sample_data/` 已迁至 `data/fixtures/sample_data/` |
| 根目录避免输出/临时目录 | ✅ | `output_de*`、`output_fr*`、`strategy_variants/` 等已移动到 `archive/legacy/`，根目录仅保留必须文件 |
| `archive/` 记录旧资产并显式标注 | ✅ | 新增 `archive/legacy/README.md`，说明“历史只读”策略 |
| `.gitignore` / `requirements.txt` | ✅ | 仍位于根目录，最新依赖已记录 |

## Remaining Housekeeping Opportunities

- **Meta 文件**：`CLAUDE.md`、`INDEX.md` 以及 `.claude/` 会话缓存仍位于根目录；若后续不需保留，可迁入 `docs/` / `archive/legacy/` 或直接清理。`.DS_Store` 也可加入 `.gitignore` 后删除。
- **Historical data volume**：`archive/legacy/` 下仍有大量旧输出（>10 GB）；如需瘦身，可进一步压缩或分批清理。
- **Automation**：未来可在 CI 中加入检查，确保新的输出一律写入 `output/runs/<run_name>/`。

总体来看，目录已经与 `REPO_RULES.md` 保持一致：工作目录仅包含活跃代码/配置/文档，历史资产集中在 `archive/legacy/`，并且所有产品输入统一放在 `config/products/`。EOF
