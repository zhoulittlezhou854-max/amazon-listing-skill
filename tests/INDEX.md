# tests/ INDEX

## 目的
存放测试文件，包括单元测试、集成测试和测试夹具。

## 内容结构
```
tests/
├── INDEX.md (此文件)
├── unit/              # 单元测试
├── integration/       # 集成测试
└── fixtures/          # 测试夹具
```

## 文件说明
| 文件/目录 | 说明 | 大小 | 最后更新 |
|-----------|------|------|----------|
| unit/ | 单元测试文件 | 空 | - |
| integration/ | 集成测试文件 | 空 | - |
| fixtures/ | 测试夹具数据 | 空 | - |
| test_canonical_facts.py | 产品事实标准化、H91 alias、claim permission 与 fact readiness 测试 | 小 | 2026-04-29 |
| test_claim_language_contract.py | 合规语言审计、repairable claim 与 blocking claim 测试 | 小 | 2026-04-29 |
| test_field_provenance.py | 字段 provenance tier、fallback eligibility 与规范化匹配测试 | 小 | 2026-04-29 |
| test_image_handoff.py | 图片制作交接文档结构、风险提示与写入测试 | 小 | 2026-04-29 |
| test_keyword_reconciliation.py | 最终候选文案关键词复核、覆盖统计与 metadata 保真测试 | 小 | 2026-04-29 |
| test_keyword_protocol.py | 关键词协议质量过滤、蓝海机会、相对分层与路由测试 | 小 | 2026-04-28 |
| test_listing_candidate.py | Listing 候选对象 reviewable/paste-ready 契约测试 | 小 | 2026-04-29 |
| test_readiness_verdict.py | ReadinessVerdict 候选排名、fallback 与 launch gate 契约测试 | 小 | 2026-04-29 |
| test_runtime_bootstrap.py | 虚拟环境自举入口测试 | 小 | 2026-04-28 |
| test_slot_contracts.py | bullet slot 单一语义 promise、B5 断裂检测与 repair payload 测试 | 小 | 2026-04-29 |

## 测试结构

### 单元测试 (unit/)
- 测试单个函数或类
- 使用mock隔离依赖
- 快速执行

### 集成测试 (integration/)
- 测试模块间交互
- 使用真实数据
- 验证端到端流程

### 测试夹具 (fixtures/)
- 测试数据
- 模拟对象
- 配置模板

## 使用指南
1. 新功能必须添加测试
2. 测试文件命名：`test_<module>_<function>.py`
3. 使用pytest框架
4. 保持测试独立和可重复

## 运行测试
```bash
# 运行所有测试
pytest tests/

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/
```

## 相关链接
- [modules/](../modules/): 被测试的核心模块
- [tools/](../tools/): 被测试的工具模块
- [data/fixtures/](../data/fixtures/): 测试数据

## 最后更新
2026-04-29: 增加 canonical facts、claim language、field provenance、slot contracts 合同层测试索引
2026-04-29: 增加 ReadinessVerdict 契约测试索引
2026-04-29: 增加最终关键词复核测试索引
2026-04-29: 增加 Listing 候选对象契约测试索引
2026-04-03: 初始创建
2026-04-28: 增加关键词协议核心测试索引
2026-04-28: 增加虚拟环境自举测试索引
