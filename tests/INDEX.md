# tests/ INDEX

## 目的
存放测试文件，包括单元测试、集成测试和测试夹具。

## 内容结构
```
tests/
├── INDEX.md (此文件)
├── unit/              # 单元测试
├── integration/       # 集成测试
├── fixtures/          # 测试夹具
├── minimal_protocol_tests.py    # 最小协议测试
└── minimal_protocol_results.json # 测试结果
```

## 文件说明
| 文件/目录 | 说明 | 大小 | 最后更新 |
|-----------|------|------|----------|
| unit/ | 单元测试文件 | 空 | - |
| integration/ | 集成测试文件 | 空 | - |
| fixtures/ | 测试夹具数据 | 空 | - |
| minimal_protocol_tests.py | 最小协议测试脚本 | 5.7KB | 2026-04-03 |
| minimal_protocol_results.json | 测试结果 | 1.1KB | 2026-04-03 |

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
2026-04-03: 初始创建