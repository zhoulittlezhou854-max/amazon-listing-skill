# Streamlit 控制台与数据反补大迭代拆解 v1

## 1. 目标定义
本轮迭代不再只优化单次 Listing 生成效果，而是把现有 pipeline 升级成一个可持续运营的本地 SaaS 雏形：

- 新品：支持可视化建品、上传四张核心表、触发生成、查看/下载报告。
- 老品：支持导入 SellerSprite / PPC 词表，做人机共审，再触发安全重构。
- 底层：把“流量词保留、真值一致性、竞品词拦截、真实 LLM 证明”变成系统级硬闸门。
- 输出：最终报告仍然面向 Amazon 实际上架，且保留系统排查信息。

## 2. 当前基线能力盘点
仓库已经具备可复用的核心后端能力：

- `main.py`
  - 已具备 step 化 workflow 执行能力。
  - 已能输出 `listing_report.md`、`generated_copy.json`、`risk_report.json`、`scoring_results.json`。
- `modules/copy_generation.py`
  - 已支持标题 / Bullet / 描述 / FAQ / Search Terms / A+ 生成。
  - 已具备多语言、本地化、关键词清洗、部分 live/fallback 元数据记录。
- `modules/intent_translator.py`
  - 已具备 COSMO intent graph 基础能力，可继续承接“广告词 -> 场景意图节点”。
- `modules/writing_policy.py`
  - 已具备动态策略、场景优先级、能力场景绑定基础。
- `modules/risk_check.py`
  - 已具备 visible 字段风险扫描、FAQ-only、合规拦截基础。
- `modules/scoring.py`
  - 已具备 A10 / COSMO / Rufus / 生产就绪度评分基础。
- `modules/llm_client.py` + `tools/live_smoke.py`
  - 已具备 live LLM healthcheck、request_id / model 元数据记录、空包识别基础。

结论：
这不是从 0 到 1 重做，而是“在现有生成引擎外面补一层产品化壳 + 在现有中台里补反馈链路”。

## 3. 核心缺口与改造方向

### 已有但要增强
- live LLM 元数据：已有，但要升级成 UI 可见、失败可解释、严格阻断正式输出。
- risk/truth：已有，但要新增“历史自然流量词留存率”与“广告词意图吸收白名单”。
- intent / blueprint：已有，但缺少“从 SellerSprite 反补词表触发的强定向改写”。

### 当前缺失
- Streamlit 控制台
- 产品工作区自动建档能力
- SellerSprite / PPC 词表解析模块
- Human-in-the-loop 交互审批层
- 历史 Listing 版本资产与 retention 对比层
- “正式可上架 / 不可上架”状态机

## 4. 总体架构拆分
建议拆成 6 个新层级，而不是把 UI 逻辑直接塞进 `main.py`：

1. `app/streamlit_app.py`
   - Streamlit 入口，双 Tab UI。
2. `app/services/workspace_service.py`
   - 新品建档、目录初始化、文件落盘、配置生成。
3. `app/services/run_service.py`
   - 封装 `main.py` workflow 调用，统一返回执行状态、报告路径、元数据。
4. `modules/csv_parser.py`
   - 解析 SellerSprite / 广告词表，识别 Organic / SP / 脏词 / 竞品词。
5. `modules/feedback_loop.py`
   - 把“运营勾选结果”转成 keyword arsenal 的增量输入，并写入反补策略快照。
6. `modules/retention_guard.py`
   - 对比历史版本与本次版本，计算核心自然词留存率，并向 `risk_check.py` / `scoring.py` 注入硬结果。

## 5. 建议目录方案

```text
amazon-listing-skill/
├── app/
│   ├── streamlit_app.py
│   ├── services/
│   │   ├── workspace_service.py
│   │   ├── run_service.py
│   │   └── report_service.py
│   └── components/
│       ├── upload_panel.py
│       ├── product_selector.py
│       └── feedback_grid.py
├── modules/
│   ├── csv_parser.py
│   ├── feedback_loop.py
│   ├── retention_guard.py
│   └── listing_status.py
├── workspace/
│   └── <product_site>/
│       ├── inputs/
│       ├── runs/
│       ├── feedback/
│       ├── snapshots/
│       └── product_config.json
```

## 6. 四阶段执行计划

### Phase 1：控制台 MVP + 后端服务层解耦
目标：先把“零代码建品 -> 跑 workflow -> 页面看报告”打通。

#### Stories
- 新增 `app/streamlit_app.py`
  - Tab 1 新品上架
  - Tab 2 老品反补先留占位
- 新增 `app/services/workspace_service.py`
  - 根据产品代号 + 站点生成 `workspace/<sku>_<site>/`
  - 自动归档 4 张输入表 + 补充文本
  - 自动生成 run config
- 新增 `app/services/run_service.py`
  - 统一调用 `AmazonListingGenerator`
  - 标准返回：`status / run_dir / report_path / metadata / error`
