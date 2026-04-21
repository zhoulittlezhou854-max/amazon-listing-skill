# unit/ INDEX

## 目的
存放单元测试文件，测试单个函数、类或模块。

## 内容结构
```
unit/
├── INDEX.md (此文件)
└── test_streamlit_launcher.py
```

## 文件说明
| 文件 | 说明 | 最后更新 |
|------|------|----------|
| test_streamlit_launcher.py | 验证本地 Streamlit 启动器的命令拼装、PID 解析与僵尸 PID 清理 | 2026-04-21 |

## 测试规范
### 文件命名
```
test_<module>_<function>.py
```
示例：
- `test_scoring_calculate.py`
- `test_copy_generation_generate.py`

### 测试结构
```python
def test_function_normal_case():
    # 正常情况测试
    pass

def test_function_edge_case():
    # 边界情况测试
    pass

def test_function_error_case():
    # 错误情况测试
    pass
```

## 覆盖率目标
- 核心模块：90%+ 覆盖率
- 工具模块：80%+ 覆盖率
- 辅助模块：70%+ 覆盖率

## 使用指南
1. 每个核心函数应有对应测试
2. 测试应独立，不依赖外部状态
3. 使用mock隔离依赖
4. 测试应快速执行（<100ms每个）

## 相关链接
- [tests/INDEX.md](../INDEX.md): 测试目录总索引
- [modules/](../../modules/): 被测试的核心模块

## 最后更新
2026-04-03: 初始创建
2026-04-21: 新增 Streamlit 启动器单元测试索引
