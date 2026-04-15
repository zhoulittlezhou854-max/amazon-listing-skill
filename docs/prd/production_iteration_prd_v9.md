# Amazon Listing Skill 生产化迭代 PRD v9.0

## 1. 文档目标

本 PRD 用于指导 `amazon-listing-skill` 从“可运行的实验型 Listing 生成管线”升级为“可审计、可追溯、可用于产品上架前人工收口的生产级系统”。

本文档覆盖：

- 现状问题与生产化目标
- 分阶段迭代范围
- 文件级改造清单
- 每阶段验收标准
- 执行顺序与交付物

## 2. 背景

当前项目已经具备如下主流程能力：

- Step 0 数据预处理
- Step 1 视觉审计
- Step 2 关键词军火库
- Step 3 能力熔断与合规检查
- Step 4 COSMO 意图图谱
- Step 5 writing_policy 生成
- Step 6 文案生成
- Step 7 风险检查
- Step 8 算法评分
- Step 9 报告生成

但现阶段系统仍存在以下生产阻断问题：

- live LLM 失败时会落入 simulated / mock copy，导致报告看似完整但并非真实模型输出
- 报告未明确区分 live success、live with fallback、offline/simulated
- 属性真值层与能力判断字段未统一，导致 4K / Wi-Fi / EIS / 防水 / 续航等能力误判
- 默认 4 场景模板仍是正式路径，策略层未充分使用真实关键词与评论信号
- 评分与可信度摘要尚未把“模型真实性”和“上架就绪状态”纳入硬门槛

## 3. 产品目标

### 3.1 总目标

跑出来的报告结果必须满足以下条件：

- 文案由 live GPT-5.4 路由真实生成，且可在报告中审计
- 文案基于属性真值与补充约束，不编造、不越权宣称
- 文案符合亚马逊底层逻辑，兼顾高流量词覆盖与转化驱动表达
- 报告能清晰标记该版本是：
  - `READY_FOR_LISTING`
  - `READY_FOR_HUMAN_REVIEW`
  - `NOT_READY`

### 3.2 生产定义

“生产级”在本项目中的定义不是完全无人值守，而是：

- 任何失败都不伪装成成功
- 任何可见宣称都可追溯到真值层
- 任何 fallback 都可审计
- 任何未通过风险门槛的结果都不会被误标为可上架版本

## 4. 非目标

本轮 v9.0 迭代不包含：

- 完整的多模态视觉识别训练体系
- A+ 图片自动生成
- PPC 数据闭环自动回写
- 100% 无人工参与的上架自动化

这些能力保留为后续 v9.x / v10.x 规划。

## 5. 核心原则

### 5.1 真实性优先

- 不能把 simulated 结果包装成 live GPT-5.4 结果
- 报告必须显示模型路由与返回状态

### 5.2 真值优先

- 属性表与补充文件构成参数真理层
- 任何可见字段中的能力都必须被真值层支持

### 5.3 审计优先

- 生成状态、删改行为、fallback、风险结论必须可回溯

### 5.4 亚马逊逻辑优先

- 关键词布局不只追求覆盖，还要考虑位置、权重与转化表达
- 文案不只是“堆参数”，而要体现购买场景、痛点与证据

## 6. 版本迭代总览

本次生产化改造分三阶段执行。

### v9.1 补充迭代：跨站统一生产版

在 v9.0 的基础上，新增一轮“跨站统一生产版”收口，目标是让 FR / DE / EN 都走同一条可审计、可配置、可直接用于亚马逊后台的正式链路。

新增目标：

- FR / DE / EN 运行配置统一切到 `gpt-5.4 + CRS openai-compatible + codex exec fallback`
- 三站点统一输出 3 段式生产报告：
  - `Part 1：运营部分`
  - `Part 2：系统部分`
  - `Part 3：诊断与优化部分`
- 关键词清洗逻辑从法语回归到德语 / 英语，避免：
  - 竞品品牌污染
  - 子品类错配（如 camera glasses / mini phone / spy cam）
  - 场景代码直接写入 Search Terms
  - 未支持能力词误写入最终亚马逊后台字段
- COSMO 从“静态四场景”继续升级为“品类感知 + 场景剧本 + 购买驱动”模式：
  - Action Camera
  - Wearable / Body Camera
  - 后续可继续扩到更多 3C 子品类

### v9.1 文件级要求

- `config/run_configs/T70_real_FR.json`
- `config/run_configs/T70_real_DE.json`
- `config/run_configs/H91lite_US.json`
  - 统一 CRS `gpt-5.4` 生产配置

- `modules/keyword_utils.py`
  - 新增子品类识别（`action_camera` / `wearable_body_camera`）
  - 扩展多语言关键词正负样本过滤
  - 增补竞品/品牌噪声阻断

