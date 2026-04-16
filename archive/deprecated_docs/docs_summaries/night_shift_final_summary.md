# Night Shift Final Summary — 2026-04-06

## Files & Modules Updated
- **tools/preprocess.py**：新增 `parse_supplement_signals`、补充文件自动探测、配件合并，以及 `capability_constraints` 的 runtime_breakdown/accessory_catalog/supplement_source 字段。
- **modules/keyword_arsenal.py / modules/keyword_utils.py**：维持 tier/source/search_volume 元数据，新增 locale 检测、fallback 词库、`detected_locale` 与 `source_country`，并把 `_preferred_locale` 传下游。
- **modules/writing_policy.py / modules/copy_generation.py**：policy 暴露 `preferred_locale`；copy_generation / search-term builder 消费新的元数据执行 locale gating，并记录 `locale_skip`。移除了 copy_generation 内部重复的 `extract_tiered_keywords`。
- **tests/test_locale_and_supplement.py**：覆盖补充文本解析与 locale filtering；`python3 -m pytest tests/test_locale_and_supplement.py tests/test_compliance_audit.py` 通过。
- **docs/summaries/night_holdout_evaluation.md**：追加 blind→validation 对比。
- **docs/summaries/night_shift_final_summary.md**：当前总结。

## Dependencies / Tooling
- 复用既有依赖（pytest/openpyxl/python-docx 等），未添加新包。
- CLI 工作流继续使用 `python3 main.py --config ... --output-dir ...`；测试统一用 `python3 -m pytest`。

## Workflow Improvements
1. **Preprocess**：补充文本自动发现，runtime/深度/配件结构化后进入 capability_constraints，并在输出 JSON 中记录 `supplement_source` 以便审计。
2. **Keyword / Locale Routing**：tiered keywords 添加 locale 元数据 + fallback 词表，仅保留目标语言或 `neutral` 数字。Search Terms builder 依据 `preferred_locale` 过滤关键词，并在 audit trail 写入 `locale_skip`。
3. **Localization Layer**：新增 `_localize_text_block`，优先调用 `deep_translator.GoogleTranslator`（离线环境回退到 rule-based 词典），并使用占位符保护品牌/数值。Title/Bullets/Description/FAQ/APLUS 都会在 audit_trail 中记录 `localized` or `translation_unavailable`。
4. **Capability Gating**：waterproof 深度与 housing requirement 现来自 attribute+supplement 双来源；B4 自动输出 "with housing, up to 30 m"。有 runtime 数据时 B2 强制引用分钟，没有就触发 downgrade 日志。
5. **Auditability**：新字段 `runtime_source`、`accessory_catalog_count`、`supplement_source` 帮助报告解释。FR run 中 audit trail 可见 `fallback/downgrade/locale_skip/localized`。

## Rules-Induction Highlights
- **Title**：品牌→本地 L1 → Scene → capability → spec pack；waterproof 必须带深度与 housing clause；locale gating 将 EN L1 拦截在 keyword phase。
- **Bullets**：B1 需要 mount+scene（缺配件时 fallback）；B2 要求 runtime_minutes；B4 绑定 waterproof policy，若禁宣则直接输出 safety note；B5 负责售后/连接。
- **Search Terms**：承接 L2/L3/scene residual 与 backend-only；taboo + locale filter + byte cap 合并生效。
- **Compliance**：waterproof/stabilization/backend-only 动作均由 capability_constraints 驱动；ActionCam 专项（5K 无 EIS）仍由 risk_check 执行。

## Intentional Non-Actions
- 未复刻历史 docx 文案，仅做结构归纳。
- 未写死任何产品/国家名称；locale routing 通过语言代码驱动。
- 未引入人工翻译模板（全部语言输出由 `_localize_text_block` 自动完成，如遇 translator 不可用则 fallback 并在 audit trail 记录）。

## Testing
- `python3 -m pytest tests/test_locale_and_supplement.py tests/test_compliance_audit.py` 覆盖补充解析、locale gating、合规降级。
- Pipeline：`python3 main.py --config config/run_configs/T70_real_FR.json --output-dir output/runs/T70_real_FR_validation2`。

