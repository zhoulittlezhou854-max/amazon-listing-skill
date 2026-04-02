# Amazon Listing Generator 项目进度报告 (基于PRD v8.4.0分析)

**生成日期**: 2026-04-03  
**PRD版本**: v8.4.0  
**项目版本**: v1.0 (对应PRD v8.3.5~v8.4.0之间)  
**分析依据**: PRD v8.4.0 完整规范

---

## PRD与当前实现对比分析

### PRD核心要求概述
- **12个输入项**: ABA关键词数据、竞品出单词报告、本品属性表、参数补充、产品全维度表、产品主图、算法规则库、合规规则库、运动相机合规规则库、目标市场、品牌名称、核心卖点
- **10个输出项**: 关键词军火库、视觉审计结果、COSMO意图图谱、产品战略侧写、Listing文案草稿、最终仲裁报告、Module 8算法评分详细表、算法对齐摘要、输出审计日志、Word导出文档
- **5个阶段**: 输入初始化与校验、数据提取与关键词处理、战略建模、文案生成、仲裁评分与输出
- **9个节点**: Start、语种初始化与检测、视觉审计、Python工程核心、意图转译引擎、产品战略侧写师、创意策略、最终仲裁者、导出Word文档

---

## 已完成的模块 (基于PRD标准重新评估) ✅

### 1. 主工作流控制器
- **文件路径**: `main.py`
- **对应PRD节点**: Start节点 + 部分工作流协调
- **状态**: 基础实现，但不符合PRD的9节点架构
- **差距分析**:
  - ✅ 提供命令行接口和步骤协调
  - ❌ 未实现完整的5阶段11步骤流程
  - ❌ 缺少节点间的明确数据传递规范
  - ❌ 缺少audit_trail跟踪机制

### 2. 数据预处理模块 (Step 0 / 阶段二部分)
- **文件路径**: `tools/preprocess.py`
- **对应PRD阶段**: 阶段二（数据提取与关键词处理）的部分功能
- **状态**: 基础数据预处理，但缺少PRD要求的完整功能
- **差距分析**:
  - ✅ 填槽字段解析（国家→语言，品牌，核心卖点，配件）
  - ✅ 多格式文件自适应（属性表、关键词表、评论表、ABA表）
  - ❌ **缺少L1/L2/L3分级**（PRD要求search_volume阈值分级）
  - ❌ **缺少Score/AdScore计算**
  - ❌ **缺少price_context提取**（竞品CSV均价分析）
  - ❌ **缺少竞品品牌提取**
  - ❌ **缺少Review痛点提取**（全维度表处理）
  - ❌ **缺少字段语义映射**（PRD F-2规则）

### 3. 能力熔断模块 (Step 3 / 阶段二部分)
- **文件路径**: `modules/capability_check.py`
- **对应PRD阶段**: 阶段二步骤2.4（能力熔断）
- **状态**: 基础能力检查，但缺少PRD要求的完整输出
- **差距分析**:
  - ✅ 运动相机专项能力熔断规则
  - ✅ 视频分辨率、防水深度、防抖类型等检查
  - ❌ **缺少parameter_constraints生成**（参数补充处理）
  - ❌ **缺少faq_only_capabilities列表生成**
  - ❌ **缺少forbidden_capabilities列表生成**
  - ❌ 输出格式不符合PRD G-2 keyword_pool结构

### 4. 写作策略生成模块 (Step 5 / 阶段三)
- **文件路径**: `modules/writing_policy.py`
- **对应PRD节点**: 产品战略侧写师（Node 6）
- **状态**: 基础writing_policy生成，但缺少PRD要求的完整功能
- **差距分析**:
  - ✅ 场景优先级排序（scene_priority）
  - ✅ 能力与场景绑定关系（capability_scene_bindings）
  - ✅ 硬性约束规则（bullet_slot_rules）
  - ✅ FAQ-only能力标记（faq_only_capabilities）
  - ❌ **缺少四类binding_type全覆盖**（PRD要求used_for_func/used_for_eve/used_for_aud/capable_of）
  - ❌ **缺少forbidden_pairs生成**（来自合规规则库）
  - ❌ **缺少完整的strategy_profile结构**（PRD G-5）
  - ❌ **缺少taboo_concepts生成**
  - ❌ **缺少verified_specs验证**

