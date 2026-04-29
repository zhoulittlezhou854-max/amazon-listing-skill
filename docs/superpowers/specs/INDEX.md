# specs INDEX

## 目的
存放通过 Superpowers brainstorming 流程整理出的正式设计文档，作为后续 implementation plan 与研发执行的需求基线。

## 内容结构
```
docs/superpowers/specs/
├── INDEX.md
└── <yyyy-mm-dd>-<topic>-design.md
```

## 文件说明
| 文件 | 说明 | 最后更新 |
|------|------|----------|
| INDEX.md | 本目录索引 | 2026-04-25 |
| 2026-04-25-packet-rerender-and-quality-gated-hybrid-design.md | Phase 2 结构化 rerender 与 hybrid quality-gated selection 设计 | 2026-04-25 |
| 2026-04-27-runtime-isolation-and-supervised-execution-design.md | 共享运行底座隔离、监督执行与 partial-success 设计 | 2026-04-27 |
| 2026-04-27-canonical-run-state-and-listing-verdict-design.md | 统一运行真相源、候选 provenance 与上线 verdict 架构设计 | 2026-04-27 |
| 2026-04-29-listing-system-contracts-design.md | listing 系统合同优先中等重构设计：关键词、候选、评分与 readiness verdict 分层 | 2026-04-29 |
| 2026-04-29-accessory-registry-and-version-b-hardening-backlog.md | 配件勾选输入层与 version_b rerender 验收门后续修复 backlog | 2026-04-29 |

## 使用指南
- 新设计统一放入 `docs/superpowers/specs/`
- 设计文件名使用 `yyyy-mm-dd-<topic>-design.md`
- 设计定稿后，再写对应的 implementation plan
- 若设计演进，新增新文件，不覆盖旧设计结论

## 相关链接
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers/INDEX.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers/plans/INDEX.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/AGENTS.md`