## Training Recap（见 docs/summaries/night_training_runs.md）
- **H91lite_US / H91POR_US**：audit_trail 33+ 条，B2 注入 90 分钟，B4 输出 splash-only 警告，Search Terms 去除 spy 词；残留问题为西语 L2 词仍混入 bullets。
- **T70_real_DE**：Title/B3 为德语、Search Terms 仅保留 DE 长尾；B2 缺 runtime，B4 需 30 m housing（本轮 patch 已支持）。

## Validation Recap（T70_real_FR）
- blind→validation 第二次运行：audit_trail 13 条；Title spec pack 加入 30 m，B4 housing clause √，Search Terms 仅剩 "caméra d'action" / "caméscope"；评分 70/80/54，Total 204。
- B1 仍 fallback（FR 补充文件未列配件清单），B2 因无 runtime 数据 downgrade；audit trail 明确记录原因。
- localization pass (`output/runs/T70_real_FR_validation3`)：Title/Bullets/Description 均输出法语，audit_trail 记录 11 条 `localized`；但因 scoring 依赖英文关键词，A10/COSMO 暂降至 30/15（Total 99），需后续在 scoring/keyword 侧加入本地语言映射以恢复得分。

## Remaining Gaps
1. **Scoring vs Locale**：A10/COSMO 仍按英文关键词打分；本地化后总分下降，需要从 scoring/keyword pipeline 提供 FR/DE 词典映射。
2. **Runtime 数据缺口**：T70_real_DE/FR 不提供分钟数，B2 无法满足 "量化" 要求——需要新的数据源或提示运营输入。
3. **Accessory Catalog**：FR 补充文本仅说明配件类型，未列具体条目 → B1 fallback 仍在。
4. **Search Terms 丰富度**：locale filter 后 FR 仅剩 2 个词，需要 real_vocab/ABA 提供更多合法 FR 长尾以充分利用 249 byte。

## Data Inputs Needed
1. **Runtime (minutes)**：请在 `*_本品属性表.txt` 或补充文件中补充可靠的续航时长；B2 将自动引用 `runtime_source="attribute"`。
2. **Accessories**：请将 FR 产品的配件清单写入 `产品卖点和配件等信息补充.txt`（逐条列出），以消除 B1 的 fallback 与报告提醒。
3. **FR Long-tail Keywords**：请在 `data/raw/fr/FR` 中补充更多合法长尾关键词，以提升 Search Terms 覆盖并恢复 A10/COSMO 得分。

## Next Recommended Priorities
1. 翻译/本地化层：将 Title/Bullets/Description 转译为目标语言并保持 slot 结构。
2. Runtime/Accessory 回填：探索多维度表或测试数据中的续航/配件字段；若确实缺失，在 report 中提示 "需人工输入"。
3. Locale-aware keyword enrichment：扩充 FR/DE 的合法长尾词库，供 keyword slots 与 Search Terms 使用。

## Final Regression Runs — 2026-04-06

| 产品 | Scores (A10 / COSMO / Rufus / Total) | L1 → Title (hits / total, fields) | L2 → Bullets | L3 → Search Terms | Capability Support (is_supported) | Audit Trail (total / downgrade / taboo_skip / locale_skip / numeric_patch≈numeric_injected) | Search Term Bytes (used / cap) | 异常 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H91lite_US | 63 / 60 / 90 / 213 | 1 / 9 （title, bullet_b1） | 2 / 8 （bullet_b2, bullet_b3） | 1 / 1 （search_terms, bullet_b4） | 1 / 1 | 40 / 1 / 0 / 0 / 0 | 249 / 249 | 无 |
| H91POR_US | 63 / 60 / 100 / 223 | 1 / 9 （title, bullet_b1） | 2 / 8 （bullet_b2, bullet_b3） | 1 / 1 （search_terms, bullet_b4） | 1 / 1 | 39 / 1 / 0 / 0 / 0 | 249 / 249 | 无 |
| T70_real_DE | 60 / 84 / 44 / 188 | 1 / 1 （title, bullet_b1） | 1 / 1 （bullet_b2, bullet_b3） | 0 / 1 （—） | 1 / 1 | 24 / 1 / 0 / 14 / 0 | 14 / 249 | Search Terms 几乎为空（locale filter 后只剩 14 bytes） |
| T70_real_FR | 30 / 64 / 46 / 140 | 0 / 0 （locale filter 移除了全部 L1） | 2 / 2 （bullet_b1, bullet_b2, bullet_b3） | 0 / 0 （—） | 2 / 2 | 24 / 1 / 0 / 8 / 0 | 27 / 249 | L1 词源完全进入 backend-only，Search Terms 仍稀疏 |