### 5. 文案生成模块 (Step 6 / 阶段四)
- **文件路径**: `modules/copy_generation.py`
- **对应PRD节点**: 创意策略（Node 7）
- **状态**: 基础文案生成，但缺少PRD要求的完整约束
- **差距分析**:
  - ✅ 多语言模板支持
  - ✅ Title、Bullets、Description、FAQ、Search Terms生成
  - ✅ A+内容生成框架
  - ❌ **未完全实现6条硬性约束**（PRD Rule 1-6）
  - ❌ **缺少边界声明句强制**（Rule 3b）
  - ❌ **缺少A+字数下限检查**（Rule 6，≥500字）
  - ❌ **缺少8项自检清单**
  - ❌ **Search Terms字节限制未验证**（≤250 bytes）

### 6. 风险检查模块 (Step 7 / 阶段五部分)
- **文件路径**: `modules/risk_check.py`
- **对应PRD阶段**: 阶段五步骤5.1（合规红线检查）的部分功能
- **状态**: 基础风险检查，但缺少PRD要求的完整审计
- **差距分析**:
  - ✅ 合规红线检查（联系方式、价格信息等）
  - ✅ writing_policy审计（部分）
  - ✅ Rufus幻觉风险检查（部分）
  - ❌ **缺少writing_policy执行审计**（6条约束逐条检查）
  - ❌ **缺少合规规则库集成**
  - ❌ **缺少运动相机专项合规检查**
  - ❌ 输出格式不符合PRD要求

---

## 完全缺失的核心模块 (按PRD优先级排序) 🚧

### P0优先级 (必需，工作流基础)

#### 1. 输入初始化与校验系统 (阶段一)
- **PRD要求**: 必需输入校验、语种初始化、站点文件一致性校验
- **预期文件**: `scripts/normalize_inputs.py`
- **关键功能**:
  - 12个输入项的完整性校验
  - 目标市场→语种映射（US→English等）
  - 站点与文件一致性校验（SITE_FILE_MISMATCH警告）
  - 生成normalized_input.json（PRD G-1结构）

#### 2. CSV解析与字段映射引擎 (阶段二步骤2.1)
- **PRD要求**: 字段语义映射（ABA/竞品/全维度表）
- **预期文件**: `scripts/parse_csv.py`
- **关键功能**:
  - 自动检测分隔符和编码
  - 语义字段映射（不要求列名完全一致）
  - BOM头处理
  - 输出标准化DataFrame + mapping_report

#### 3. 关键词处理与军火库构建 (阶段二步骤2.2-2.7)
- **PRD要求**: L1/L2/L3分级、Score/AdScore计算、price_context提取等
- **预期文件**: `scripts/extract_fields.py`
- **关键功能**:
  - L1/L2/L3分级（search_volume阈值：L1≥10,000等）
  - [🔥High-Conv]标记（conversion_rate≥1.5%等）
  - Score/AdScore计算
  - price_context提取（竞品CSV均价中位数）
  - 竞品品牌提取
  - Review痛点提取（全维度表）
  - 生成arsenal_output.json（PRD G-2结构）

#### 4. 视觉审计模块 (Node 2)
- **PRD要求**: 多模态分析产品图片，提取视觉标签
- **预期文件**: `modules/visual_audit.py` + Claude Vision API集成
- **关键功能**:
  - visual_tags提取（3-5个标签）
  - mount_visuals识别（挂载方式）
  - usage_context_hints推断（使用场景）
  - compliance_flags检查（合规标志）
  - 生成visual_audit.json（PRD G-3结构）