- 调整 `main.py`
  - 把当前 CLI 可重用能力暴露成可 import 的 service 级函数
  - 避免 Streamlit 直接依赖 print 输出判断状态
- 新增 `modules/listing_status.py`
  - 定义 `READY_FOR_REVIEW / NOT_READY_FOR_LISTING / RUN_FAILED`

#### 关键文件
- 新增 `app/streamlit_app.py`
- 新增 `app/services/workspace_service.py`
- 新增 `app/services/run_service.py`
- 新增 `modules/listing_status.py`
- 修改 `main.py`
- 修改 `requirements.txt`，加入 `streamlit`
- 修改 `README.md`，补本地 Web 启动说明

#### 验收标准
- 运营无需命令行即可上传资料并生成一份完整报告。
- 页面能直接显示 `listing_report.md`。
- 页面能看到真实模型、provider、request_id、generation_status。
- live LLM 空包时，页面明确标记失败，不能把 fallback 结果伪装成正式完成。

### Phase 2：真值 Schema + 硬闸门产品化
目标：让 UI 跑出来的结果具备“能不能上架”的明确判定。

#### Stories
- 统一产品真值字段 schema
  - 从属性表、手动说明、历史快照抽取统一 truth object
- 强化 `risk_check.py`
  - 竞品词强拦截
  - 参数冲突强拦截
  - unsupported claim 强拦截
- 强化 `modules/llm_client.py`
  - healthcheck / probe / response metadata 结构统一
  - 明确区分 `live_success / live_with_fallback / live_failed / empty_packet`
- 强化 `modules/scoring.py`
  - 引入 `listing_status` 与生产就绪度总闸门

#### 关键文件
- 修改 `tools/preprocess.py`
- 修改 `modules/capability_check.py`
- 修改 `modules/risk_check.py`
- 修改 `modules/scoring.py`
- 修改 `modules/report_generator.py`
- 修改 `modules/llm_client.py`

#### 验收标准
- 若文案出现真值冲突，状态必须为 `NOT_READY_FOR_LISTING`。
- 若 live LLM 返回空包，必须显示原因与 request_id，并阻断正式状态。
- 报告三段式仍保留，但新增“最终状态”和“阻断原因”。

### Phase 3：SellerSprite 解析 + 人机共审反补链路
目标：先做可控的数据入口，再谈策略吸收。

#### Stories
- 新增 `modules/csv_parser.py`
  - 自动兼容 CSV / XLSX
  - 尽量识别 SellerSprite 常见列名：关键词、流量来源、搜索量、转化率、订单占比、PPC/SP 标识
- 新增 `modules/feedback_loop.py`
  - 把运营勾选后的关键词落成标准结构：
    - `organic_core`
    - `sp_intent`
    - `backend_only`
    - `blocked_terms`
- Tab 2 前端联调
  - 读取本地已有产品目录
  - 上传反补词表
  - 渲染勾选表
  - 默认对竞品词/乱码/低质量词取消勾选并高亮
- 反补记录持久化
  - 每次审批保存到 `workspace/<product>/feedback/feedback_<date>.json`

#### 关键文件
- 新增 `modules/csv_parser.py`
- 新增 `modules/feedback_loop.py`
- 新增 `app/components/feedback_grid.py`
- 修改 `app/streamlit_app.py`
- 修改 `tools/data_loader.py` 或新增专用 loader

#### 验收标准
- 运营能在网页上完成出单词审批，而不是回 Excel 手工处理。
- 系统能自动标红竞品词、异常词、乱码词。
- 确认后的词表能形成结构化反馈快照，供后续生成使用。

### Phase 4：Retention + 意图翻译 + 动态改写
目标：实现真正的“老品安全迭代”。

#### Stories
- 新增 `modules/retention_guard.py`
  - 从历史最佳版本 / 上一版中提取 Top 自然流量词
  - 计算 Title + L1 Bullets 留存率
  - 若 Top 5 自然词丢失过多，直接阻断
- 扩展 `modules/intent_translator.py`
  - 将 `sp_intent` 词表翻译为标准 Intent Node
  - 例如 `ski camera / helmet mount / bike helmet cam` -> `winter_sports_capture / helmet_mount_stability / cycling_pov`
- 扩展 `modules/writing_policy.py`
  - 支持来自反补词表的强制 bullet 主题
  - 支持“某一槽位必须覆盖某一场景”的契约
- 扩展 `modules/blueprint_generator.py`
  - 把 retention 和新 intent 一起纳入 blueprint
- 扩展 `modules/copy_generation.py`
  - 前端文案优先保 Organic Core
  - SP Intent 只在可造句、真值支持、风险可控的条件下进入 visible copy
  - Ugly Terms 仅进入 Search Terms