- `modules/writing_policy.py`
  - 场景提取由“松散关键词命中”升级为“标准场景别名归一”
  - 去除 `vlog_camera` 这类原始代码式场景泄漏
  - 产品战略侧写改为按品类动态生成

- `modules/intent_translator.py`
  - 新增 wearable/body camera 的 COSMO scene playbook
  - STAG 改为按品类输出不同广告分组建议

- `modules/copy_generation.py`
  - Search Terms 停止注入 backend-only 能力词
  - 标题优先承载 2 个高价值 L1 关键词（可容纳时）
  - Bullet LLM 提示增加 forbidden visible terms，减少 unsupported capability 泄漏

- `tests/test_locale_and_supplement.py`
  - 增加跨站生产守护测试，锁定关键词清洗、场景归一和 backend-only 搜索词禁注入

### 阶段 1：LLM 真实性与运行闸门

目标：先解决“必须真跑 GPT-5.4，不能再假装成功”

范围：

- live LLM 健康检查
- 请求/响应元数据审计
- simulated/mock copy 退出正式链路
- 报告新增真实性与 readiness 标记

交付结果：

- 生产报告可以明确区分 live success / live with fallback / failed
- offline / simulated 不再被误判为正式可上架结果

### 阶段 2：真值层与合规层升级

目标：解决“文案必须可信，不能乱宣称”

范围：

- 属性字段标准化
- supplement 结构化提取
- capability check 重构
- risk gate 强化

交付结果：

- visible claim 100% 可追溯
- 条件型能力可自动降级到 FAQ / backend / boundary

### 阶段 3：策略层与文案层升级

目标：解决“文案要更符合亚马逊底层逻辑，更有流量与购买力”

范围：

- 从默认四场景模板切到动态策略
- traffic / conversion 双目标关键词路由
- bullet blueprint 约束化
- copy generation 槽位化

交付结果：

- 文案更接近真实可上架 Listing
- 报告能解释高流量词与高转化表达的平衡逻辑

## 7. 阶段 1 详细范围

### 7.1 改造目标

- 当 `force_live_llm=true` 时，系统必须先通过 live 健康检查
- Step 6 不再产出整段 mock copy
- 报告首页必须展示真实性审计信息
- 报告必须新增 `Listing Readiness` 状态

### 7.2 文件级任务清单

#### A. `modules/llm_client.py`

责任：

- 管理第三方 OpenAI-compatible / OpenAI / DeepSeek 路由
- 为下游提供统一的真实性元数据

改造项：

- 新增 `healthcheck()` 能力，执行最小 live 探测
- 为每次真实请求记录：
  - `configured_model`
  - `returned_model`
  - `provider`
  - `wire_api`
  - `base_url`
  - `request_id`
  - `response_id`
  - `latency_ms`
  - `success`
  - `error`
- 暴露 `response_metadata` / `healthcheck_status`
- 日志中禁止泄露 API key

验收标准：

- live 请求成功后，元数据可被 copy/report 读取
- route 不可用时，能在生成前返回明确错误

#### B. `main.py`

责任：

- 负责主流程 orchestration
- 负责 live gate 与失败终止策略

改造项：

- 初始化时执行 LLM healthcheck
- `force_live_llm=true` 且 healthcheck 失败时直接中断
- Step 6 删除整段 simulated mock copy 的正式返回
- Step 6 返回中增加：
  - `generation_status`
  - `llm_metadata`
- 工作流在关键步骤 error 时中止后续正式产出

验收标准：

- 正式 run 中不再出现 `step_6.status=simulated`
- Step 6 失败时不会继续产出伪正式报告

#### C. `modules/copy_generation.py`

责任：

- 将每次字段生成的结果封装为最终 Listing 文案
- 汇总 live/fallback 状态写入 metadata

改造项：

- 汇总 LLM response metadata 到 `generated_copy.metadata`
- 统计 `llm_fallback_count`
- 输出 `generation_status`：
  - `live_success`
  - `live_with_fallback`
  - `offline`
- 输出 `llm_healthcheck`

验收标准：

- `generated_copy.json` 能完整说明本次文案的生成真实性

#### D. `modules/report_generator.py`

责任：

- 生成最终仲裁报告
- 标记结果是否可用于上架前收口

改造项：

- 首页新增 `Listing Readiness`
- 首页新增 `Generation Authenticity`
- `Data Ingestion Audit` 增加：
  - configured model
  - returned model
  - wire api
  - request id
  - generation status
- `评分可信度摘要` 纳入真实性校验，非 live success 不得标记为“评分可信”

验收标准：