#### 5. 意图转译引擎 (Node 4)
- **PRD要求**: COSMO意图图谱生成，STAG广告分组
- **预期文件**: `modules/intent_translator.py`
- **关键功能**:
  - 基于High-Conv词的用户身份分析
  - 购买阶段识别（Awareness/Consideration/Decision）
  - 痛点问题分析
  - STAG分组（3-5个场景分组）
  - 生成intent_graph.json（PRD G-4结构）

### P1优先级 (核心功能，影响输出质量)

#### 6. 完整的产品战略侧写师 (Node 6增强)
- **PRD要求**: 完整的strategy_profile生成，含四类binding_type
- **预期文件**: `modules/strategy_profile.py`（增强现有writing_policy.py）
- **关键功能**:
  - capability_tiers划分（P0/P1/P2）
  - writing_policy完整性校验（5个子字段）
  - 四类binding_type全覆盖（used_for_func/used_for_eve/used_for_aud/capable_of）
  - taboo_concepts生成（合并合规规则）
  - verified_specs验证（与属性表完全一致）

#### 7. 算法规则库集成系统
- **PRD要求**: 各节点按章节编号定向读取算法规则库
- **预期文件**: `rules/`目录 + 规则注入机制
- **关键功能**:
  - 算法规则库v2.0（Markdown章节结构）解析
  - 节点定向读取（Node 3读第八章等）
  - 规则内容注入prompt上下文
  - 规则版本管理

#### 8. 合规规则库集成系统
- **PRD要求**: 违禁词清单、风格指南、侵权品牌库处理
- **预期文件**: `rules/compliance/`目录
- **关键功能**:
  - 通用合规规则库解析
  - 运动相机专项合规规则库解析
  - taboo_concepts合并生成
  - 合规红线检查集成

### P2优先级 (输出完善，影响用户体验)

#### 9. 完整算法评分模块 (Node 8 / 阶段五步骤5.3)
- **PRD要求**: A10/COSMO/Rufus/价格竞争力评分，逐维度明细表
- **预期文件**: `modules/scoring.py`
- **关键功能**:
  - A10评分（title_front_80/keyword_tiering/conversion_signals）
  - COSMO评分（scene_coverage/capability_scene_binding/audience_tags）
  - Rufus评分（fact_completeness/faq_coverage/conflict_check）
  - 价格竞争力评分（5档细化，中位数85%-110%→10分等）
  - boundary_declaration_check（边界声明句检查）
  - aplus_word_count_check（A+字数≥500检查）
  - 生成scoring_detail.json（PRD G-7结构）

#### 10. 最终仲裁报告生成器 (Node 8 / 阶段五步骤5.6)
- **PRD要求**: Module 1-8完整报告，中文说明+目标语言Listing
- **预期文件**: `modules/report_generator.py`
- **关键功能**:
  - Module 1: 最终Listing输出
  - Module 2: 关键词覆盖审计表
  - Module 3: 合规红线检查结果
  - Module 4: writing_policy执行审计（6条约束）
  - Module 5: 竞品差异化分析
  - Module 6: 广告投放建议（STAG分组）
  - Module 7: Rufus Q&A种子列表
  - Module 8: 算法对齐评分详细表 + 算法对齐摘要
  - 语言规范：说明文字统一中文，Listing内容目标语言

#### 11. 输出审计日志系统 (阶段五步骤5.8)
- **PRD要求**: 全流程审计信息汇总
- **预期文件**: `scripts/audit_output.py`
- **关键功能**:
  - fields_used记录（实际使用的字段）
  - missing_inputs记录（缺失的必需输入）
  - used_docs/ignored_docs记录
  - risk_flags汇总
  - boundary_declaration_check记录
  - aplus_word_count_check记录
  - l1_l2_l3_distribution统计
  - 生成audit_trail.json（PRD G-8结构）

#### 12. Word文档导出模块 (Node 9)
- **PRD要求**: .docx文件生成，固定命名格式
- **预期文件**: `scripts/export_docx.py`
- **关键功能**:
  - final_report.md → .docx转换
  - 文件命名：Amazon_Listing_{brand}_{site}_v840.docx
  - 保留标题层级和表格格式
  - 不覆盖已有文件

