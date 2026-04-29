# superpowers INDEX

## 目的
存放通过 Superpowers 工作流生成的设计与计划文档，作为阶段性实现与收口任务的执行入口。

## 内容结构
```
docs/superpowers/
├── INDEX.md
├── plans/
│   ├── INDEX.md
│   └── <yyyy-mm-dd>-<plan-name>.md
└── specs/
    ├── INDEX.md
    └── <yyyy-mm-dd>-<topic>-design.md
```

## 文件说明
| 文件 | 说明 | 最后更新 |
|------|------|----------|
| INDEX.md | 本目录索引 | 2026-04-20 |
| plans/ | 分阶段实施计划与专项修复计划 | 2026-04-29 |
| specs/ | 设计文档与需求基线 | 2026-04-29 |
| plans/2026-04-29-field-contracts-and-canonical-facts-plan.md | canonical_facts、claim_language_contract、field_provenance、slot_contracts 合同层实施计划 | 2026-04-29 |

## 使用指南
- 新增设计时统一放入 `specs/`
- 新增计划时统一放入 `plans/`
- 设计文件名使用 `yyyy-mm-dd-<topic>-design.md`
- 计划文件名使用 `yyyy-mm-dd-<plan-name>.md`
- 新增或更新设计/计划后同步维护对应 `INDEX.md`

## 相关链接
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/INDEX.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/progress/PROGRESS.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/AGENTS.md`
