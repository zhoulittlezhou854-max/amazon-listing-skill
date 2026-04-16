# Night Holdout Evaluation — T70_real_FR (Blind Run)

## Blind Run Snapshot（2026-04-06）
- **Title 结构**：`TOSBARRFT camera sport 4k ... 4K, EIS 1080P` → 品牌 + FR L1 (`camera sport 4k`) + 场景 (`cycling recording`) + 能力 (`4k recording`) + Spec Pack (`4K, EIS 1080P`)；禁词黑名单已剔除 “espion” 词根，仅保留允许的技术词。
- **audit_trail**：23 条；含 `taboo_skip`（espion/espion sans fil）、`backend_only`（IP68/EIS）、`fallback`（B1 mount 资料缺失）、`downgrade`（B2 runtime 缺分钟）。
- **Bullets**：
  - B1：磁吸挂载 + 66g 体量；`fallback` 记录提示缺 accessories 元数据。
  - B2：仍落在 runtime 能力，但因属性表缺分钟只输出 “all-day power”，触发 downgrade。
  - B3：轻量 + vlog 场景；语言用 FR/EN 混合关键词（caméra / camera）。
  - B4：Waterproof 边界语句存在，但尚未引用 30 m 深度。
  - B5：保留 Wi-Fi + 兼容性信息，使用 “hd recording” 作为能力标签。
- **Search Terms**：16 个词条，包含 `dashcam moto / caméra sport / caméra d'action` 等本地词；taboo 过滤器已剔除 “espion” 系列词，仅保留 allowed backend-only（无 spy 词）；字节 <249。
- **Scores**：A10 65 / COSMO 80 / Rufus 54 / Total 199 (Max 300)。

## 历史 Docx 结构对比（盲跑后查看）
- **Title**：人工版本在 90+ 字符内塞入 30 m Waterproof、64MP、双屏和使用场景（vlogging、cyclisme、plongée），与我们模型版的 slot 顺序一致，但多了明确深度 + audience 词，且没有冗余 “camera sport 4k ... 4K” 的重复。
- **Bullet Roles**：
  - B1 聚焦磁吸+66g 超轻，可对齐我们当前 B1 目标；需要补 accessories 源以消除 fallback。
  - B2 强调 “Boîtier étanche 30 m” 并把 snorkel/diving 场景和 housing 条件放入同一行；说明我们也应在 capability_constraints 注入深度信息。
  - B3 专注 EIS 1080P，用“motor/bike” 场景强化 COSMO；提示我们可将 review/keyword 中的 véhicule 场景转入 B3 persona。
  - B4 讲 4K + dual screen + 64MP；当前策略把这些拆散，可考虑将高像素/双屏放 B4 以匹配 scoring。
  - B5 用 Wi-Fi + 兼容性收尾，与我们策略一致但写得更本地化（法语大写标题短语）。
- **其他字段**：历史 FAQ 明确 housing requirement 与 EIS 模式，Search Terms 部分保持纯本地词且无 taboo；我们依赖 blacklist 已去掉 spy 词，但仍混入英语 token（mini camera 等），需要 real_vocab routing 优化。

## 接下来
1. **深度/模式补注入**：从 `attribute_data` 提取 `30m` 与 housing 条件，写到 B4 和 Title spec pack；同样解析 EIS 支持模式写入 B3/B4。
2. **Accessories 数据清洗**：把 `产品卖点和配件` txt 解析进结构化字段，避免 B1 fallback。
3. **Locale routing**：对 FR 场景下的 Search Terms 与 bullets 开启 locale-only 过滤，减少英语残词。
4. **准备对照分析**：在完成上述修正后再运行一次 FR 版本，并补充“历史 vs 当前”差异表，确保 blind→validation 流程有据可查。

## Validation Run — 2026-04-06（post capability/locale patch）
- **Status**：T70_real_FR 已转入 Validation 集；运行目录 `output/runs/T70_real_FR_validation2`。
- **Title 结构**：`TOSBARRFT action camera 4k cycling recording ... 30m Waterproof, EIS 1080P`。Spec pack 现在带 `30m Waterproof` + `EIS 1080P`，但整体仍为 EN 语序 → 需要后续翻译层才能输出纯 FR。
- **Bullet 审计**：
  - **B1**：仍因缺 accessories 结构化数据触发 `fallback`，但重量 66 g 继续保留。
  - **B2**：`downgrade` 仍在（FR 属性文件无续航分钟）；属性/补充文本都不含 runtime，因此只能输出 “all-day power” 并记录审计。
  - **B3**：输出 `camera sport, caméra` 混合标签；locale filter 未干预到 visible copy（只作用于关键词/搜索词），需要在后续翻译任务中解决。
  - **B4**：现在显式声明 “Only waterproof when using included housing (up to 30 m)”；`capability_constraints.waterproof_depth_m=30` 生效。
  - **B5**：保留 Wi-Fi + 24-month warranty，无违规。
- **Search Terms**：locale gating 将 EN 词全部剔除后仅剩 `["caméra d'action", "caméscope"]`（<50 bytes）。虽满足“纯法语”，但词量偏少，后续可引入更多 FR 长尾供填充（需 real_vocab enrich）。
- **audit_trail**：13 条记录（taboo_skip、visible_skip、fallback、downgrade）；删除了所有 spy/espion 相关词，也记录了 locale_skip。
- **Scores**：保持 A10 70 / COSMO 80 / Rufus 54 / Total 204。Title/Bullet 结构稳定但因 runtime 数据缺失未能提升 A10。
- **差异 vs 历史 Docx**：
  - Title 现已在 spec pack 中包含 30 m 限制，符合人工稿逻辑，但仍缺 FR 文案调性。
  - 搜索词已无英文词；人工稿的 FR 长尾（caméra casque, caméra sportive 等）需从 real_vocab/ABA 补充。
  - B4 的 housing clause 与历史稿一致；B2 runtime 仍为空白，历史稿通过手工 360 min 数据填充（需确认是否可从别的源复用）。
- **待办**：
  1. 若原始资料确实缺续航数据，需在 report 中提示“runtime 未提供”；若还有其他产品（如 H91）能提供分钟，可考虑迁移规则或允许运营手动输入。
  2. Locale filter 目前只应用于关键词/搜索词，Title/Bullets 仍是英语 → 后续得对 copy_generation 的 `_translate_text_to_language` 输出做合规检查。

## Validation Run — 2026-04-06（localization layer）
- **Run dir**：`output/runs/T70_real_FR_validation3`，preferred_locale=`fr`。
- **Title/Bullets/Description**：均通过 `localized` 审计（method=rule_based）；Title 输出 `caméra d'action…30m Étanche`，Bullets 为法语短句且 `30 m`, `TOSBARRFT`, `EIS 1080P` 等参数保持原样。
- **Audit trail**：新增 11 条 `localized` 记录；若未来可访问外部翻译 API，可将 method 切换为 `external`，当前因离线环境走 rule-based fallback。
- **Scores**：A10=30 / COSMO=15 / Rufus=54 / Total=99。翻译后关键词不再匹配英语评分规则，A10/COSMO 急剧下降；需在 scoring/keyword 侧增加本地语言映射以恢复分数。
- **Known gaps**：B1 fallback、B2 runtime 缺失依旧；Search Terms 仍仅 2 个 FR 词，需要后续 real_vocab enrich。当前报告中 `runtime_source=""`、`accessory_catalog_count=0`、`supplement_source.accessory_count=0` 已清晰记录数据缺口。