### P3优先级 (辅助功能，优化开发体验)

#### 13. 模拟模块与测试工具
- **预期文件**: `utils/mock_modules.py` + 测试数据
- **关键功能**:
  - 各模块的模拟版本
  - 测试数据生成器
  - 错误注入测试支持

#### 14. 规则文件体系
- **预期文件**: `rules/`目录下的多个规则文件
- **关键功能**:
  - `writing_policy_schema.json`（JSON Schema定义）
  - `keyword_tiering_rules.md`（L1/L2/L3分级规则）
  - `algorithm_scoring_rules.md`（评分规则）
  - `listing_generation_rules.md`（6条硬性约束）
  - `field_mapping_rules.md`（CSV字段映射）
  - `doc_priority_rules.md`（P0-P4优先级）

#### 15. 配置与模板系统
- **预期文件**: `templates/`目录
- **关键功能**:
  - `run_config.json`模板
  - `product_specs.txt`模板
  - `specs_supplement.txt`模板

---

## 各模块与PRD节点映射对照表

| PRD节点 | PRD entityId | 当前对应文件 | 状态 | 差距程度 |
|---------|-------------|-------------|------|----------|
| Start | start-i3lpk77r3r84k7ucpfz0fi2d | main.py | ⚠️ 部分实现 | 缺少节点架构 |
| 语种初始化与检测 | ar-lnx8mymug9z0qrt2kkb06nxn | tools/preprocess.py部分 | ⚠️ 部分实现 | 缺少完整校验 |
| 视觉审计 | ar-z6lxuhrz4ooas7ytumpohd4m | **缺失** | ❌ 未实现 | 完全缺失 |
| Python工程核心 | ar-covpjvc024x30lts8noj25f7 | tools/preprocess.py + modules/capability_check.py | ⚠️ 部分实现 | 缺少L1/L2/L3分级等 |
| 意图转译引擎 | ar-tnj6y2l2rej8sq0ifg5y25ld | **缺失** | ❌ 未实现 | 完全缺失 |
| 产品战略侧写师 | ar-lczwnqyy1v4tbvjiw9j64ksq | modules/writing_policy.py | ⚠️ 部分实现 | 缺少四类binding_type等 |
| 创意策略 | ar-ycbkaxcvj95uuv3mrs7uvtyk | modules/copy_generation.py | ⚠️ 部分实现 | 缺少6条硬性约束完全实现 |
| 最终仲裁者 | ar-nnfgad420hhuxwgfiw4xwkt2 | modules/risk_check.py部分 + 缺失 | ⚠️ 部分实现 | 缺少Module 1-8完整实现 |
| 导出Word文档 | ar-ee7ef0qeg3o7f0pqvwxdzoh6 | **缺失** | ❌ 未实现 | 完全缺失 |

---

## 文件结构差距分析

### 当前文件结构
```
├── main.py                              # 简化的工作流控制器
├── tools/
│   ├── __init__.py
│   └── preprocess.py                    # 基础数据预处理
├── modules/
│   ├── capability_check.py              # 基础能力熔断
│   ├── writing_policy.py                # 基础写作策略
│   ├── copy_generation.py               # 基础文案生成
│   └── risk_check.py                    # 基础风险检查
├── utils/                               # （空目录）
└── SKILL.md                             # 项目技能文档
```