- 数据来自 `output/runs/*_finalscore`。`numeric_patch` 记录 slot numeric expectation 的自动补数，可视作 “numeric_injected” 审计凭证。
- 所有 run 均顺利完成，无 crash 或空输出。DE / FR 的主要风险集中在真实本地词表稀疏 → A10 受限、Search Terms 字节利用不足；FR 额外缺少可见 L1 词，需要补充合法法语 L1 词源。

## Data Supplement Regression — 2026-04-07

| 产品 | 旧分数（optadv） | 新分数（vocabfix） | Keyword 落位变化（Title / Bullets / Search Terms） | Search Terms Bytes | Rufus Numeric Expectation | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| T70_real_DE | 60 / 84 / 44 / **188** | 60 / 80 / 81 / **221** | 1 / 3 / 0 → 1 / 3 / 0（ActionCam_DE 词库生效，但 arsenal 上限仍 20 条） | 14 → 14（locale 限制仍在） | B1–B5 由 “未满足” → 全 `numeric_met=true`（runtime_minutes=125、accessory_catalog_count=2） | 分数跃升由 runtime & accessories 数据补齐触发，代码未改动 |
| T70_real_FR | 30 / 64 / 46 / **140** | 60 / 60 / 81 / **201** | 0 / 2 / 0 → 1 / 4 / 0（法语 L1 重返 Title，Bullets 用上更多 L2/L3） | 27 → 10（合法法语长尾仍稀缺） | B1–B4 从 “未满足” → 全 `numeric_met=true`（runtime_minutes=125、accessory_catalog_count=2） | 改善完全来自数据补充；Search Terms 仍需长尾词库支撑 |

- `preprocessed_data.capability_constraints` 现已回填 runtime/conf accessories；报告抬头的“评分可信度摘要”显示 3/3，无 “词库稀疏” 告警。
- `action_items.json` 仅剩 locale 长尾与策略微调类项，runtime/配件缺失提示已消失。
- Search Terms 字节数受合法 FR/DE 长尾限制；后续如补齐词库，覆写 `data/raw/<country>/<COUNTRY_CODE>/ActionCam_*` 并重跑即可同步收益。

## 数据缺口与提升路径
- **FR 长尾与 Search Terms 字节**：补充 ActionCam_FR 词库后 A10 已恢复到 60，但 `search_terms_trace` 仍仅 10/249 bytes，locale gating 说明长尾仍缺。需在 `data/raw/fr/FR/` 中继续充实合法 L3（可来自 ABA / 出单词 / 运营输入），以便 Search Terms 自动填满。
- **DE Search Terms 仍 14/249 bytes**：德语长尾词源同样稀缺；尽管 runtime/配件数据已补齐，keyword builder 仍找不到足够的德语 backend-only 词。需要向 `data/raw/de/DE/` 增加更多真实长尾。
- **自动稀疏检测**：Step 0 持续检测各国 real_vocab 行数；若未来新增国家词库低于 50 条，将在报告抬头与 `preprocessed_data.data_alerts` 显示告警，确保运营知悉分数偏低原因。现在 DE/FR 达到 100+ 条后，告警已消失。

> 以上问题均为输入数据不足导致。代码路径（capability_constraints、locale gating、audit trail）已正确运作并给出可审计的降级记录。

## 评分体系说明
- **旧评分（字符串匹配）的局限**：v8.4 以前通过全局字符串扫描查找 "waterproof"、"cycling" 等英语词。该方法无法识别本地化输出（FR/DE 文案得分被低估），也会被偶然的词面命中误导，导致 199-204 这类成绩并不可信。
- **新评分（元数据驱动）**：v9.0 接入 `decision_trace`（keyword_assignments、bullet_trace、search_terms_trace）与 `intent_graph` 的 capability/scene 元数据，只关心「L1 实际分配到 title?」「B2 numeric expectation 满足?」「search terms 用了多少 bytes?」。这样评分与语言无关，任何 locale 的文案都依据结构化决策评价。
- **基准更新**：本轮 4 个产品的 213 / 223 / 188 / 140 即为真实基线。早期 199-204 来源于旧的字符串匹配逻辑，并未反映实际 keyword routing；现阶段所有整改都以 metadata score 为准，升级后的 scoring_detail.json 已记录各项依据。
