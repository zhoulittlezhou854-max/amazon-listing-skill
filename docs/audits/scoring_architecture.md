# Metadata-Driven Scoring Architecture (Step 8)

> 更新日期：2026-04-06  
> 责任模块：`modules/scoring.py`、`main.py` Step 8

## 1. 背景与目标
- **旧版局限**：早期评分依赖字符串扫描（在标题/五点/描述中找 “waterproof”“biking”等字面），只对英文文案有效，且无法说明每条得分对应的决策来源。
- **新版原则**：评分完全依据 pipeline 产生的结构化元数据（keyword assignments、bullet trace、capability metadata、audit trail 等），与语言无关，可追溯到具体 slot/scene/合规动作。

## 2. 输入通路
| 数据源 | 描述 | 供给模块 |
| --- | --- | --- |
| `generated_copy.decision_trace.keyword_assignments` | 记录每个 keyword（含 tier/source/search_volume）落在的字段列表 | `modules.copy_generation.KeywordAssignmentTracker` |
| `generated_copy.decision_trace.bullet_trace` | 每个 bullet slot 的 scene/capability/numeric expectation 满足情况 | `modules.copy_generation.generate_bullet_points` |
| `generated_copy.decision_trace.search_terms_trace` | Search Terms 实际字节数、byte cap、backend-only 计数 | `modules.copy_generation.generate_search_terms` |
| `generated_copy.audit_trail` | delete/downgrade/backend_only/locale_skip/numeric_patch 等审计事件 | 所有 copy_generation 子模块 |
| `intent_graph.capability_metadata` / `scene_metadata` | 能力/场景是否允许可见展示 | `modules.intent_translator` |
| `preprocessed_data.capability_constraints` | runtime_minutes、waterproof_depth、backend-only 词等限制 | `tools.preprocess` |
| `preprocessed_data.keyword_data` | price context（avg_price）供价格评分 | `tools.preprocess` / `modules.keyword_arsenal` |

## 3. 评分子模块
### 3.1 A10（关键词路由）
1. **L1 → Title**：统计 tier=L1 的 keyword 在 `assigned_fields` 中出现 `title*` 的条数；按命中比例折算 0~40。
2. **L2 → Bullets**：同理检查 `bullet_*` 覆盖度，要求 ≥3 个不同 slot 才拿满分。
3. **L3 → Search Terms**：确认 L3 是否进入 `search_terms`（可叠加 backend-only 字段）；占比决定 0~30。

### 3.2 COSMO（能力/场景）
1. **Capability Coverage**：遍历 `intent_graph.capability_metadata` 中 `is_supported=True` 的能力，看是否在可见 bullet trace 中出现，对应 0~40。
2. **Scene Distribution**：比较 bullet trace 的 scene_code 与 `scene_metadata`（或 writing_policy.scene_priority），覆盖率映射到 0~40。
3. **Compliance Actions**：`audit_trail` 的 downgrade/backend_only/taboo_skip 不是扣分，而是奖励（每条 4~5 分，最多 20），因为系统正确阻断风险。

### 3.3 Rufus（信息密度）
1. **Numeric Expectations**：统计 bullet trace 中 `numeric_expectation=True` 的 slot，按 `numeric_met` 结果算 0~40；若 slot 无期望则默认满分。
2. **Spec Signals**：检查 capability_constraints 是否提供 runtime / waterproof_depth / accessory_catalog 等结构化数据，有则加分至 40。
3. **Search Term Bytes**：根据 `search_terms_trace.byte_length`，>150 bytes 视为满 20 分，低于则同比例降级。

### 3.4 Price Competitiveness
若 `keyword_data` 提供 avg_price 且属性表有当前售价，则比较 ratio 得 0~10，否则不纳入总分。

## 4. 输出
- `scoring_results.json` 结构包含 A10/COSMO/Rufus breakdown、价格、boundary & A+ 检查。
- 兼容旧字段：`a10_score`、`cosmo_score`、`rufus_score`、`price_competitiveness_score`、`grade`。

## 5. Main Pipeline 集成
1. Step 6 生成文案时写入 `decision_trace`。
2. Step 8 (`main.py` → `modules.scoring.calculate_scores`) 传入 `generated_copy`, `writing_policy`, `preprocessed_data`, `intent_graph`。
3. Step 9 报告模板引用 `scoring_results.json` 展示新分数。

## 6. QA / Future Work
- **数据依赖**：若 real vocab / locale 词表为空，则 A10 分数可能下降——需要补充数据而非改动评分。
- **扩展**：可在 bullet trace 中追加更多信号（如 `backend_only` 原因、persona 标签）以拓展 COSMO/Rufus 维度。

> 结论：新的元数据评分可解释、可审计且语言无关，是当前 140 / 188 / 213 / 223 等分数的唯一官方基准。
