# tools/ INDEX

## 目的
存放工具函数、数据加载器和预处理模块。

## 内容结构
```
tools/
├── INDEX.md (此文件)
├── __init__.py        # 包初始化
├── country_vocab.py   # 国家词汇表
├── data_loader.py     # 数据加载器
├── launch_streamlit_console.command # 双击启动本地控制台
├── live_smoke.py      # 线上 smoke 工具
├── preprocess.py      # 数据预处理
└── streamlit_launcher.py # 本地 Streamlit 控制台启动器
```

## 模块说明
| 模块 | 说明 | 大小 | 最后更新 |
|------|------|------|----------|
| __init__.py | 包初始化文件 | 小 | 2026-04-03 |
| country_vocab.py | 国家特定词汇和规则 | 中 | 2026-04-03 |
| data_loader.py | 加载CSV/JSON数据 | 中 | 2026-04-03 |
| launch_streamlit_console.command | 双击后启动控制台并自动打开浏览器 | 小 | 2026-04-21 |
| preprocess.py | 数据清洗和转换 | 中 | 2026-04-03 |
| live_smoke.py | 本地/线上 smoke 运行工具 | 中 | 2026-04-21 |
| streamlit_launcher.py | 启停 Streamlit 控制台并管理 PID/日志 | 中 | 2026-04-21 |

## 功能说明

### data_loader.py
- 加载CSV、JSON、Excel文件
- 统一数据格式
- 关键词 CSV/XLSX 字段标准化会保留蓝海指标（CTR、CPC、竞品数、标题密度、集中度等）
- 错误处理和验证

### preprocess.py
- 数据清洗和标准化
- 关键词表摄取会保留 SQP/ABA/PPC 指标，并避免反馈词伪造 tier 或搜索量地板
- 文本预处理
- 特征提取

### country_vocab.py
- 国家特定词汇表
- 语言规则
- 本地化处理

### streamlit_launcher.py
- 启动本地 Streamlit 控制台到后台
- 输出固定访问地址、PID 文件和日志文件位置
- 支持 `start / stop / restart / status`

### launch_streamlit_console.command
- 适合 Finder 里双击启动
- 会调用 `streamlit_launcher.py start`
- 启动后自动打开浏览器到本地控制台

## 使用指南
1. 数据相关工具放入此目录
2. 保持函数单一职责
3. 添加详细文档字符串
4. 与业务逻辑分离

## 依赖关系
- 依赖 `data/` 目录的输入数据
- 被 `modules/` 目录的模块调用
- 独立于业务逻辑，可复用

## 相关链接
- [modules/](../modules/): 核心业务模块
- [data/](../data/): 数据文件目录
- [tests/](../tests/): 测试文件目录

## 最后更新
2026-04-03: 初始创建
2026-04-21: 补充 Streamlit 启动器与 smoke 工具索引
2026-04-28: 补充关键词蓝海指标摄取说明