#### 关键文件
- 新增 `modules/retention_guard.py`
- 修改 `modules/intent_translator.py`
- 修改 `modules/writing_policy.py`
- 修改 `modules/blueprint_generator.py`
- 修改 `modules/copy_generation.py`
- 修改 `modules/risk_check.py`
- 修改 `modules/scoring.py`

#### 验收标准
- 老品反补后，系统能说明：
  - 哪些历史自然词被保住了
  - 哪些广告词转译成了什么意图
  - 哪些词仅进入 Search Terms
  - 为什么某些词被拒绝进入 visible copy
- 若丢失 Top 自然词，则状态必须为 `NOT_READY_FOR_LISTING`。

## 7. 数据结构建议

### 产品工作区配置 `product_config.json`
```json
{
  "product_code": "T70",
  "site": "FR",
  "brand_name": "TOSBARRFT",
  "workspace_dir": "workspace/T70_FR",
  "input_files": {
    "attribute_table": "inputs/attribute.xlsx",
    "keyword_table": "inputs/keywords.xlsx",
    "aba_merged": "inputs/aba.xlsx",
    "review_table": "inputs/reviews.csv"
  },
  "manual_notes": "...",
  "created_at": "2026-04-11T00:00:00Z"
}
```

### 反馈快照 `feedback_*.json`
```json
{
  "product_code": "T70",
  "site": "FR",
  "source_file": "feedback/sellersprite_2026-04-11.xlsx",
  "approved_keywords": {
    "organic_core": [],
    "sp_intent": [],
    "backend_only": [],
    "blocked_terms": []
  },
  "operator_notes": "...",
  "saved_at": "2026-04-11T00:00:00Z"
}
```

## 8. UI 交互细节建议

### Tab 1：新品上架
- 左侧输入：国家 / 品牌 / 产品代号 / 4 文件上传 / 补充说明
- 右侧输出：
  - 运行状态
  - LLM 状态卡片
  - 报告预览
  - 文件按钮：下载报告 / 打开工作区 / 查看最近 run

### Tab 2：老品反补
- 顶部选择器：产品工作区
- 中部上传区：SellerSprite 词表
- 下方数据网格：
  - `keep`
  - `keyword`
  - `source`
  - `search_volume`
  - `conversion`
  - `suggested_slot`
  - `risk_flag`
  - `reason`
- 底部动作：
  - 保存反馈快照
  - 基于已勾选词重构 Listing

## 9. 必须新增的测试集

### 单测
- `tests/test_csv_parser.py`
  - SellerSprite 常见列名兼容
  - Organic / SP 识别
  - 脏词 / 竞品词识别
- `tests/test_retention_guard.py`
  - Top 自然词留存率计算
  - 触发阻断阈值
- `tests/test_feedback_loop.py`
  - 勾选结果到分层词池的结构化输出

### 集成测试
- `tests/test_streamlit_services.py`
  - 新品初始化 -> 工作区建档 -> workflow 触发
  - 反馈快照 -> 增量策略 -> 重构执行

### 回归测试
- 保留现有：
  - `tests/test_copy_generation.py`
  - `tests/test_locale_and_supplement.py`
  - `tests/test_production_guardrails.py`

## 10. 风险点与规避

- Streamlit 不适合承接重型长任务 stdout
  - 规避：service 层返回结构化状态，不依赖 UI 解析 print。
- SellerSprite 列名不稳定
  - 规避：先做 alias 字典，再做模糊识别。
- 老品反补容易把广告噪音带进前台文案
  - 规避：反补词必须先经过 parser -> operator approval -> truth/risk gate。
- CRS `gpt-5.4` 网关偶发空包
  - 规避：UI 显示 live healthcheck；正式状态以 metadata + output completeness 双条件为准。

## 11. 推荐执行顺序
按实际收益和依赖关系，建议不是严格按 PRD 的自然语言顺序开发，而是按下面顺序：

1. Phase 1：先把 Streamlit 控制台跑起来。
2. Phase 2：把状态机、truth gate、LLM gate 做硬。
3. Phase 3：再接 SellerSprite 与人工审批。
4. Phase 4：最后做 retention + intent-driven rewrite。

原因：
- 没有 Phase 1，业务无法直观看到系统价值。
- 没有 Phase 2，UI 只是把风险更快暴露，不适合生产使用。
- 没有 Phase 3，Tab 2 只是空壳。
- 没有 Phase 4，老品反补仍只是“导词”，不是“算法驱动增长”。

## 12. 本轮建议的首批开发包
如果现在立刻开始动手，我建议第一批直接做下面 8 项：

- 加 `streamlit` 依赖与启动入口
- 建 `app/streamlit_app.py`
- 建 `workspace_service.py`
- 建 `run_service.py`
- 抽 `main.py` 的可复用 workflow 调用
- 把 report / metadata 输出整理成 UI 可消费结构
- 加 `listing_status.py`
- 补一组最小集成测试，先保证 Tab 1 MVP 闭环

这 8 项完成后，系统就从“脚本”进入“产品”阶段。
