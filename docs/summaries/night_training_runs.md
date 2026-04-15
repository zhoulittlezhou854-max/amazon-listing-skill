# Night Training Runs — 2026-04-06

| 产品 | audit_trail 记录 | Title 结构 | Bullet 职责 | Search Terms 路由 | Scoring (A10 / COSMO / Rufus / Total) | 发现的问题与原因 |
| --- | --- | --- | --- | --- | --- | --- |
| H91lite_US | ✅ 33 条（downgrade + backend-only + dedupe） | 品牌→L1→Scene→Capability→Spec；Waterproof 场景被自动剔除 | B1–B5 按角色输出，B2 注入 90‑min runtime，B4 输出安全提示 | L2/L3 + backend-only (`ip68`, `eis`)；字节 <249；taboo 词已过滤 | 65 / 80 / 54 / 199 | Bullet 关键词仍夹杂西语（camara para grabar contenido）；B1 因不含明确配件继续触发 fallback 日志 |
| H91POR_US | ✅ 36 条 | 同 H91lite，Title 无 underwater；Spec Pack 带 90‑min | Bullet 结构与 H91lite 相同；B4 自动降级为 warning 文案 | Search Terms 去除了 spycam/hidden camera 等禁词，backend-only 仅留 `eis` | 65 / 80 / 54 / 199 | 与 H91lite 相同：挂载配件缺结构化来源导致 B1 fallback；Spanish 关键词仍出现在 B2/B3，需在 keyword slots 侧做 Locale 约束 |
| T70_real_DE | ✅ 12 条 | Title 包含品牌+德语 L1 + scene + 4K/EIS；允许 underwater | B1/B3 使用德语 capability，B2 仍缺分钟（属性无 runtime） | Search Terms 仅保留德语长尾，spycam 已被 blacklist | 50 / 80 / 54 / 184 | B4 文案仅写 “withstands deep water” 未加入 30 m + housing；需从 attribute/supplement 中解析深度；B2 仍缺 runtime 数值 |

**共性结论**
- audit_trail 在三个产品中均捕获 delete/downgrade/backend-only，`listing_report.md` 的 “自动删改审计” 表格可读。
- Title 插槽遵循 brand→L1→scene→capability→spec，且非防水 SKU 已自动剔除 underwater 场景；仍需后续将 Spanish/Chinese capability 彻底翻译成目标语。
- Bullet 结构受 policy 控制，B2 注入 runtime（无数据时 fallback），B4 根据约束输出 warning；后续需补充运行时/配件数据以减少 fallback。
- Search Terms 路由满足 “L2/L3+场景+backend-only” 策略，并新增 taboo blacklist（spycam/hidden camera 等）；下一步可接入更完整的禁词清单。