### PRD要求的完整文件结构
```
├── main.py                              # 主工作流入口（9节点协调）
├── scripts/                             # 数据处理脚本
│   ├── normalize_inputs.py              # 输入初始化与校验
│   ├── parse_csv.py                     # CSV解析与字段映射
│   ├── extract_fields.py                # 关键词处理与军火库构建
│   ├── audit_output.py                  # 输出审计日志生成
│   └── export_docx.py                   # Word文档导出
├── modules/                             # 核心逻辑模块
│   ├── visual_audit.py                  # 视觉审计（Node 2）
│   ├── data_processor.py                # Python工程核心（Node 3增强）
│   ├── intent_translator.py             # 意图转译引擎（Node 4）
│   ├── strategy_profile.py              # 产品战略侧写师（Node 6增强）
│   ├── copy_generator.py                # 创意策略（Node 7增强）
│   ├── scoring_engine.py                # 算法评分（Node 8部分）
│   └── report_generator.py              # 最终仲裁报告（Node 8部分）
├── rules/                               # 规则文件体系
│   ├── algorithm_rules_v2.md            # 算法规则库
│   ├── compliance_rules.txt             # 合规规则库
│   ├── compliance_actioncam.txt         # 运动相机合规规则库
│   ├── writing_policy_schema.json       # writing_policy JSON Schema
│   ├── keyword_tiering_rules.md         # L1/L2/L3分级规则
│   ├── algorithm_scoring_rules.md       # 算法评分规则
│   ├── listing_generation_rules.md      # 文案生成规则
│   ├── field_mapping_rules.md           # 字段映射规则
│   └── doc_priority_rules.md            # 文档优先级规则
├── templates/                           # 输入模板
│   ├── run_config.json                  # 运行配置模板
│   ├── product_specs.txt                # 属性表模板
│   └── specs_supplement.txt             # 参数补充模板
├── utils/                               # 工具函数
│   ├── mock_modules.py                  # 模拟模块
│   └── test_data/                       # 测试数据
└── tests/                               # 测试套件
    ├── unit/
    └── integration/
```

---

## 关键差距总结（10条核心问题）

### 1. 输入处理不完整
- **问题**: 仅支持部分输入项，缺少12个输入的完整校验和处理
- **影响**: 无法处理算法规则库、合规规则库、产品主图等关键输入
- **PRD要求**: 阶段一（输入初始化与校验）完整实现

### 2. 关键词分级系统缺失
- **问题**: 缺少L1/L2/L3分级、Score/AdScore计算、High-Conv标记
- **影响**: 关键词军火库无法构建，影响后续所有模块
- **PRD要求**: 阶段二步骤2.2-2.3

### 3. 数据提取功能不完整
- **问题**: 缺少price_context提取、竞品品牌提取、Review痛点提取
- **影响**: 价格竞争力评分缺失，竞品分析不完整
- **PRD要求**: 阶段二步骤2.5-2.7

### 4. 视觉审计完全缺失
- **问题**: 无产品图片分析能力
- **影响**: 视觉标签、挂载方式、使用场景推断无法获取
- **PRD要求**: Node 2（视觉审计）完整实现

### 5. 意图转译引擎缺失
- **问题**: 无COSMO意图图谱生成能力
- **影响**: STAG广告分组、用户意图分析无法进行
- **PRD要求**: Node 4（意图转译引擎）完整实现

### 6. writing_policy不完整
- **问题**: 缺少四类binding_type全覆盖、forbidden_pairs生成等
- **影响**: 文案生成约束不完整，可能产生不合规内容
- **PRD要求**: 阶段三完整实现

### 7. 文案生成约束不全
- **问题**: 未完全实现6条硬性约束，缺少边界声明句、A+字数检查等
- **影响**: 生成的Listing可能不符合算法优化要求
- **PRD要求**: 阶段四完整实现（Rule 1-6）

### 8. 算法评分系统缺失
- **问题**: 无A10/COSMO/Rufus/价格竞争力评分
- **影响**: 无法评估Listing质量，无法提供优化建议
- **PRD要求**: 阶段五步骤5.3-5.5

### 9. 审计与日志系统缺失
- **问题**: 无audit_trail生成，无法追踪执行过程
- **影响**: 输出透明度低，问题排查困难
- **PRD要求**: audit_trail.json强制输出

### 10. 输出格式不完整
- **问题**: 缺少最终仲裁报告、Word导出文档等关键输出
- **影响**: 交付物不完整，无法直接使用
- **PRD要求**: 10个输出项完整生成