- 报告中能一眼看出该结果是不是 GPT-5.4 live 生成
- simulated / offline / partial fallback 会导致 readiness 降级

#### E. `docs/prd/production_iteration_prd_v9.md`

责任：

- 持续记录生产化迭代范围
- 作为后续阶段开发依据

改造项：

- 本轮创建并维护本文档

验收标准：

- 文档内容与当前实现保持同步

### 7.3 阶段 1 Ready 判定逻辑

报告层 readiness 采用以下规则：

- `READY_FOR_LISTING`
  - `generation_status == live_success`
  - `risk_report.overall_passed == true`

- `READY_FOR_HUMAN_REVIEW`
  - `generation_status == live_with_fallback`
  - 或风险未完全通过但文案已完成真实 live 生成

- `NOT_READY`
  - `generation_status == offline`
  - 或 Step 6 failed
  - 或未通过 live 健康检查

## 8. 阶段 2 详细范围

### 8.1 目标

把“可见文案 = 真值支持 + 条件明确 + 风险可控”落实到代码结构。

### 8.2 文件级任务

#### A. `tools/preprocess.py`

- 增加属性字段标准化层
- 结构化提取 supplement：
  - runtime
  - waterproof condition
  - stabilization limits
  - accessories
  - mounting modes

#### B. `modules/capability_check.py`

- 从展示型规则改为真值驱动规则
- 输出：
  - `allowed_visible`
  - `allowed_with_condition`
  - `faq_only`
  - `forbidden`

#### C. `modules/risk_check.py`

- 增加 unsupported claim 检查
- 增加条件型能力边界声明检查
- 增加语言一致性检查
- 增加 backend / taboo / competitor 清洗审计

验收标准：

- 任何 visible claim 都能从 `preprocessed_data` 追溯回原始证据

## 9. 阶段 3 详细范围

### 9.1 目标

把文案逻辑从模板化，升级为“高流量词 + 转化驱动 + 亚马逊底层逻辑”的结构化生成。

### 9.2 文件级任务

#### A. `modules/writing_policy.py`

- 主流程改用 `generate_policy()`
- 默认四场景模板仅作为 debug fallback
- 引入 traffic / conversion 双目标路由

#### B. `modules/keyword_arsenal.py`

- 区分：
  - traffic keywords
  - conversion keywords
  - backend only terms
  - taboo / competitor terms

#### C. `modules/intent_translator.py`

- 把 scene 扩展为 persona + pain point + buying trigger

#### D. `modules/blueprint_generator.py`

- 每条 bullet 输出固定结构：
  - scene
  - persona
  - pain point
  - proof
  - assigned keywords
  - forbidden mentions

#### E. `modules/copy_generation.py`

- 将 Title / Bullets / Description / FAQ / Search Terms 拆为字段级 contract
- 强化亚马逊逻辑：
  - Title 做索引
  - Bullets 做购买力
  - FAQ 消化限制
  - Search Terms 做残余词布局

验收标准：

- 最终文案接近真实可上架版本，而非模板说明书

## 10. 测试策略

### 10.1 单元测试

- `tests/test_llm_runtime.py`
- `tests/test_listing_readiness.py`
- `tests/test_copy_generation.py`
- `tests/test_compliance_audit.py`
- `tests/test_locale_and_supplement.py`

### 10.2 黄金样本回归

建议覆盖：

- FR 运动相机
- DE 运动相机
- US 穿戴/记录设备
- 有 runtime / 无 runtime
- 有 accessories / 缺 accessories
- 有防水壳条件 / 无壳条件

## 11. 风险与应对

### 风险 1：第三方路由行为不完全兼容

应对：

- `modules/llm_client.py` 做兼容层封装
- 不把第三方路由直接等同于官方 API

### 风险 2：字段标准化耗时较长

应对：

- 优先覆盖当前主产品 T70 / H91 的高频字段
- 后续逐步扩展

### 风险 3：live 成功但部分字段 fallback

应对：

- 不隐藏 fallback
- readiness 降级到 `READY_FOR_HUMAN_REVIEW`

## 12. 执行顺序

按以下顺序依次实施：

1. `docs/prd/production_iteration_prd_v9.md`
2. `modules/llm_client.py`
3. `main.py`
4. `modules/copy_generation.py`
5. `modules/report_generator.py`
6. 阶段 1 验证
7. 阶段 2 开工
8. 阶段 3 开工

## 13. 本轮迭代完成定义

本轮完成定义为：

- 已新增并保存生产化迭代 PRD
- 已落地 live runtime healthcheck
- 已移除 Step 6 正式 simulated mock copy 出口
- 已在报告中加入真实性和 readiness 状态
- 已通过至少一轮本地静态校验
