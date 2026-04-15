# Claude 项目索引规则与命名要求

本文档为 `amazon-listing-skill` 项目提供详细的目录结构、命名规范和文件索引规则。所有新文件必须遵循此规范。

## 目录结构规范

### 标准仓库结构
```
amazon-listing-skill/
├── README.md
├── REPO_RULES.md
├── REPO_INDEX.md
├── CLAUDE.md (此文件)
├── cleanup_candidates.md
├── .gitignore
├── requirements.txt
├── main.py
│
├── modules/              # 核心业务逻辑模块
├── tools/               # 工具函数和辅助模块
├── config/              # 配置文件
├── data/                # 数据文件
├── output/              # 输出文件
├── docs/                # 文档
├── tests/               # 测试文件
└── archive/             # 归档文件
```

### 目录详细说明

#### `modules/`
核心业务逻辑模块，每个文件负责一个独立功能：
- `scoring.py`: 评分算法
- `copy_generation.py`: 文案生成
- `writing_policy.py`: 写作策略
- `keyword_arsenal.py`: 关键词库
- `intent_translator.py`: 意图翻译
- `visual_audit.py`: 视觉审核
- `report_generator.py`: 报告生成
- `risk_check.py`: 风险检查
- `capability_check.py`: 能力检查
- `language_utils.py`: 语言工具
- `keyword_utils.py`: 关键词工具

#### `tools/`
工具函数和数据预处理：
- `data_loader.py`: 数据加载
- `preprocess.py`: 数据预处理
- `country_vocab.py`: 国家词汇表
- `__init__.py`: 包初始化

#### `config/`
配置文件，按产品和国家组织：
```
config/
├── products/           # 产品配置
│   ├── T70M_pro/
│   ├── EN_sample/
│   ├── FR_sample/
│   ├── ES_sample/
│   └── IT_sample/
├── samples/           # 样例配置
└── <country>-<product>-<purpose>.json
```

#### `data/`
数据文件，严格分层：
```
data/
├── raw/               # 原始数据（不可修改）
│   ├── de/           # 德国数据
│   ├── fr/           # 法国数据
│   └── shared/       # 共享数据
├── processed/         # 处理后的数据
├── fixtures/          # 测试数据
└── archive/           # 归档数据
```

#### `output/`
输出文件，按运行组织：
```
output/
├── runs/              # 运行输出
│   ├── <yyyy-mm-dd>_<country>_<product>_<purpose>/
│   └── default/      # 默认运行
├── reports/           # 稳定报告
└── debug/             # 调试输出
```

#### `docs/`
文档文件，按类型组织：
```
docs/
├── prd/              # 产品需求文档
├── knowledge-base/   # 知识库
├── progress/         # 进度记录
├── audits/           # 审核报告
└── summaries/        # 总结报告
```

#### `tests/`
测试文件：
```
tests/
├── unit/            # 单元测试
├── integration/     # 集成测试
└── fixtures/        # 测试夹具
```

#### `archive/`
归档文件：
```
archive/
├── legacy/          # 遗留文件
├── tmp_snapshots/   # 临时快照
└── deprecated_docs/ # 废弃文档
```

## 命名规范

### 通用规则
1. **小写字母**：尽可能使用小写
2. **分隔符**：使用连字符 `-` 或下划线 `_`，不要使用空格
3. **国家代码**：小写 (de, fr, it, es, en)
4. **产品代码**：保持原有标识符 (T70M, H88)
5. **日期格式**：`yyyy-mm-dd`

### 配置文件命名
```
<country>-<product>-<purpose>.json
```
示例：
- `de-t70m-run.json`
- `fr-h88-regression.json`
- `de-h88-sample.json`

### 输出目录命名
```
<yyyy-mm-dd>_<country>_<product>_<purpose>
```
示例：
- `2026-04-03_de_t70m_run`
- `2026-04-03_fr_h88_regression`

### 输出文件命名
```
<yyyy-mm-dd>_<country>_<product>_<artifact>.<ext>
```
示例：
- `2026-04-03_de_t70m_scoring-results.json`
- `2026-04-03_de_t70m_listing-report.md`
- `2026-04-03_fr_h88_execution-summary.json`

### 临时/调试文件
前缀必须是以下之一：
- `tmp_`
- `debug_`
- `scratch_`

临时文件只能存放在：
- `output/debug/`
- `archive/tmp_snapshots/`

## 文件索引要求

### 每个目录必须有 INDEX.md
每个非空目录必须包含 `INDEX.md` 文件，描述：
1. 目录目的和内容
2. 文件列表和说明
3. 创建/更新指南
4. 相关依赖和引用

### INDEX.md 模板
```markdown
# 目录名 INDEX

## 目的
[说明此目录的作用]

## 内容结构
```
[目录树结构]
```

## 文件说明
| 文件 | 说明 | 最后更新 |
|------|------|----------|
| file1.py | 功能描述 | yyyy-mm-dd |
| file2.json | 配置描述 | yyyy-mm-dd |

## 使用指南
[如何使用此目录中的文件]

## 相关链接
- [相关文档链接]
- [依赖模块]
```

### 根目录索引文件
1. `REPO_RULES.md`: 仓库规则
2. `REPO_INDEX.md`: 仓库结构索引
3. `CLAUDE.md`: Claude 代理规则（此文件）
4. `cleanup_candidates.md`: 清理候选项

## 新文件创建流程

1. **确定文件类型**：源代码、配置、数据、文档、测试
2. **选择正确目录**：根据文件类型选择对应目录
3. **遵循命名规范**：使用正确的命名模式
4. **创建索引更新**：更新所在目录的 `INDEX.md`
5. **更新根索引**：如需要，更新 `REPO_INDEX.md`

## 禁止行为

1. ❌ 不要在根目录创建随机文件
2. ❌ 不要使用模糊文件名 (final_v2, test_new, tmp_fix2)
3. ❌ 不要混合不同类型文件
4. ❌ 不要创建重复版本 (copy_generation_new.py)
5. ❌ 不要跳过索引更新

## 用户配置文件参考

本文档维护者的个人配置和业务上下文信息存储在Claude Code的记忆系统中，供AI代理参考。

**配置文件位置**: `~/.claude/projects/-Users-zhoulittlezhou/memory/user_profile.md`

**主要包含内容**:
- 个人身份与愿景（姓名、时区、核心业务愿景）
- 亚马逊运营业务上下文（品类、品牌、合规要求）
- 核心系统架构（OpenClaw多智能体协作阵列）
- 开发与调试偏好（工作流原则、工具链习惯）
- 大模型路由配置（LLM调用策略与API管理）

**使用说明**: 
1. 当处理与用户个人背景、业务逻辑相关的任务时，可参考此配置文件
2. 配置文件会通过Claude Code记忆系统自动加载到上下文
3. 如需详细背景信息，可访问上述文件路径

---

## 修改历史

| 日期 | 版本 | 修改说明 |
|------|------|----------|
| 2026-04-03 | 1.0 | 初始版本 |
```

*此文件由 Claude 自动生成，用于指导文件创建和组织。*