---

## 实施优先级建议

### 第一阶段（核心基础，1-2周）
1. **输入处理系统** (`scripts/normalize_inputs.py`) - P0
2. **CSV解析引擎** (`scripts/parse_csv.py`) - P0
3. **关键词处理系统** (`scripts/extract_fields.py`) - P0
4. **writing_policy增强** (`modules/strategy_profile.py`) - P1

### 第二阶段（核心功能，2-3周）
5. **算法规则库集成** (`rules/`目录) - P1
6. **文案生成约束完善** (`modules/copy_generator.py`增强) - P1
7. **算法评分模块** (`modules/scoring.py`) - P1
8. **报告生成模块** (`modules/report_generator.py`) - P2

### 第三阶段（辅助功能，1-2周）
9. **审计日志系统** (`scripts/audit_output.py`) - P2
10. **Word导出模块** (`scripts/export_docx.py`) - P2
11. **视觉审计模块** (`modules/visual_audit.py`) - P3
12. **意图转译模块** (`modules/intent_translator.py`) - P3

### 第四阶段（测试优化，1周）
13. **模拟模块与测试数据** (`utils/mock_modules.py`) - P3
14. **完整测试套件** (`tests/`目录) - P3
15. **文档与模板** (`templates/`目录) - P3

---

## 风险与挑战

### 高风险
1. **算法评分准确性**：A10/COSMO/Rufus算法实现复杂度高
2. **多模态视觉分析**：Claude Vision API集成和成本控制
3. **规则库解析**：算法规则库v2.0的章节定向读取实现

### 中风险
4. **字段语义映射**：CSV字段自动识别可能不稳定
5. **性能问题**：多文件处理和大数据量可能影响性能
6. **错误处理**：降级行为的正确实现

### 低风险
7. **模板系统**：输入模板的标准化
8. **测试覆盖**：完整测试套件的构建

---

## 验收标准参考（基于PRD J节）

### 输入完整时的预期输出检查清单
- [ ] `arsenal_output.json`：含L1/L2/L3分级、price_context数值、competitor_brands非空
- [ ] `strategy_profile.json`：writing_policy 5个子字段非空，四类binding_type全覆盖
- [ ] `listing_draft.json`：self_check 8项全部true，search_terms≤250 bytes
- [ ] `final_report.md`：含Module 1-8全部内容，Module 8有逐维度得分表
- [ ] `scoring_detail.json`：A10/COSMO/Rufus逐项得分，价格竞争力有具体得分
- [ ] `audit_trail.json`：used_docs包含所有输入文件，ignored_docs为空或合理
- [ ] `Amazon_Listing_{brand}_{site}_v840.docx`：Word文档正确生成

### 输入缺失时的降级行为检查清单
- [ ] 必需输入缺失 → 立即终止，输出MISSING_REQUIRED_INPUT错误
- [ ] competitor_words.csv缺失 → price_context=null，价格评分跳过
- [ ] full_dimension.csv缺失 → review_pain_points=[]，FAQ退化为属性表推断
- [ ] product_images缺失 → visual_audit跳过，audit_trail记录
- [ ] CSV字段映射失败 → 跳过该字段，audit_trail.ignored_docs记录原因

### 输出质量评估检查清单
- [ ] Title：前80字符含品牌名+类目词+L1词+最高优先级场景词
- [ ] Bullets：B1-B5满足bullet_slot_rules，B4含边界声明句
- [ ] FAQ：覆盖5个类型，每个回答含具体数字或条件
- [ ] Search Terms：字节数≤250，无重复词，无品牌词
- [ ] 算法评分：三个维度各有逐项得分，每个维度有说明简述

---

**最后更新**: 2026-04-03  
**分析依据**: PRD v8.4.0 完整文档  
**维护者**: Claude Code Assistant  
**状态**: 项目当前实现仅覆盖PRD约30%的核心功能，需要系统性重构和增强