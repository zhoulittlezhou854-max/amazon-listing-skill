
Amazon Listing Generator
可复刻 PRD — v8.4.0
A. PRD 摘要
项目        内容
文档版本        v8.4.0
文档用途        在 Refly 之外的平台完整复刻本工作流，所有逻辑显式展开
适用平台        Claude Code / 本地 Python 脚本工作流 / 任何支持 LLM API 调用的编排框架
原始平台        Refly.ai，画布标题 "Amazon listing 8.4.0"，Plan ID wp-gpykiek741yze0jdo4pcdhqx
版本演进        v8.1（基础文案）→ v8.3.5（writing_policy + 算法评分）→ v8.4.0（定向读取 + capable_of + Rule 3b/6 + 价格评分细化）
版本改进对照：

版本        新增内容
v8.1        基础 Title/Bullets/Description/FAQ/ST 生成；无 writing_policy；无算法评分
v8.3.5        writing_policy（5子字段）；Module 8 算法评分（A10/COSMO/Rufus）；全局中文声明；Node 4 上游引用修复
v8.4.0        算法规则库定向读取指令（各节点按章节编号读取）；capable_of 第4类关联；Rule 3b 边界声明强制；Rule 6 A+字数下限；价格竞争力评分5档细化；Module 8 逐维度明细表输出；防抬分声明
B. 输入定义
共 12 个输入项，8 个文件类，4 个文本类。

B-1. ABA 关键词数据
属性        内容
输入名称        ABA 关键词数据
变量 ID        var-aba-csv
输入类型        CSV 文件，UTF-8 编码，逗号分隔，必须有表头行
是否必填        是
作用        核心关键词来源。用于 L1/L2/L3 三级分级、Score/AdScore 计算、[🔥High-Conv] 标记、军火库构建、语种自动检测兜底
必须包含的字段（语义匹配，列名可不同）        关键词列（keyword/搜索词/search_term）；月搜索量列（search_volume/月搜索量/搜索量）；转化率列（conversion_rate/购买率/转化率）；ABA排名列（ABA月排名/aba_rank，可选）
缺失时处理        终止执行，输出错误：MISSING_REQUIRED_INPUT: aba_keywords，不生成任何 Listing
优先级        P3（数据层，低于规则层 P1/P2，高于辅助层 P4）
是否允许被覆盖        否。ABA 数据是关键词分级的唯一来源，不可被其他输入替代
已知问题        当前 Refly 版本中，文件挂载与目标站点可能不一致（如运行 DE 站时挂载了 FR 站文件）。复刻时必须在输入校验阶段检查文件名/内容语言与 site 参数的一致性
B-2. 竞品出单词报告
属性        内容
输入名称        竞品出单词报告
变量 ID        var-competitor-csv
输入类型        CSV 文件，UTF-8 编码，逗号分隔，必须有表头行
是否必填        是（标注必填，但当前 Refly 版本实际未被有效读取——见 H 节）
作用        三个用途：① 蓝海词挖掘（月购买量高但搜索量低的词）；② 竞品品牌提取（用于 Title/ST 禁用词列表）；③ price_context 提取（品类价格中位数，供 Node 8 价格竞争力评分使用）
必须包含的字段        关键词列；均价列（均价/avg_price/price）；购买率列（购买率/conversion_rate）；月购买量列（月购买量/monthly_purchases）；竞品数列（竞品数/商品数/competitor_count）
实际文件结构（已读取）        第一列为文件名（非字段名，数据全空）；字段包括：关键词/标签/AC推荐词/ABA月排名/ABA周排名/月搜索量/月购买量/购买率/展示量/点击量/SPR/标题密度/商品数/需供比/广告竞品数/点击总占比/转化总占比/货流值/PPC竞价/建议竞价范围/均价/评分数/评分值/所属类目/国家/型号
缺失时处理        跳过竞品分析和 price_context 提取；Node 8 价格竞争力评分标注"数据缺失，跳过评分"，不计入总分分母；在 audit_trail 的 missing_inputs 中记录
优先级        P3
是否允许被覆盖        否
B-3. 本品属性表
属性        内容
输入名称        本品属性表
变量 ID        var-specs-txt
输入类型        TXT 文件，UTF-8 编码，键值对格式（参数名: 参数值，每行一条）
是否必填        是
作用        产品参数的绝对真理来源。用于：① 能力熔断（过滤不可宣传的能力）；② verified_specs 生成；③ capability_tiers（P0/P1/P2）划分；④ 禁止编造未在此文件中出现的参数
建议格式        品牌: TOSBARRFT、分辨率: 5K/4K/1080P、防抖: EIS（仅1080P和4K支持，5K不支持）、防水: 配件防水壳支持30M、屏幕: 双屏幕、连接: WiFi、电池: 1350mAh
缺失时处理        终止执行，输出错误：MISSING_REQUIRED_INPUT: product_specs。无属性表则无法执行能力熔断，参数存在被编造的风险
优先级        P0（最高优先级，绝对真理层）。与任何其他输入冲突时，以本品属性表为准
是否允许被覆盖        不允许被覆盖。参数补充（B-4）只能补充缺失字段，不能修改已有参数
B-4. 参数补充
属性        内容
输入名称        参数补充
变量 ID        var-specs-supplement
输入类型        文本（字符串），自由格式，建议用分号或换行分隔多条信息
是否必填        否
作用        补充本品属性表中未覆盖的参数约束，尤其是"不建议宣传"类说明。当前示例值："只有1080P和4K模式支持防抖，5K模式不支持防抖。1080P下的防抖效果比4K好。不建议突出宣传在4K和5K下的防抖。产品配件带防水壳支持30M防水，磁吸配件可挂脖或者吸附各种金属表面，其他固件可固定在车把或者头盔上"
对能力熔断的影响        含"不建议突出宣传"的能力 → 列入 faq_only_capabilities；含"不支持"的功能 → 列入 forbidden_capabilities；含参数限制说明 → 列入 parameter_constraints
缺失时处理        仅依赖本品属性表执行熔断，在 audit_trail 的 optional_missing 中记录
优先级        P0（与本品属性表同级，作为补充）
是否允许被覆盖        否。参数补充与本品属性表共同构成参数真理层
B-5. 产品全维度表
属性        内容
输入名称        产品全维度表
变量 ID        var-full-dimension-csv
输入类型        CSV 文件，UTF-8 编码
是否必填        是（标注必填，但当前 Refly 版本实际未被有效读取——见 H 节）
作用        提供 Review Insights（差评关键词、高频痛点）和 Rufus Log（用户高频问题）。用于：① Node 3 竞品痛点分析；② Node 7 FAQ 生成的问题来源；③ Node 8 Rufus faq_coverage 评分依据
必须包含的字段        差评关键词列（负面情感词）；Rufus高频问题列（用户问答日志）；评分分布列（1-5星各占比）
缺失时处理        跳过 Review 痛点分析；FAQ 生成退化为基于属性表推断；在 audit_trail 的 missing_inputs 中记录
优先级        P3
是否允许被覆盖        否
B-6. 产品主图
属性        内容
输入名称        产品主图
变量 ID        var-product-images
输入类型        图片文件（JPG/PNG），支持多张（isSingle: false）
是否必填        是
作用        视觉审计节点的唯一输入。提取：visual_tags（使用场景/材质/设计特征/接口细节）；mount_visuals（挂载方式）；usage_context_hints（使用场景推断）；compliance_flags（合规检查）
当前挂载文件        7张图片：11.jpg / 9.jpg / 10.jpg / 8.jpg / 16.jpg / 13.jpg / 15.jpg
缺失时处理        跳过视觉审计节点；visual_tags 在 strategy_profile 中标注为空；在 audit_trail 的 missing_inputs 中记录；不影响文案生成，但 COSMO 场景覆盖评分可能降低
优先级        P4（辅助层）
是否允许被覆盖        否
B-7. 算法规则库
属性        内容
输入名称        算法规则库
变量 ID        var-algorithm-rules
输入类型        TXT 文件（v1.0 为 XML 三段式结构；v2.0 为 Markdown 章节结构，第一章～第十四章 + 附录A/B）
是否必填        是
作用        为 Node 3/6/7/8 提供算法规则依据。各节点按章节编号定向读取，不泛读全文
各节点读取章节映射        Node 3：第八章（L1-L3矩阵）+ 第一章1.2节 + 第一章1.3节；Node 6：第一章1.2节 + 第二章 + 第四章 + 第十二章 + 附录A；Node 7：第三章 + 第四章 + 第七章 + 第十三章 + 附录A/B；Node 8：第一章1.3节 + 第三章 + 第八章 + 第十二章 + 附录B
v1.0 → v2.0 章节映射        A10_Core_Strategy第5.2节 → 第三章3.1节；COSMO_Deep_Dive第2.4节 → 第一章1.2节；Rufus_AEO_Guide L1-L3矩阵 → 第八章8.1节；Rufus Score权重模型 → 第一章1.3节
缺失时处理        终止执行。算法规则库是评分和文案约束的核心依据，缺失时无法保证输出质量
优先级        P1（规则层，高于数据层 P3）
是否允许被覆盖        否
已知问题        在 Refly 的 execute_code 沙箱中，Python 代码无法访问 LLM 上下文中的文件内容，导致 Node 3 实际未读取算法规则库。复刻时需将规则内容直接注入 prompt 上下文
B-8. 合规规则库
属性        内容
输入名称        合规规则库
变量 ID        var-compliance-rules
输入类型        TXT 文件，XML 结构化
是否必填        是
作用        提供违禁词清单、风格指南、侵权品牌库。用于 Node 6（taboo_concepts 生成）、Node 7（文案合规检查）、Node 8（Module 3 合规红线检查）
缺失时处理        警告继续执行，在 risk_flags 中标注"合规规则库缺失，输出未经合规验证"
优先级        P2（合规层，高于数据层 P3）
是否允许被覆盖        否
B-9. 运动相机合规规则库
属性        内容
输入名称        运动相机合规规则库
变量 ID        var-compliance-actioncam
输入类型        TXT 文件，XML 结构化
是否必填        否（required: false）
作用        运动相机品类专用合规规则，补充通用合规规则库。包含：执法场景禁用词（police/law enforcement）；未包含配件声明规则；隐蔽拍摄相关合规限制
缺失时处理        静默跳过，仅使用通用合规规则库，在 audit_trail 的 optional_missing 中记录
优先级        P2
是否允许被覆盖        否
B-10. 目标市场
属性        内容
输入名称        目标市场
变量 ID        var-target-country
输入类型        下拉选项（option 类型，单选）
是否必填        是
可选值        🇺🇸 US / 🇬🇧 UK / 🇩🇪 DE / 🇫🇷 FR / 🇪🇸 ES / 🇮🇹 IT / 🇯🇵 JP / 🇨🇦 CA / 🇦🇺 AU / 🇲🇽 MX
作用        驱动语种初始化（US/UK/CA/AU→English；DE→German；FR→French；ES→Spanish；IT→Italian；JP→Japanese；MX→Spanish）；驱动 Search Term 字节限制（JP 站为 500 bytes，其他站为 250 bytes）
缺失时处理        从 ABA CSV 的关键词语言特征自动检测语种（兜底逻辑）
优先级        P4（辅助层，但语种初始化依赖此项）
是否允许被覆盖        否
B-11. 品牌名称
属性        内容
输入名称        品牌名称
变量 ID        var-manual-brand
输入类型        文本（字符串）
是否必填        是
作用        强制植入 Title 开头；用于竞品关键词排除（品牌词不得出现在 Search Terms）；用于导出文件命名（Amazon_Listing_{brand}_v840.docx）
当前示例值        TOSBARRFT
缺失时处理        终止执行，输出错误：MISSING_REQUIRED_INPUT: brand_name
优先级        P0（品牌名是 Title 的强制首位元素）
是否允许被覆盖        否
B-12. 核心卖点
属性        内容
输入名称        核心卖点
变量 ID        var-selling-points
输入类型        文本（字符串）
是否必填        否
作用        为 Node 7 文案生成提供卖点方向参考。当前示例值："双屏幕，支持EIS防抖，可WI-FI连接手机"
缺失时处理        从本品属性表和 writing_policy 推断卖点，在 audit_trail 的 optional_missing 中记录
优先级        P4
是否允许被覆盖        可被本品属性表覆盖。若卖点与属性表参数冲突，以属性表为准
C. 输出定义
共 10 个输出项。

C-1. 关键词军火库
属性        内容
输出名称        关键词军火库（arsenal_output）
输出格式        JSON 文件（v81_arsenal_output.json）
生成节点        Node 3（Python 工程核心）
必须包含的字段        site（站点代码）；language（语种）；circuit_breaker_applied（能力熔断是否执行）；parameter_constraints（参数约束列表）；reserve_keywords（关键词列表，含 keyword/level/score/ad_score/search_volume/conversion_rate/high_conv）；competitor_brands（竞品品牌列表）；price_context（品类价格中位数，含 price_median/currency/sample_size）；review_pain_points（差评关键词列表）；rufus_high_freq_questions（Rufus高频问题列表）
生成标准        L1：search_volume ≥ 10,000；L2：1,000 ≤ search_volume < 10,000；L3：search_volume < 1,000 且意图明确；[🔥High-Conv]：conversion_rate ≥ 1.5% 或月购买量/搜索量比值显著高于品类均值
直接相关输入        ABA CSV（主要）；竞品 CSV（price_context + competitor_brands）；本品属性表 + 参数补充（parameter_constraints）；全维度表（review_pain_points）
是否附带审计        是。必须在 audit_trail 中记录哪些 CSV 文件被成功读取，哪些字段映射失败
C-2. 视觉审计结果
属性        内容
输出名称        视觉审计结果（visual_audit）
输出格式        JSON（内嵌在节点输出中）
生成节点        Node 2（视觉审计）
必须包含的字段        visual_tags（3-5个标签：使用场景/材质/设计特征/接口细节）；mount_visuals（挂载方式列表）；usage_context_hints（使用场景推断列表）；compliance_flags（合规检查结果列表）
生成标准        基于多模态视觉分析，不得编造图片中未出现的元素
直接相关输入        产品主图（唯一来源）
是否附带审计        否（但 compliance_flags 本身即为合规审计结果）
C-3. COSMO 意图图谱
属性        内容
输出名称        COSMO 意图图谱（intent_graph）
输出格式        JSON + Markdown 表格
生成节点        Node 4（意图转译引擎）
必须包含的字段        每个 High-Conv 词的：user_identity（谁在搜索）；purchase_intent（购买阶段：Awareness/Consideration/Decision）；pain_point（解决的问题）；stag_groups（3-5个场景分组，每组含 group_name/keywords/persona）
生成标准        基于军火库中前20个 [🔥High-Conv] 词执行意图分析
直接相关输入        军火库输出（reserve_keywords 中的 High-Conv 词）
是否附带审计        否
C-4. 产品战略侧写
属性        内容
输出名称        产品战略侧写（strategy_profile）
输出格式        JSON 文件
生成节点        Node 6（产品战略侧写师）
必须包含的字段        category_type；category_subtype；physical_form；form_details；primary_capabilities；capability_tiers（P0/P1/P2 三级）；primary_usage_scenarios；secondary_usage_scenarios；target_personas；competitive_advantages；taboo_concepts；verified_specs；writing_policy（含 scene_priority / capability_scene_bindings / faq_only_capabilities / forbidden_pairs / bullet_slot_rules）
writing_policy.capability_scene_bindings 必须覆盖四类 binding_type        used_for_func（功能关联）；used_for_eve（事件关联）；used_for_aud（受众关联）；capable_of（底层能力推理，v8.4.0新增）
生成标准        verified_specs 必须与本品属性表完全一致，禁止编造；faq_only_capabilities 必须包含 parameter_constraints 中的受限能力；四类 binding_type 必须全部覆盖，缺少须在 JSON 中标注原因
直接相关输入        军火库输出；视觉审计结果；意图图谱；本品属性表；参数补充；算法规则库（第一章1.2节/第二章/第四章/第十二章/附录A）；合规规则库；运动相机合规规则库
是否附带审计        是。必须在 writing_policy 中标注每个 capability_scene_bindings 条目的 binding_type
C-5. Listing 文案草稿
属性        内容
输出名称        Listing 文案草稿（listing_draft）
输出格式        JSON 或 Markdown
生成节点        Node 7（创意策略）
必须包含的字段        title（目标语言）；bullets（B1-B5，目标语言）；description（目标语言，plain text）；faq（5条Q&A，目标语言）；search_terms（目标语言，≤250 bytes）；aplus_content（目标语言，≥500字可索引正文）；self_check（8项自检结果）
生成标准        严格按 writing_policy 的 6 条硬性约束执行（Rule 1-6，详见 F 节）；8项自检全部通过后输出
直接相关输入        战略侧写（writing_policy 为核心约束）；军火库（关键词来源）；意图图谱（场景词来源）；视觉审计（挂载方式）；算法规则库（第三章/第四章/第七章/第十三章/附录A/B）；合规规则库；品牌名称；核心卖点
是否附带审计        是。必须附带 8 项自检清单结果
C-6. 最终仲裁报告
属性        内容
输出名称        最终仲裁报告（final_report）
输出格式        Markdown 文档（通过 generate_doc 工具生成）
生成节点        Node 8（最终仲裁者）
必须包含的模块        Module 1：最终 Listing（目标语言）；Module 2：关键词覆盖审计表；Module 3：合规红线检查；Module 4：writing_policy 执行审计（6条约束逐条结论）；Module 5：竞品差异化分析（3-5条）；Module 6：广告投放建议（STAG分组）；Module 7：Rufus Q&A 种子列表；Module 8：算法对齐评分详细表 + 《算法对齐摘要》
语言规范        所有说明性文字统一中文；仅 Listing 内容片段（Title/Bullets/Description/FAQ/ST）使用目标语言
直接相关输入        战略侧写；文案草稿；意图图谱；军火库（含 price_context）；算法规则库；合规规则库；品牌名称
是否附带审计        是。Module 8 必须输出逐维度得分明细表（含说明简述），不得只输出汇总分
C-7. Module 8 算法评分详细表
属性        内容
输出名称        算法评分详细表（scoring_detail）
输出格式        Markdown 表格（内嵌在最终仲裁报告 Module 8 中）
总分        310 分（A10: 100 + COSMO: 100 + Rufus: 100 + 价格竞争力: 10）
必须输出的表格        A10 维度表（title_front_80/keyword_tiering/conversion_signals + 小计）；COSMO 维度表（scene_coverage/capability_scene_binding/audience_tags + 小计）；Rufus 维度表（fact_completeness/faq_coverage/conflict_check + 小计）；价格竞争力表（品类中位数/当前定价/所在区间/实际得分）；v2.0 新增检查项（boundary_declaration_check + aplus_word_count_check）
每个维度必须包含        满分值；实际得分；说明简述（1句话，中文，点出得分原因）
防抬分要求        评分是对当前 Listing 的客观体检，不因 Listing 由本工作流生成而假设高分；如未满足规则必须如实扣分
直接相关输入        文案草稿；军火库（price_context）；算法规则库（第一章1.3节/第三章/第八章/第十二章/附录B）
是否附带审计        是。boundary_declaration_check 和 aplus_word_count_check 为强制输出字段
C-8. 《算法对齐摘要》
属性        内容
输出名称        算法对齐摘要
输出格式        Markdown 章节（最终仲裁报告末尾独立章节）
必须包含        评分汇总表（A10/COSMO/Rufus/价格竞争力 + 总计/310）；评级（90-100优秀/70-89良好/<70待优化）；各算法优化建议（每项2-3条可执行建议）；综合结论（2-3句话）
与 Module 8 的关系        汇总视图，不替代 Module 8 的逐维度明细表；两者必须同时输出
是否附带审计        否（本身即为审计结论）
C-9. 输出审计日志
属性        内容
输出名称        输出审计日志（audit_trail）
输出格式        JSON 文件
生成节点        贯穿全流程，最终由 Node 8 汇总
必须包含的字段        execution_time；site；language；brand；fields_used（实际使用的字段列表）；missing_inputs（缺失的必需输入）；optional_missing（缺失的可选输入）；used_docs（实际读取并使用的文档）；ignored_docs（存在但未被使用的文档，含原因）；risk_flags（发现的风险项）；boundary_declaration_check（存在/否 + 原文 + 得分影响）；aplus_word_count_check（字数 + 是否达标 + 得分影响）；l1_l2_l3_distribution（L1/L2/L3词在Title/Bullets/ST中的分布统计）
直接相关输入        全部输入
是否必须输出        是。每次执行必须生成 audit_trail，不可省略
C-10. Word 导出文档
属性        内容
输出名称        Word 文档
输出格式        .docx 文件
生成节点        Node 9（导出 Word 文档）
文件命名        Amazon_Listing_{brand}_{site}_v840.docx
必须包含        最终仲裁报告全部内容（Module 1-8）；算法对齐摘要；格式化表格和标题层级
生成标准        保存到新文件路径，不覆盖已有文件；使用 python-docx 或等价库
直接相关输入        最终仲裁报告；品牌名称
是否附带审计        否
D. 分阶段流程
共 5 个阶段，11 个步骤。

阶段一：输入初始化与校验
阶段目标：确认所有必需输入存在且格式正确，完成语种初始化，为后续阶段提供标准化的运行上下文。

输入：全部 12 个输入变量

处理逻辑：

步骤 1.1 — 必需输入校验

检查以下文件是否存在且非空：
- aba_keywords.csv
- product_specs.txt
- brand_name（文本变量）
- target_country（选项变量）
- algorithm_rules（规则库文件）
- compliance_rules（合规规则库文件）
  
如任一缺失：
→ 输出 MISSING_REQUIRED_INPUT: {input_name}
→ 终止执行，不进入后续阶段
步骤 1.2 — 语种初始化

读取 target_country 变量值，按以下映射表确定语种：
US → English | UK → English | CA → English | AU → English
DE → German | FR → French | ES → Spanish | IT → Italian
JP → Japanese | MX → Spanish

如 target_country 为空：
→ 读取 aba_keywords.csv 的关键词语言特征自动检测
→ 在 audit_trail 中标注 detection_method: auto_detected

输出：{ site, language_code, language_name, detection_method, brand }
步骤 1.3 — 站点与文件一致性校验

检查 aba_keywords.csv 和 competitor_words.csv 的文件名或内容语言
是否与 site 参数一致。

如不一致（如运行 DE 站但挂载了 FR 站文件）：
→ 在 risk_flags 中标注 SITE_FILE_MISMATCH: {file_name}
→ 不终止执行，但在 audit_trail 中记录警告
输出：normalized_input 对象（见 G 节）

失败兜底：必需输入缺失时终止；可选输入缺失时降级继续，在 audit_trail 记录

生效规则：doc_priority_rules（P0-P4 优先级层级）

阶段二：数据提取与关键词处理
阶段目标：从所有 CSV 和 TXT 输入中提取结构化数据，完成关键词分级、能力熔断、price_context 提取，输出关键词军火库。

输入：normalized_input；ABA CSV；竞品 CSV；本品属性表；参数补充；全维度表；算法规则库（第八章）

处理逻辑：

步骤 2.1 — CSV 字段语义映射

对每个 CSV 文件，按以下规则识别列名（不要求完全一致）：

ABA CSV 字段映射：
- 关键词列：keyword / 关键词 / search_term / 搜索词
- 搜索量列：search_volume / 月搜索量 / 搜索量 / volume
- 转化率列：conversion_rate / 购买率 / 转化率 / cvr
- 排名列：ABA月排名 / aba_rank / 月排名（可选）
  
竞品 CSV 字段映射：
- 关键词列：keyword / 关键词
- 价格列：均价 / avg_price / price（用于 price_context）
- 购买率列：购买率 / conversion_rate
- 月购买量列：月购买量 / monthly_purchases
- 竞品数列：竞品数 / 商品数 / competitor_count
- 注意：第一列若为文件名（列名与文件名相同），自动跳过
  
全维度表字段映射：
- 差评关键词列：差评关键词 / negative_keywords / 负面词
- 高频问题列：Rufus问题 / user_questions / 高频问题
- 评分列：评分值 / rating / 评分
  
映射失败时：在 audit_trail.ignored_docs 中记录该列，不终止执行
步骤 2.2 — L1/L2/L3 分级

依据算法规则库第八章，按以下阈值执行分级：
L1（一级核心词）：search_volume ≥ 10,000
  → 强制进入 Title / B1 / B2
L2（二级场景词）：1,000 ≤ search_volume < 10,000
  → 进入 B3-B5 / Search Terms
L3（三级长尾词）：search_volume < 1,000 且意图明确（含场景词/长尾修饰词）
  → 进入 Search Terms / Q&A
  → 禁止进入 Title

[🔥High-Conv] 标记条件（满足任一即标记）：
- conversion_rate ≥ 1.5%
- 月购买量/月搜索量 > 品类均值 × 1.5
步骤 2.3 — Score / AdScore 计算

Score = log10(search_volume + 1) × conversion_rate_normalized
  其中 conversion_rate_normalized = conversion_rate_value / 100

AdScore = Score × ad_relevance_factor
  其中 ad_relevance_factor 基于 ABA排名倒数（排名越高，因子越大）
  如无排名数据，ad_relevance_factor = 1.0

按 Score 降序排列，输出 reserve_keywords 列表
步骤 2.4 — 能力熔断

读取 product_specs.txt 和 specs_supplement.txt，提取：

parameter_constraints（参数约束）：
- 含"不支持"的功能 → 列入 forbidden_capabilities
- 含"不建议突出宣传"的能力 → 列入 faq_only_capabilities
- 含参数限制说明 → 列入 parameter_constraints
  
示例（基于当前产品）：
parameter_constraints = [
  "No stabilization for 5K",
  "1080P stabilization > 4K stabilization",
  "Avoid highlighting 4K/5K stabilization"
]
faq_only_capabilities = ["5K防抖", "4K防抖效果说明"]

circuit_breaker_applied = true（如有任何约束被触发）
步骤 2.5 — price_context 提取

从竞品 CSV 的均价列提取所有非空价格值
计算中位数（median）
输出：{
  "price_median": 69.99,
  "currency": "EUR",（从均价列的货币符号推断）
  "sample_size": 24
}

如均价列不存在或全空：
→ price_context = null
→ 在 audit_trail.missing_inputs 中记录
→ Node 8 价格评分标注"数据缺失，跳过评分"
步骤 2.6 — 竞品品牌提取

从竞品 CSV 的关键词列中识别品牌词（大写开头、非通用词）
输出 competitor_brands 列表
用于 Title/ST 生成时的禁用词过滤
步骤 2.7 — Review 痛点提取

从全维度表提取：
- review_pain_points：差评中高频出现的负面词（如"过热""虚标""断连"）
- rufus_high_freq_questions：Rufus日志中的高频用户问题
- rating_distribution：1-5星各占比
  
如全维度表未提供或字段映射失败：
→ review_pain_points = []
→ rufus_high_freq_questions = []
→ 在 audit_trail.missing_inputs 中记录
输出：keyword_pool 对象（见 G 节）；arsenal_output.json

失败兜底：

ABA CSV 解析失败 → 终止执行
竞品 CSV 解析失败 → 跳过竞品相关字段，继续执行
全维度表解析失败 → 跳过 Review

输出：keyword_pool 对象（见 G 节）；arsenal_output.json

失败兜底：

ABA CSV 解析失败 → 终止执行
竞品 CSV 解析失败 → 跳过 price_context / competitor_brands，继续执行，audit_trail 记录
全维度表解析失败 → 跳过 review_pain_points，继续执行，audit_trail 记录
能力熔断无法执行（属性表缺失）→ 终止执行
生效规则：field_mapping_rules；keyword_tiering_rules（L1/L2/L3 阈值）；doc_priority_rules（P0 属性表优先）

阶段三：战略建模
阶段目标：基于关键词军火库、视觉审计结果、意图图谱，生成产品战略侧写（strategy_profile），核心产出是 writing_policy——后续所有文案生成的强制约束层。

输入：arsenal_output.json；visual_audit.json；intent_graph.json；本品属性表；参数补充；算法规则库（第一章1.2节/第二章/第四章/第十二章/附录A）；合规规则库；运动相机合规规则库

处理逻辑：

步骤 3.1 — 读取算法规则库（定向）

仅读取以下章节，忽略其余内容：
- 第一章 1.2节：COSMO 四类核心关联逻辑
（used_for_func / used_for_eve / used_for_aud / capable_of）
- 第二章：A10 / COSMO / Rufus 三系统协同关系
- 第四章：五点描述优化规则
- 第十二章：Rufus 幻觉风险规避协议
- 附录A：COSMO 意图映射快查表
步骤 3.2 — capability_tiers 划分

基于本品属性表和参数补充，将产品能力分为三级：

P0（核心能力，必须进入 Title 和 B1/B2）：
- 产品最核心的差异化能力，有具体参数支撑
- 示例：磁吸挂载系统、双屏幕、EIS防抖（1080P/4K）
  
P1（重要能力，进入 B3/B4 和竞品对比）：
- 有竞品痛点对比价值的能力
- 示例：WiFi连接、防水壳30M防水、多种挂载配件
  
P2（辅助能力，进入 B5 和 FAQ）：
- 质保、售后、兼容性信息
- 示例：5K视频模式（无防抖，仅在FAQ说明）、配件兼容性
  
注意：faq_only_capabilities 中的能力不得进入 P0/P1
步骤 3.3 — writing_policy 生成

生成 writing_policy 对象，必须包含以下 5 个子字段：

1. scene_priority（场景优先级排序）
  - 基于 intent_graph 的 STAG 分组搜索量排序
  - 最高流量场景排第一，依次排列
  - 示例：["户外运动/骑行", "通勤安防", "旅行Vlog", "摩托车记录"]
    
2. capability_scene_bindings（能力场景绑定）
每个 P0/P1 能力必须声明：
  - capability：能力名称
  - binding_type：四类之一（必须全部覆盖）
  · used_for_func：功能性常识关联
    示例：EIS防抖 → 覆盖"运动稳定、骑行录像、防抖"节点
  · used_for_eve：事件/场合关联
    示例：磁吸挂载 → "骑行比赛""通勤记录""户外探险"
  · used_for_aud：受众群体关联
    示例：双屏幕 → "Vlogger""骑行爱好者""通勤族"
  · capable_of：底层能力推理（v8.4.0新增）
    示例：写"1350mAh电池支持约90分钟1080P录制"
    而非"长续航"；触发场景：用户问"能录多久？"
  - allowed_scenes：允许与该能力组合的场景列表
  - forbidden_scenes：禁止与该能力组合的场景列表
  示例：EIS防抖的 forbidden_scenes = ["5K视频"]
    
3. faq_only_capabilities（只能进FAQ的能力）
  - 来源：parameter_constraints 中"不建议突出宣传"的能力
  - 示例：["5K防抖说明", "4K防抖效果对比1080P"]
  - 这些能力禁止出现在 Title 或任何 Bullet
    
4. forbidden_pairs（绝对禁止同时出现的能力组合）
  - 来源：合规规则库 + parameter_constraints
  - 格式：[["能力A", "能力B"], ...]
  - 示例：[["5K视频", "防抖"], ["执法场景", "隐蔽拍摄"]]
    
5. bullet_slot_rules（B1-B5 强制内容规则）
每条必须有明确规则，不得为空：
  - B1：挂载系统/主场景 + P0能力 + 参数（大写开头短语）
  - B2：P0核心能力 + 量化参数（电池/分辨率/帧率）
  - B3：P1竞品痛点对比 + 场景词
  - B4：P1/P2能力 + 使用场景 + 边界声明句
  - B5：P2质保/售后/兼容性信息
步骤 3.4 — taboo_concepts 生成

合并以下来源的禁用概念：
- 合规规则库中的违禁词类别
- 运动相机合规规则库中的专项禁用（如 law_enforcement_context）
- parameter_constraints 中的 forbidden_capabilities
- 视觉审计 compliance_flags 中发现的风险项
  
输出 taboo_concepts 列表
输出：strategy_profile.json（含完整 writing_policy）

失败兜底：

capability_scene_bindings 无法覆盖某类 binding_type → 在 JSON 中标注原因，不强制补全，继续执行
writing_policy 某子字段为空 → 在 audit_trail.risk_flags 中标注，降级执行（文案生成时对应约束失效）
生效规则：COSMO 四类关联逻辑；能力熔断结果（parameter_constraints）；合规规则库

阶段四：文案生成
阶段目标：基于 writing_policy 的 6 条硬性约束，生成完整 Listing 文案（Title / B1-B5 / Description / FAQ / Search Terms / A+），并执行 8 项自检。

输入：strategy_profile.json（writing_policy 为核心约束）；arsenal_output.json；intent_graph.json；visual_audit.json；算法规则库（第三章/第四章/第七章/第十三章/附录A/B）；合规规则库；品牌名称；核心卖点；语种

处理逻辑：

步骤 4.0 — STEP 0：强制读取 writing_policy（生成任何文案前必须执行）

从 strategy_profile.json 读取 writing_policy，
在内部确认以下 6 条硬性约束全部加载：

Rule 1 — 场景优先级锁定
  严格按 scene_priority 顺序分配场景词
  最高优先级场景必须出现在 Title 和 B1
  禁止将低优先级场景提升至 Title

Rule 2 — 能力场景绑定
  每个能力只能与 allowed_scenes 中的场景组合
  严禁与 forbidden_scenes 中的场景同句出现

Rule 3 — forbidden_pairs 禁止
  forbidden_pairs 中的能力组合禁止在任何单条
  Bullet 或 Title 中同时出现

Rule 3b — 边界声明强制（v8.4.0新增）
  每个 Listing 必须含 ≥1 条边界声明句
  格式："Optimized for [场景A]; not engineered for [场景B]"
  建议放置位置：B4 或 B5
  违反 → Rufus conflict_check 维度 -10分

Rule 4 — faq_only 限制
  faq_only_capabilities 中的能力只能出现在 FAQ
  严禁写入 Title 或任何 Bullet

Rule 5 — Bullet 槽位强制
  严格按 bullet_slot_rules 填充 B1-B5
  每条必须满足对应槽位的强制内容规则

Rule 6 — A+ 字数下限（v8.4.0新增）
  A+ 可索引正文 ≥ 500字（英文）
  统计范围：所有模块正文（不含标题/alt text/表格表头）
  违反 → Rufus fact_completeness 维度 -15分
步骤 4.1 — 读取算法规则库（定向，按顺序执行）

执行顺序：第三章 → 第四章 → 第七章 → 附录B

第三章（标题优化规则）：生成 Title 时读取
第四章（五点描述优化规则）：生成 Bullets 时读取
第七章（图片与A+内容）：生成 A+ 文案时读取
第十三章（3C品类特殊规则与高频误区）：全程参考
附录A（COSMO意图映射快查表）：场景词选取时参考
附录B（Rufus幻觉风险规避速查表）：自检时参考
步骤 4.2 — Title 生成

格式：[Brand] + [L1关键词] + [最高优先级场景词] + [核心能力+参数] + [差异化特征]

约束：
- 品牌名必须在最前面
- 前80字符必须包含：品牌名 + 类目词 + L1能力词 + 最高优先级场景词
- 总字符数 ≤ 200 chars（目标语言）
- 禁止使用 faq_only_capabilities 中的能力词
- 禁止使用 L3 长尾词
- 禁止使用 competitor_brands 列表中的品牌词
- 禁止重复堆砌形容词（如 very fast quick rapid）
- 使用名词短语，不用破碎关键词串
步骤 4.3 — Bullet Points 生成（B1-B5）

严格按 writing_policy.bullet_slot_rules 执行：

B1：{bullet_slot_rules.B1}
  必须包含：挂载系统/主场景 + P0能力 + 参数
  格式：大写开头短语
  示例结构：MAGNETIC MOUNT SYSTEM — [挂载描述] + [P0能力] + [参数]

B2：{bullet_slot_rules.B2}
  必须包含：P0核心能力 + 量化参数
  量化参数示例：电池容量mAh + 续航时长；分辨率 + 帧率

B3：{bullet_slot_rules.B3}
  必须包含：P1竞品痛点对比 + 场景词
  不得直接提竞品品牌名
  使用隐性对比（如"Unlike bulky action cameras..."）

B4：{bullet_slot_rules.B4}
  必须包含：P1/P2能力 + 使用场景
  必须包含边界声明句（Rule 3b）
  格式："Optimized for [场景A]; not engineered for [场景B]"

B5：{bullet_slot_rules.B5}
  必须包含：P2质保/售后/兼容性信息
  包含具体质保期限或售后承诺

每条字符限制：≤ 250 chars（目标语言）
禁止：HTML/Markdown 格式；faq_only_capabilities 中的能力词
步骤 4.4 — Description 生成

格式：100% plain text，零 HTML/Markdown
字数：250-300 words（目标语言）
结构：产品定位 → 主场景描述 → 核心能力 → 目标用户 → 行动号召
约束：
- 覆盖 scene_priority 中排名前2的场景
- 覆盖 P0 + P1 能力（不得提及 faq_only_capabilities）
- 明确提及至少1类目标用户
- 不得重复 Title 和 Bullets 中的完整句子
步骤 4.5 — FAQ 生成（5 Q&A）

必须覆盖的问题类型：
1. 防水：具体防水深度/条件（来自属性表）
2. 防抖：说明支持的模式和限制（faq_only_capabilities 在此详细说明）
3. 兼容性：支持的设备/系统
4. 电池：续航时长 + 充电时间（具体数字）
5. 配件：包含哪些配件 + 可选配件
  
每个回答必须包含具体数字或条件，禁止空洞回答（如"效果很好"）
faq_only_capabilities 中的能力必须在此详细说明，不得回避
步骤 4.6 — Search Terms 生成

字节限制：≤ 250 bytes（UTF-8编码）
  验证方法：len(search_terms.encode('utf-8')) ≤ 250

内容规则：
- 使用未进入 Title/Bullets 的 L2/L3 词
- 优先使用 [🔥High-Conv] 标记的 L2 词
- L3 词全部进入 Search Terms
- 词与词之间用空格分隔，不用逗号
  
禁止：
- 重复 Title/Bullets 中已出现的词
- 品牌词（本品牌 + competitor_brands 列表）
- 违禁词（compliance_rules.txt）
- L1 词（已在 Title/B1/B2 覆盖）
步骤 4.7 — A+ 文案生成

可索引正文字数：≥ 500字（英文）
统计范围：所有模块正文（不含标题/alt text/表格表头）

必须覆盖：
- 产品故事（品牌背景/设计理念）
- 核心场景图说明（对应 visual_audit 的 usage_context_hints）
- 参数对比表（本品 vs 同类产品，不得提竞品品牌名）
- 用户证言引导（基于 review_pain_points 的正面回应）
- ≥1 条 capable_of 类型底层能力证明句
示例："1350mAh battery delivers up to 90 minutes of continuous
1080P recording — verified under standard test conditions"
步骤 4.8 — 8 项自检

生成完成后，逐项确认：

☑/☒ 1. Title 前80字符含：品牌名 + 类目词 + L1能力词 + 最高优先级场景词
☑/☒ 2. scene_priority 已按优先级顺序分配场景词
☑/☒ 3. 所有能力均与 allowed_scenes 绑定，无 forbidden_scenes 违规
☑/☒ 4. forbidden_pairs 中的组合未在任何单条文案中同时出现
☑/☒ 5. faq_only_capabilities 中的能力未出现在 Title 或 Bullets
☑/☒ 6. B1-B5 每条均满足 bullet_slot_rules 的强制内容规则
☑/☒ 7. Search Terms ≤ 250 bytes，无重复，无品牌词
☑/☒ 8. 至少1条边界声明句已嵌入 Bullets 或 FAQ；A+ 正文字数 ≥ 500字

如有任何 ☒，必须修正后再输出，不得带着未通过项直接输出
输出：listing_draft.json（含 title/bullets/description/faq/search_terms/aplus_content/self_check）

失败兜底：

自检第1-6项未通过 → 修正后重新输出，不得跳过
自检第7项字节超限 → 删减 L3 词直到满足限制
自检第8项 A+ 字数不足 → 补充内容至 500字，如无法补充则在 audit_trail 中标注并如实扣分
生效规则：writing_policy 6条硬性约束；title_rules；bullet_rules；description_rules；search_terms_rules；forbidden_rules

阶段五：仲裁、评分与输出
阶段目标：对文案草稿执行合规检查、算法评分、输出最终报告和 Word 文档。

输入：listing_draft.json；strategy_profile.json；intent_graph.json；arsenal_output.json（含 price_context）；算法规则库（第一章1.3节/第三章/第八章/第十二章/附录B）；合规规则库；运动相机合规规则库；品牌名称

处理逻辑：

步骤 5.1 — 合规红线检查（Module 3）

逐条核查：
1. 违禁词清单（compliance_rules.txt）
2. 侵权品牌库（competitor_brands + 合规规则库品牌列表）
3. 风格指南违规（夸大宣传/虚假承诺/无数据支撑的绝对化表述）
4. 运动相机专项（如存在 compliance_actioncam.txt）：
  - 执法场景词（police/law enforcement/surveillance）
  - 未包含配件的声明
  - 隐蔽拍摄相关合规限制
    
输出：compliance_violations 列表（含违规项 + 修正建议）
步骤 5.2 — writing_policy 执行审计（Module 4）

逐条核查 6 条硬性约束在最终文案中的执行情况：
- Rule 1：场景词是否按 scene_priority 顺序出现
- Rule 2：每个能力是否只与 allowed_scenes 组合
- Rule 3：forbidden_pairs 是否有违规
- Rule 3b：边界声明句是否存在，原文是什么
- Rule 4：faq_only_capabilities 是否泄漏到 Title/Bullets
- Rule 5：B1-B5 槽位规则是否满足
- Rule 6：A+ 正文字数是否 ≥ 500字
  
输出：每条规则的 pass/fail + 说明
步骤 5.3 — Module 8 算法评分（定向读取规则库）

读取算法规则库：
- 第一章 1.3节（Rufus Score权重模型）
- 第三章（title_front_80评分依据）
- 第八章（keyword_tiering评分依据）
- 第十二章（conflict_check评分依据）
- 附录B（幻觉风险速查表）
  
按章节顺序逐维度评分，禁止跳过任何维度：

A10 评分（满分100）：
  title_front_80（0-40）：
    含品牌+类目 → +10
    含L1能力词 → +15
    含场景词 → +15
  keyword_tiering（0-30）：
    ≥80% L1词出现在Title/B1/B2 → +20
    Title无L3长尾词 → +10
  conversion_signals（0-30）：
    B1有P0能力+参数 → +10
    B2-3有P1竞品痛点 → +10
    B4-5有P2质保 → +10

COSMO 评分（满分100）：
  scene_coverage（0-40）：
    ≥2个场景明确提及 → +20
    其中1个在Title/B1 → +20
  capability_scene_binding（0-40）：
    ≥3条能力+场景组合句 → +20
    每主场景≥1条 → +20
  audience_tags（0-20）：
    提及1类目标用户 → +10
    提及2类以上并关联能力/场景 → +10

Rufus 评分（满分100）：
  fact_completeness（0-40）：
    ≥70%参数为结构化键值对 → +30
    其余语义明确 → +10
    A+字数不足500字 → -15（Rule 6联动）
  faq_coverage（0-40）：
    ≥3个高频问题含数字/条件 → +30
    无空洞回答 → +10
  conflict_check（0-20）：
    无冲突 → +20
    轻微不严谨 → +10
    硬冲突 → 0，并列出冲突项
    无边界声明句（Rule 3b违反）→ 额外 -10

价格竞争力评分（满分10）：
  数据来源：arsenal_output.json 的 price_context.price_median
  中位数 85%-110%（甜蜜区）→ 10分
  中位数 70%-85% → 7分
  中位数 110%-115% → 6分
  中位数 115%以上 → 0分
  中位数 70%以下 → 3分
  price_context 缺失 → 标注"数据缺失，跳过评分"，不计入总分分母

总分 = A10 + COSMO + Rufus + 价格竞争力（满分310）

重要：评分是对当前 Listing 的客观体检，不因 Listing
由本工作流生成而假设高分，如未满足规则必须如实扣分
步骤 5.4 — Module 8 详细评分表输出

必须输出填好实际得分的 Markdown 表格（不得只输出汇总分）：

A10 维度评分表：
维度
满分
实际得分
说明简述（1句话）
title_front_80
40
[填入]
[填入]
keyword_tiering
30
[填入]
[填入]
conversion_signals
30
[填入]
[填入]
A10 小计
100
[填入]


COSMO / Rufus 同结构。

价格竞争力表：
指标
值
品类价格中位数
[从price_context填入]
当前定价
[填入]
所在区间
[填入]
实际得分
[填入]

v2.0 新增检查项：
boundary_declaration_check:
  存在边界声明句: [是/否]
  声明句原文: "[...]"
  得分影响: [+10 / -10]

aplus_word_count_check:
  A+正文字数: [N]字
  是否达到500字下限: [是/否]
  得分影响: [+15 / -15]
步骤 5.5 — 《算法对齐摘要》输出

在详细评分表之后输出，作为汇总视图：

1. 评分汇总表：
算法
总分
评级
A10
__ / 100
优秀/良好/待优化
COSMO
__ / 100
优秀/良好/待优化
Rufus
__ / 100
优秀/良好/待优化
价格竞争力
__ / 10
优秀/良好/待优化
总计
__ / 310


评级标准：
A10/COSMO/Rufus：90-100优秀 / 70-89良好 / <70待优化
价格竞争力：10分优秀 / 6-9分良好 / <6分待优化

2. 各算法优化建议（每项2-3条可执行建议）
3. 综合结论（2-3句话）
步骤 5.6 — 最终报告生成（generate_doc 工具）

汇总 Module 1-8，生成 final_report.md
语言规范：所有说明性文字统一中文；
仅 Listing 内容片段（Title/Bullets/Description/FAQ/ST）使用目标语言

必须调用 generate_doc 工具，禁止直接在 chat 中输出纯文本
步骤 5.7 — Word 文档导出

使用 execute_code 工具执行 Python 代码
将 final_report.md 转换为 .docx 文件
文件命名：Amazon_Listing_{brand}_{site}_v840.docx
保存到新文件路径，不覆盖已有文件
步骤 5.8 — 输出审计日志生成

汇总全流程审计信息，生成 audit_trail.json
（字段详见 C-9 输出定义）
输出：final_report.md；scoring_detail.json；audit_trail.json；Amazon_Listing_{brand}.docx

失败兜底：

generate_doc 工具调用失败 → 重试一次，仍失败则输出错误日志，不输出纯文本
Word 导出失败 → 在 audit_trail 中记录，final_report.md 仍正常输出
价格评分数据缺失 → 跳过该维度，不影响其他评分
生效规则：algorithm_scoring_rules；compliance_rules；writing_policy 执行审计规则；输出审计规则

E. 节点清单
共 9 个节点（1个 Start + 8个 skillResponse）。

E-1. Start（起始节点）
属性        内容
节点名称        Start
entityId        start-i3lpk77r3r84k7ucpfz0fi2d
节点职责        工作流入口，触发后续所有节点执行
上游依赖        无
下游输出        触发语种初始化节点
使用工具        无
迁移建议        替换为本地脚本的 main() 入口函数
E-2. 语种初始化与检测
属性        内容
节点名称        语种初始化与检测
entityId（画布）        ar-lnx8mymug9z0qrt2kkb06nxn
taskId（Plan）        ar-lq37bnj5iattwv8q4ecz4f4t
节点职责        根据目标市场变量确定目标语种；ABA数据兜底检测
上游依赖        var-target-country；var-aba-csv
下游输出        语种代码和语言名称，供所有后续节点使用
提示词逻辑        优先读取 target_country 变量映射语种；为空时从 ABA CSV 关键词语言特征自动检测；输出固定格式三行文本
使用工具        无
是否建议保留        保留逻辑，但迁移为 normalize_inputs.py 中的硬编码映射函数，无需独立 LLM 调用
E-3. 视觉审计 - 产品图像分析
属性        内容
节点名称        视觉审计 - 产品图像分析
entityId（画布）        ar-z6lxuhrz4ooas7ytumpohd4m
taskId（Plan）        ar-q3h5nvu987f9qsq9c8rfsnwj
节点职责        多模态分析产品图片，提取视觉标签、挂载方式、使用场景、合规标志
上游依赖        var-product-images；语种初始化输出
下游输出        visual_audit.json（visual_tags / mount_visuals / usage_context_hints / compliance_flags）
提示词逻辑        分4个分析任务：① 通用视觉标签（3-5个）；② 配件与挂载方式识别；③ 使用场景推断（2-3个）；④ 合规检查（4项 flag）；输出固定 JSON 结构
使用工具        无（依赖多模态视觉能力）
是否建议保留        保留，迁移为独立 Claude Vision API 调用，输入图片列表，输出标准化 JSON
E-4. Python 工程核心 - 自适应算法引擎
属性        内容
节点名称        Python 工程核心 - 自适应算法引擎
entityId（画布）        ar-covpjvc024x30lts8noj25f7
taskId（Plan）        ar-gw8g9k6m1zstemj0ok6dgz1l
节点职责        CSV解析、L1/L2/L3分级、Score/AdScore计算、能力熔断、军火库构建、price_context提取
上游依赖        var-aba-csv；var-competitor-csv；var-specs-txt；var-specs-supplement；var-full-dimension-csv；var-algorithm-rules；var-compliance-rules；var-compliance-actioncam；语种初始化输出
下游输出        arsenal_output.json（reserve_keywords / parameter_constraints / price_context / competitor_brands / review_pain_points）
提示词逻辑        顶部插入算法规则库定向读取指令（第八章/第一章1.2节/第一章1.3节）；分级规则速查硬编码在 prompt 中；6个任务：CSV解析/分级/熔断/军火库/站点感知/price_context
使用工具        execute_code（Python 沙箱）
⚠️ 已知不稳定        ① LLM 自行生成 Python 代码，字段映射不稳定；② execute_code 沙箱无法访问 LLM 上下文中的算法规则库文件，导致 L1/L2/L3 分级实际未按规则库执行；③ 竞品 CSV 和全维度表当前未被有效读取
是否建议保留        建议重构。迁移为硬编码 Python 脚本（parse_csv.py + extract_fields.py），字段映射规则固化，不依赖 LLM 生成代码
E-5. 意图转译引擎 - COSMO Intent Mapping
属性        内容
节点名称        意图转译引擎 - COSMO Intent Mapping
entityId（画布）        ar-tnj6y2l2rej8sq0ifg5y25ld
taskId（Plan）        ar-kmvq0czurn64wy8ik0kwrqzv
节点职责        将军火库中的 High-Conv 词转译为用户意图图谱和 STAG 广告分组
上游依赖        arsenal_output.json（前20个 High-Conv 词）
下游输出        intent_graph.json（User Identity / Purchase Intent / Pain Point / STAG Grouping）
提示词逻辑        4个分析维度：User Identity / Purchase Intent / Pain Point / STAG Grouping（3-5组）；输出 Intent Graph JSON + STAG Grouping Markdown 表格
使用工具        无
是否建议保留        保留，迁移为独立 LLM prompt 调用，输入军火库 JSON，输出意图图谱 JSON
E-6. 产品战略侧写师 - Meta-Cognition Layer
属性        内容
节点名称        产品战略侧写师 - Meta-Cognition Layer
entityId（画布）        ar-lczwnqyy1v4tbvjiw9j64ksq
taskId（Plan）        ar-is93d16pixq0bp5fa03f9nvo
节点职责        生成产品战略侧写 JSON，核心产出是 writing_policy（场景优先级/能力场景绑定/禁止配对/FAQ限制/Bullet槽位规则）
上游依赖        visual_audit.json；arsenal_output.json；intent_graph.json；var-specs-txt；var-specs-supplement；var-algorithm-rules；var-compliance-rules；var-compliance-actioncam
下游输出        strategy_profile.json（含完整 writing_policy，四类 binding_type 全覆盖）
提示词逻辑        顶部定向读取指令（第一章1.2节/第二章/第四章/第十二章/附录A）；输出完整 JSON 结构；writing_policy 5个子字段填写规则显式说明；capable_of 第4类关联类型说明
使用工具        无
是否建议保留        保留，是工作流核心控制层。迁移时建议增加 JSON Schema 校验，确保 writing_policy 结构完整
E-7. 创意策略 - 营销文案生成
属性        内容
节点名称        创意策略 - 营销文案生成
entityId（画布）        ar-ycbkaxcvj95uuv3mrs7uvtyk
taskId（Plan）        ar-sdi699hmc1od3h5us03oeq8b
节点职责        基于 writing_policy 的 6 条硬性约束生成完整 Listing 文案（Title/B1-B5/Description/FAQ/ST/A+），执行 8 项自检
上游依赖        strategy_profile.json（writing_policy）；arsenal_output.json；intent_graph.json；visual_audit.json；语种初始化输出；var-manual-brand；var-selling-points；var-specs-supplement；var-algorithm-rules；var-compliance-rules；var-compliance-actioncam
下游输出        listing_draft.json（含 title/bullets/description/faq/search_terms/aplus_content/self_check）
提示词逻辑        顶部定向读取指令（第三章→第四章→第七章→附录B）；STEP 0 强制读取 writing_policy；6条硬性约束（Rule 1-6）；6个生成任务；8项自检清单
使用工具        无
是否建议保留        保留，迁移为独立 LLM prompt 调用，writing_policy 作为系统 prompt 注入
E-8. 最终仲裁者 - 完整输出协议
属性        内容
节点名称        最终仲裁者 - 完整输出协议
entityId（画布）        ar-nnfgad420hhuxwgfiw4xwkt2
taskId（Plan）        ar-ds849o2983zj0tit38xqug6q
节点职责        执行 Module 1-8（最终Listing输出/关键词审计/合规检查/writing_policy审计/竞品分析/广告建议/Rufus Q&A/算法评分），生成最终仲裁报告
上游依赖        strategy_profile.json；listing_draft.json；intent_graph.json；arsenal_output.json（含price_context）；var-algorithm-rules；var-compliance-rules；var-compliance-actioncam；var-manual-brand
下游输出        final_report.md（通过 generate_doc 工具生成）；scoring_detail.json；audit_trail.json
提示词逻辑        顶部定向读取指令（第一章1.3节/第三章/第八章/第十二章/附录B）；全局中文声明；Module 1-8 逐模块说明；Module 8 评分规则 + 详细评分表输出要求；《算法对齐摘要》结构；防抬分声明
使用工具        generate_doc（强制调用，禁止纯文本输出）
⚠️ 已知问题        节点职责过重（8个Module），单次调用上下文压力大；当前画布版本仍显示 v8.3.5（画布节点未同步最新 Plan prompt）
是否建议保留        保留逻辑，建议拆分为：评分脚本 + 报告生成脚本 + 审计脚本，每个模块独立可测试
E-9. 导出 Word 文档
属性        内容
节点名称        导出 Word 文档 (.docx)
entityId（画布）        ar-ee7ef0qeg3o7f0pqvwxdzoh6
taskId（Plan）        ar-nsmcle2gbtlc7ho2b6ceyby3
节点职责        将最终仲裁报告转换为格式化 Word 文档
上游依赖        final_report.md（Node 8 输出）；var-manual-brand
下游输出        Amazon_Listing_{brand}_v835.docx
提示词逻辑        调用 execute_code 执行 Python 代码；引用上游节点 entityId（ar-nnfgad420hhuxwgfiw4xwkt2）；保存到新文件路径
使用工具        execute_code（Python 沙箱）
是否建议保留        保留，迁移为独立 export_docx.py 脚本，使用 python-docx 库，比沙箱更稳定
F. 规则系统
F-1. 输入文档优先级规则
P0（绝对真理层）：
- 本品属性表（product_specs.txt）
- 参数补充（specs_supplement）
→ 所有参数以此为准，禁止编造未出现的参数
→ 与任何其他输入冲突时，P0 优先
  
P1（规则层）：
- 算法规则库（algorithm_rules_v2.md）
- 各节点按章节编号定向读取，不泛读全文
→ 高于数据层，规则优先于数据
  
P2（合规层）：
- 合规规则库（compliance_rules.txt）
- 运动相机合规规则库（compliance_actioncam.txt）
→ 高于数据层，合规优先于卖点
  
P3（数据层）：
- ABA 关键词数据
- 竞品出单词报告
- 产品全维度表
  
P4（辅助层）：
- 产品主图
- 核心卖点
- 参数补充（与 P0 共享，但优先级低于属性表）
  
冲突处理：
  P0 vs P4 冲突 → P0 优先，risk_flags 记录
  P1 vs P3 冲突 → P1 优先（规则优先于数据）
  P2 vs P4 冲突 → P2 优先（合规优先于卖点）
  任何文件 vs parameter_constraints → parameter_constraints 优先
F-2. 字段映射规则
ABA CSV（按语义匹配，不要求列名完全一致）：
  关键词列：keyword / 关键词 / search_term / 搜索词
  搜索量列：search_volume / 月搜索量 / 搜索量 / volume
  转化率列：conversion_rate / 购买率 / 转化率 / cvr
  排名列：ABA月排名 / aba_rank / 月排名（可选）

竞品 CSV：
  关键词列：keyword / 关键词
  价格列：均价 / avg_price / price
  购买率列：购买率 / conversion_rate
  月购买量列：月购买量 / monthly_purchases
  竞品数列：竞品数 / 商品数 / competitor_count
  注意：第一列若为文件名（列名与文件名相同），自动跳过

全维度表 CSV：
  差评关键词列：差评关键词 / negative_keywords / 负面词
  高频问题列：Rufus问题 / user_questions / 高频问题
  评分列：评分值 / rating

映射失败处理：
  在 audit_trail.ignored_docs 中记录该列
  不终止执行，继续处理其他字段
F-3. 标题生成规则
格式：[Brand] + [L1关键词] + [最高优先级场景词] + [核心能力+参数] + [差异化特征]

前80字符约束（移动端可见区域）：
  必须包含：品牌名 + 类目词 + L1能力词 + 最高优先级场景词

字符限制：≤ 200 chars（目标语言）

强制规则：
  ① 品牌名必须在最前面
  ② 使用名词短语，不用破碎关键词串
  ③ 参数必须具体（写"4K 30fps"而非"高清"）
  ④ 场景词必须是 COSMO 图谱中的标准节点词

禁止：
  ① faq_only_capabilities 中的能力词
  ② L3 长尾词
  ③ competitor_brands 列表中的品牌词
  ④ 重复堆砌形容词（very fast quick rapid 等）
  ⑤ 低优先级场景词出现在前80字符
F-4. 五点描述生成规则
槽位强制规则（来自 writing_policy.bullet_slot_rules）：
  B1：挂载系统/主场景 + P0能力 + 参数（大写开头短语）
  B2：P0核心能力 + 量化参数（电池/分辨率/帧率）
  B3：P1竞品痛点对比 + 场景词（不得提竞品品牌名）
  B4：P1/P2能力 + 使用场景 + 边界声明句（Rule 3b）
  B5：P2质保/售后/兼容性信息（含具体质保期限）

字符限制：每条 ≤ 250 chars（目标语言）

格式规范：
  ① 每条以全大写名词短语开头
  ② 结构：[功能名词] + [核心利益点] + [数据支撑] + [场景]
  ③ 每条至少包含一个具体数字或参数
  ④ 禁止 HTML/Markdown 格式

边界声明句（B4 必须包含）：
  格式："Optimized for [场景A]; not engineered for [场景B]"
  示例："Optimized for 1080P/4K action recording;
        not engineered for 5K stabilized footage"

禁止：
  ① faq_only_capabilities 中的能力词
  ② forbidden_pairs 中的能力组合同句出现
  ③ 竞品品牌名
  ④ 模糊描述（如"Fast Charging"无数据支撑）
F-5. 描述生成规则
格式：100% plain text，零 HTML/Markdown
字数：250-300 words（目标语言）
结构：产品定位 → 主场景描述 → 核心能力 → 目标用户 → 行动号召

内容约束：
  ① 覆盖 scene_priority 中排名前2的场景
  ② 覆盖 P0 + P1 能力（不得提及 faq_only_capabilities）
  ③ 明确提及至少1类目标用户（target_personas）
  ④ 不得重复 Title 和 Bullets 中的完整句子

禁止：
  ① HTML 标签（<br> / <b> / <ul> 等）
  ② Markdown 格式（** / ## / - 等）
  ③ 编造未在 product_specs.txt 中出现的参数
F-6. Search Terms 规则
字节限制：≤ 250 bytes（UTF-8编码）
验证：len(search_terms.encode('utf-8')) ≤ 250

内容规则：
  ① 使用未进入 Title/Bullets 的 L2/L3 词
  ② 优先使用 [🔥High-Conv] 标记的 L2 词
  ③ L3 词全部进入 Search Terms（禁止进入 Title）
  ④ 词与词之间用空格分隔，不用逗号

禁止：
  ① 重复 Title/Bullets 中已出现的词
  ② 品牌词（本品牌 + competitor_brands 列表）
  ③ 违禁词（compliance_rules.txt）
  ④ L1 词（已在 Title/B1/B2 覆盖）
F-7. 禁止事项（全局）
参数类：
  ① 禁止编造未在 product_specs.txt 中出现的参数
  ② 禁止忽略 parameter_constraints（能力熔断结果）
  ③ 禁止将 faq_only_capabilities 写入 Title 或 Bullets
  ④ 禁止将 forbidden_pairs 中的能力组合写入同一条文案

品牌类：
  ⑤ 禁止使用竞品品牌名（competitor_brands 列表）
  ⑥ 禁止在 Search Terms 中使用品牌词

格式类：
  ⑦ 禁止在 Description 中使用 HTML 或 Markdown
  ⑧ 禁止在 Search Terms 中重复 Title/Bullets 中的词

评分类：
  ⑨ 禁止因 Listing 由本工作流生成而在评分中自动抬分
  ⑩ 禁止跳过任何评分维度

工具类：
  ⑪ Node 8 禁止直接在 chat 中输出纯文本（必须调用 generate_doc）
F-8. 风险控制规则
Rufus 幻觉风险规避（来自算法规则库附录B）：
  ① 兼容性字段不得留空（空值 = 不支持）
  ② 模糊描述必须数据化
     "Fast Charging" → "0-50% in 30 mins"
     "长续航" → "1350mAh，1080P模式约90分钟"
  ③ 前端文案与后端属性必须一致
     如"3 Pack" vs "1 Count"会被 Rufus 判定为信息不可信
  ④ 评论中出现的负面词必须在文案中预防性说明
     如差评含"过热" → 在文案中强调散热设计

合规风险：
  ⑤ 运动相机执法场景禁用词（police/law enforcement）
  ⑥ 未包含配件不得在文案中声称包含
  ⑦ 隐蔽拍摄相关表述需符合合规规则库要求

站点文件一致性：
  ⑧ 运行 DE 站时必须使用 DE 站 ABA 和竞品数据
     文件名/内容语言与 site 参数不一致时发出 SITE_FILE_MISMATCH 警告
F-9. 缺失字段处理规则
必需输入缺失 → 终止执行：
- aba_keywords.csv
- product_specs.txt
- brand_name
- algorithm_rules
- compliance_rules
  
可选输入缺失 → 降级继续：
- competitor_words.csv → 跳过竞品分析和 price_context
- full_dimension.csv → 跳过 Review 痛点分析
- product_images → 跳过视觉审计
- specs_supplement → 仅用属性表执行熔断
- selling_points → 从属性表推断
- compliance_actioncam → 仅用通用合规规则
  
CSV 字段映射失败 → 跳过该字段：
- 在 audit_trail.ignored_docs 中记录
- 不终止执行
  
price_context 缺失 → 价格评分跳过：
- 标注"数据缺失，跳过评分"
- 不计入总分分母（总分分母从310降为300）
  
writing_policy 子字段缺失 → 对应约束失效：
- 在 audit_trail.risk_flags 中标注
- 文案生成时该约束不执行
F-10. 输出审计规则
每次执行必须生成 audit_trail.json，包含：
  fields_used：实际使用的字段列表
  missing_inputs：缺失的必需输入
  optional_missing：缺失的可选输入
  used_docs：实际读取并使用的文档
  ignored_docs：存在但未被使用的文档（含原因）
  risk_flags：发现的风险项
  boundary_declaration_check：
    exists: true/false
    sentence: "..."
    score_impact: "+10 / -10"
  aplus_word_count_check：
    word_count: N
    meets_minimum: true/false
    score_impact: "+15 / -15"
  l1_l2_l3_distribution：
    title: {l1: N, l2: N, l3: N}
    bullets: {l1: N, l2: N, l3: N}
    search_terms: {l1: N, l2: N, l3: N}

Module 8 评分必须输出逐维度明细表：
  不得只输出汇总分
  每个维度必须有说明简述（1句话）
  防抬分声明必须在 prompt 中显式声明
G. 数据结构
G-1. normalized_input
{
  "site": "DE",
  "language_code": "de",
  "language_name": "German",
  "detection_method": "manual_override",
  "brand": "TOSBARRFT",
  "selling_points": "双屏幕，支持EIS防抖，可WI-FI连接手机",
  "specs_supplement": "只有1080P和4K模式支持防抖...",
  "files_present": {
    "aba_csv": true,
    "competitor_csv": true,
    "specs_txt": true,
    "full_dimension_csv": true,
    "product_images": true,
    "algorithm_rules": true,
    "compliance_rules": true,
    "compliance_actioncam": true
  },
  "files_missing": [],
  "warnings": [
    "SITE_FILE_MISMATCH: T70M_FR_ABA关键词表_数据表.csv (FR file used for DE site)"
  ]
}
G-2. keyword_pool（arsenal_output）
{
  "site": "DE",
  "language": "German",
  "circuit_breaker_applied": true,
  "parameter_constraints": [
    "No stabilization for 5K",
    "1080P stabilization > 4K stabilization",
    "Avoid highlighting 4K/5K stabilization"
  ],
  "faq_only_capabilities": [
    "5K防抖说明",
    "4K防抖效果对比1080P"
  ],
  "forbidden_capabilities": [],
  "reserve_keywords": [
    {
      "keyword": "action cam",
      "level": "L1",
      "score": 6.31,
      "ad_score": 11.08,
      "search_volume": 30843,
      "conversion_rate": "0.78%",
      "high_conv": false
    },
    {
      "keyword": "dashcam fahrrad",
      "level": "L2",
      "score": 5.51,
      "ad_score": 6.98,
      "search_volume": 2776,
      "conversion_rate": "2.27%",
      "high_conv": true
    }
  ],
  "competitor_brands": [],
  "price_context": {
    "price_median": null,
    "currency": null,
    "sample_size": 0,
    "data_available": false
  },
  "review_pain_points": [],
  "rufus_high_freq_questions": []
}
G-3. visual_audit
{
  "visual_tags": [
    "Outdoor sports",
    "Compact thumb design",
    "Dual touchscreens",
    "Magnetic attachment",
    "Rugged texture"
  ],
  "mount_visuals": [
    "magnetic_clip_detail",
    "helmet_mount_shot",
    "chest_mount_shot",
    "bike_mount_shot",
    "neck_lanyard_shot"
  ],
  "usage_context_hints": [
    "outdoor_adventure",
    "urban_commute",
    "sports_recording"
  ],
  "compliance_flags": [
    "no_weapon_context",
    "no_unincluded_accessories",
    "no_inappropriate_content",
    "no_law_enforcement_context"
  ]
}
G-4. intent_graph
{
  "high_conv_keywords_analyzed": 20,
  "intent_nodes": [
    {
      "keyword": "dashcam fahrrad",
      "user_identity": "Cyclist / Urban commuter",
      "purchase_intent": "Decision",
      "pain_point": "Need hands-free recording while cycling",
      "stag_group": "cycling_security"
    }
  ],
  "stag_groups": [
    {
      "group_id": "cycling_security",
      "group_name": "骑行安防记录",
      "keywords": ["dashcam fahrrad", "helmkamera fahrrad", "action cam halterung"],
      "persona": "通勤骑行者 / 骑行爱好者",
      "primary_pain_point": "骑行途中需要稳定记录，证据留存"
    },
    {
      "group_id": "bodycam_security",
      "group_name": "随身安防记录",
      "keywords": ["bodycam", "körperkamera", "body cam"],
      "persona": "安防需求用户 / 执法辅助（需合规）",
      "primary_pain_point": "需要隐蔽或随身的记录设备"
    }
  ]
}
G-5. strategy_profile
{
  "category_type": "Electronics",
  "category_subtype": "Action Camera",
  "physical_form": "Compact Magnetic Modular Camera",
  "form_details": "Ultra-compact thumb-sized body camera with dual screens and magnetic mounting system",
  "primary_capabilities": ["Magnetic Mount", "Dual Screen", "EIS Stabilization (1080P/4K)", "WiFi"],
  "capability_tiers": {
    "P0": ["Magnetic Mount System", "Dual Screen", "EIS 1080P Stabilization"],
    "P1": ["WiFi App Control", "30M Waterproof Case", "Multi-mount Accessories"],
    "P2": ["5K Video Mode (No Stabilization)", "Warranty & After-sales"]
  },
  "primary_usage_scenarios": ["cycling_security", "outdoor_adventure"],
  "secondary_usage_scenarios": ["travel_vlog", "sports_recording"],
  "target_personas": ["Cyclists", "Outdoor enthusiasts", "Vloggers", "Commuters"],
  "competitive_advantages": [
    "Magnetic attachment vs traditional clip mounts",
    "Dual screen for real-time framing",
    "Ultra-compact form factor"
  ],
  "taboo_concepts": [
    "law_enforcement_context",
    "police_uniform",
    "unincluded_accessories",
    "5K_stabilization_claim"
  ],
  "verified_specs": {
    "resolution": "5K/4K/1080P",
    "stabilization": "EIS (1080P and 4K only)",
    "waterproof": "30M with case accessory",
    "screen": "Dual screens",
    "connectivity": "WiFi",
    "battery": "1350mAh"
  },
  "writing_policy": {
    "scene_priority": [
      "骑行安防记录（最高优先级）",
      "户外运动",
      "随身安防",
      "旅行Vlog"
    ],
    "capability_scene_bindings": [
      {
        "capability": "EIS防抖",
        "binding_type": "used_for_func",
        "allowed_scenes": ["骑行安防记录", "户外运动", "旅行Vlog"],
        "forbidden_scenes": ["5K视频模式"]
      },
      {
        "capability": "磁吸挂载",
        "binding_type": "used_for_eve",
        "allowed_scenes": ["骑行安防记录", "通勤", "户外探险", "摩托车记录"],
        "forbidden_scenes": []
      },
      {
        "capability": "双屏幕",
        "binding_type": "used_for_aud",
        "allowed_scenes": ["旅行Vlog", "户外运动"],
        "forbidden_scenes": []
      },
      {
        "capability": "1350mAh电池",
        "binding_type": "capable_of",
        "allowed_scenes": ["骑行安防记录", "户外运动"],
        "forbidden_scenes": [],
        "capable_of_statement": "1350mAh battery delivers up to 90 minutes of continuous 1080P recording"
      }
    ],
    "faq_only_capabilities": [
      "5K防抖说明（5K模式不支持防抖）",
      "4K vs 1080P防抖效果对比"
    ],
    "forbidden_pairs": [
      ["5K视频", "防抖"],
      ["执法场景", "隐蔽拍摄"]
    ],
    "bullet_slot_rules": {
      "B1": "磁吸挂载系统 + P0能力（EIS防抖）+ 参数（1080P/4K）",
      "B2": "P0核心能力（双屏幕/WiFi）+ 量化参数（电池1350mAh/续航时长）",
      "B3": "P1竞品痛点对比（传统运动相机体积大/安装复杂）+ 骑行/通勤场景词",
      "B4": "P1能力（防水壳30M）+ 使用场景 + 边界声明句",
      "B5": "P2质保/售后/配件兼容性信息"
    }
  }
}
G-6. listing_draft
{
  "language": "German",
  "site": "DE",
  "brand": "TOSBARRFT",
  "title": "TOSBARRFT Action Cam 4K Bodycam – Magnetische Halterung, EIS-Stabilisierung, Dual-Display, WiFi, Fahrrad Helmkamera",
  "bullets": {
    "B1": "MAGNETISCHES MONTAGESYSTEM & EIS-STABILISIERUNG — ...",
    "B2": "DUAL-DISPLAY & 1350MAH AKKU — ...",
    "B3": "KOMPAKTE BODYCAM FÜR FAHRRAD & PENDLER — ...",
    "B4": "30M WASSERDICHT MIT SCHUTZGEHÄUSE — ... Optimiert für 1080P/4K-Aufnahmen; nicht für 5K-stabilisierte Videos konzipiert.",
    "B5": "12 MONATE GARANTIE & UMFANGREICHES ZUBEHÖR — ..."
  },
  "description": "...(250-300 words plain text)...",
  "faq": [
    {"q": "Ist die Kamera wasserdicht?", "a": "Mit dem mitgelieferten Schutzgehäuse ist die Kamera bis 30 Meter wasserdicht."},
    {"q": "Funktioniert die Bildstabilisierung bei 5K?", "a": "Nein. EIS-Stabilisierung ist nur im 1080P- und 4K-Modus verfügbar. Im 5K-Modus ist keine Stabilisierung aktiv."},
    {"q": "Wie lange hält der Akku?", "a": "Der 1350mAh-Akku ermöglicht ca. 90 Minuten Aufnahme im 1080P-Modus."},
    {"q": "Ist die Kamera mit dem Smartphone kompatibel?", "a": "Ja, über WiFi mit der zugehörigen App für iOS und Android."},
    {"q": "Welches Zubehör ist im Lieferumfang enthalten?", "a": "Im Lieferumfang sind enthalten: Magnetclip, Schutzgehäuse (30M wasserdicht), Fahrradhalterung, Helmhalterung und USB-C-Ladekabel."}
  ],
  "search_terms": "helmkamera fahrrad bodycam kaufen mini bodycam action cam brustgurt pov kamera mini camera wifi",
  "aplus_content": "...(≥500 words)...",
  "self_check": {
    "rule_1": true,
    "rule_2": true,
    "rule_3": true,
    "rule_3b": true,
    "rule_4": true,
    "rule_5": true,
    "rule_6": true,
    "rule_7": true,
    "rule_8": true
  }
}
G-7. scoring_detail
{
  "a10": {
    "title_front_80": {"max": 40, "score": 35, "note": "含品牌+类目+L1能力词，场景词位于第80字符边界"},
    "keyword_tiering": {"max": 30, "score": 30, "note": "L1词全部在Title/B1/B2，Title无L3长尾词"},
    "conversion_signals": {"max": 30, "score": 20, "note": "B1有P0+参数，B4-5缺少明确质保承诺"},
    "subtotal": 85
  },
  "cosmo": {
    "scene_coverage": {"max": 40, "score": 40, "note": "骑行+户外两场景明确提及，其中骑行在Title/B1"},
    "capability_scene_binding": {"max": 40, "score": 30, "note": "3条能力+场景组合句，但次要场景覆盖不足"},
    "audience_tags": {"max": 20, "score": 20, "note": "明确提及骑行者和通勤族，并关联能力"},
    "subtotal": 90
  },
  "rufus": {
    "fact_completeness": {"max": 40, "score": 25, "note": "约65%参数为键值对，略低于70%阈值"},
    "faq_coverage": {"max": 40, "score": 40, "note": "5个高频问题均含数字/条件，无空洞回答"},
    "conflict_check": {"max": 20, "score": 20, "note": "无冲突，边界声明句存在"},
    "subtotal": 85
  },
  "price_competitiveness": {
    "price_median": null,
    "current_price": null,
    "range": "数据缺失",
    "max": 10,
    "score": null,
    "data_available": false,
    "note": "竞品CSV价格数据未读取，跳过评分"
  },
  "total": 260,
  "max_total": 300,
  "boundary_declaration_check": {
    "exists": true,
    "sentence": "Optimiert für 1080P/4K-Aufnahmen; nicht für 5K-stabilisierte Videos konzipiert.",
    "score_impact": "+10"
  },
  "aplus_word_count_check": {
    "word_count": 523,
    "meets_minimum": true,
    "score_impact": "+15"
  }
}
G-8. audit_trail
{
  "execution_time": "2026-03-31T10:00:00Z",
  "site": "DE",
  "language": "German",
  "brand": "TOSBARRFT",
  "fields_used": [
    "aba_keywords.keyword",
    "aba_keywords.search_volume",
    "aba_keywords.conversion_rate",
    "product_specs.all_fields",
    "specs_supplement.parameter_constraints"
  ],
  "missing_inputs": [
    "competitor_words.avg_price (price_context unavailable)",
    "full_dimension.review_pain_points"
  ],
  "optional_missing": [
    "selling_points (inferred from specs)"
  ],
  "used_docs": [
    "aba_keywords.csv",
    "product_specs.txt",
    "specs_supplement",
    "algorithm_rules (第八章/第一章1.2节/第一章1.3节)",
    "compliance_rules.txt"
  ],
  "ignored_docs": [
    {"file": "competitor_words.csv", "reason": "avg_price column not mapped, price_context skipped"},
    {"file": "full_dimension.csv", "reason": "review_negative column not found"},
    {"file": "compliance_actioncam.txt", "reason": "file present but no violations triggered"}
  ],
  "risk_flags": [
    "SITE_FILE_MISMATCH: ABA file appears to be FR station data",
    "price_context_missing: Node 8 price scoring skipped"
  ],
  "boundary_declaration_check": {
    "exists": true,
    "sentence": "Optimiert für 1080P/4K-Aufnahmen; nicht für 5K-stabilisierte Videos konzipiert.",
    "score_impact": "+10"
  },
  "aplus_word_count_check": {
    "word_count": 523,
    "meets_minimum": true,
    "score_impact": "+15"
  },
  "l1_l2_l3_distribution": {
    "title": {"l1": 2, "l2": 1, "l3": 0},
    "bullets": {"l1": 1, "l2": 4, "l3": 0},
    "search_terms": {"l1": 0, "l2": 3, "l3": 3}
  }
}
H. 当前问题与迁移建议
H-1. 输入文档使用不透明
问题描述：

Node 3 使用 execute_code 工具，LLM 自行生成 Python 代码。代码逻辑不固定，每次运行可能不同，字段映射结果无法预测
竞品 CSV 和全维度表在当前版本实际未被有效读取（已通过输出 JSON 验证）
算法规则库文件在 execute_code 沙箱中无法被 Python 代码访问（沙箱与 LLM 上下文隔离）
站点与文件不一致时无警告机制（运行 DE 站挂载 FR 文件）
迁移建议：

① 用硬编码 Python 脚本替代 LLM 生成代码：
   parse_csv.py：固化字段映射规则，按语义匹配列名
   extract_fields.py：固化 L1/L2/L3 阈值，不依赖 LLM 推断

② 将算法规则库内容直接注入 prompt 上下文：
   不依赖文件读取，将关键规则段落作为 system prompt 的一部分

③ 在 normalize_inputs.py 中增加站点文件一致性校验：
   检查文件名/内容语言与 site 参数是否一致
   不一致时输出 SITE_FILE_MISMATCH 警告

④ 每次执行后输出 audit_trail.json，记录哪些文件被读取、哪些字段被使用
H-2. 节点职责重叠
问题描述：

Node 8（最终仲裁者）承担 8 个 Module，单次 LLM 调用上下文过长，容易导致后半部分输出质量下降
Node 7（文案生成）和 Node 8（Module 1 最终 Listing 输出）都输出 Listing，存在重复
Node 6（战略侧写）和 Node 4（意图图谱）都分析用户意图，边界不清晰
迁移建议：

Node 8 拆分为 3 个独立模块：
  ① scoring_agent.py：执行 Module 8 算法评分，输出 scoring_detail.json
  ② report_generator.py：执行 Module 1-7，生成 final_report.md
  ③ audit_agent.py：执行 audit_trail 生成

Node 7 输出作为草稿，Node 8 Module 1 作为仲裁后的最终版本：
  两者之间增加明确的"仲裁差异说明"字段

Node 4 专注关键词意图分析（STAG分组）：
  Node 6 专注产品能力建模（writing_policy）：
  两者输入输出明确分离，不重叠
H-3. 提示词过长或耦合
问题描述：

Node 7 的 prompt 包含：定向读取指令 + STEP 0 + 6条硬性约束 + 6个生成任务 + 8项自检，单个 prompt 约 3000 字
Node 8 的 prompt 包含：定向读取指令 + 全局声明 + 8个 Module 说明 + 完整评分规则 + 输出格式要求，约 4000 字
writing_policy 在 Node 6 生成、Node 7 读取、Node 8 审计，三个节点都需要理解同一个数据结构，但没有共享的 schema 定义
迁移建议：

① 将 writing_policy 的 JSON Schema 定义为独立文件：
   writing_policy_schema.json
   所有节点引用同一 schema，不在 prompt 中重复定义

② Node 7 的 6 条硬性约束提取为独立规则文件：
   rules/listing_generation_rules.md
   prompt 中只引用文件路径，不内联规则内容

③ Node 8 的评分规则提取为独立文件：
   rules/algorithm_scoring_rules.md
   prompt 中只引用章节编号，不内联评分逻辑

④ 使用 system prompt + user prompt 分离：
   system prompt：角色定义 + 规则文件引用 + 禁止事项
   user prompt：当前任务的具体输入数据
H-4. 工具绑定不合理
问题描述：

Node 3 使用 execute_code 执行 LLM 生成的 Python 代码，代码质量不稳定，且沙箱无法访问 LLM 上下文中的文件
Node 8 强制使用 generate_doc 工具，但工具调用失败时没有降级方案
Node 9 使用 execute_code 生成 Word 文档，沙箱环境的 python-docx 版本不可控
迁移建议：

Node 3 → 替换为本地 Python 脚本（parse_csv.py + extract_fields.py）：
  不依赖 LLM 生成代码，字段映射逻辑固化

Node 8 → 替换为直接 LLM API 调用，输出 Markdown 文本：
  不依赖 generate_doc 工具，Markdown 文本更易于后续处理

Node 9 → 替换为本地 export_docx.py 脚本：
  使用固定版本的 python-docx，不依赖沙箱环境
H-5. 输出难审计
问题描述：

当前工作流没有强制的 audit_trail 输出机制，审计信息散落在各节点的 contentPreview 中
Module 8 评分表在 v8.4.0 之前只输出汇总分，不输出逐维度明细（已在 v8.4.0 修复）
无法从输出中判断哪些输入文件被实际读取、哪些字段被使用
迁移建议：

① 每个节点执行后必须输出结构化的 node_audit 对象：
   {
     "node_id": "...",
     "inputs_received": [...],
     "inputs_used": [...],
     "inputs_ignored": [...],
     "output_fields": [...],
     "warnings": [...]
   }

② 最终 audit_trail.json 由各节点的 node_audit 汇总生成

③ Module 8 评分必须输出逐维度明细表（v8.4.0已实现）

④ 增加 listing_field_traceability：
   每个 Listing 字段（Title/B1-B5/ST等）标注来源
   示例：title.keyword_source = "L1: action cam (ABA rank 1)"
I. Refly 外复刻方案
I-1. 保留为 Prompt 的部分
以下逻辑适合保留为 LLM prompt 调用：

① 视觉审计（Node 2）
   输入：图片列表
   输出：visual_audit JSON
   理由：纯多模态推理，无法用脚本替代

② COSMO 意图图谱（Node 4）
   输入：High-Conv 关键词列表
   输出：intent_graph JSON
   理由：语义理解任务，LLM 优于规则脚本

③ 产品战略侧写（Node 6）
   输入：军火库 + 视觉审计 + 意图图谱 + 属性表
   输出：strategy_profile JSON（含 writing_policy）
   理由：需要跨多源数据的语义整合，LLM 核心能力

④ Listing 文案生成（Node 7）
   输入：writing_policy + 军火库 + 语种
   输出：listing_draft JSON
   理由：创意生成任务，LLM 核心能力

⑤ 最终仲裁报告生成（Node 8 的 Module 1-7 部分）
   输入：listing_draft + strategy_profile + intent_graph
   输出：final_report.md
   理由：综合分析和报告撰写，LLM 核心能力
I-2. 改成规则文件的部分
以下逻辑适合提取为独立规则文件（Markdown/JSON）：

① writing_policy_schema.json
   内容：writing_policy 的完整 JSON Schema 定义
   被引用：Node 6（生成时）/ Node 7（约束时）/ Node 8（审计时）

② rules/keyword_tiering_rules.md
   内容：L1/L2/L3 分级阈值（search_volume 阈值 + High-Conv 判定条件）
   被引用：Node 3（分级时）/ Node 8（keyword_tiering 评分时）

③ rules/algorithm_scoring_rules.md
   内容：A10/COSMO/Rufus/价格竞争力完整评分规则
   被引用：Node 8（评分时）

④ rules/listing_generation_rules.md
   内容：6条硬性约束（Rule 1-6）+ 8项自检清单
   被引用：Node 7（生成时）

⑤ rules/field_mapping_rules.md
   内容：CSV 字段语义映射规则（ABA/竞品/全维度表）
   被引用：parse_csv.py

⑥ rules/doc_priority_rules.md
   内容：P0-P4 优先级层级 + 冲突处理规则
   被引用：所有节点
I-3. 改成脚本的部分
以下逻辑适合改成本地 Python 脚本：

① scripts/normalize_inputs.py
   输入：inputs/ 目录 + run_config.json
   输出：normalized_input.json + validation_report.json
   逻辑：必需文件校验 + 语种映射 + 站点文件一致性校验

② scripts/parse_csv.py
   输入：CSV 文件路径 + file_type（aba/competitor/full_dimension）
   输出：标准化 DataFrame + mapping_report
   逻辑：自动检测分隔符 + 语义字段映射 + BOM 头处理

③ scripts/extract_fields.py
   输入：aba_df + competitor_df + full_dimension_df + specs_text
   输出：arsenal_output.json
   逻辑：L1/L2/L3 分级（硬编码阈值）+ Score 计算 + 能力熔断 + price_context

④ scripts/validate_required_fields.py
   输入：strategy_profile.json
   输出：policy_validation.json
   逻辑：writing_policy 完整性校验 + 四类 binding_type 覆盖检查

⑤ scripts/audit_output.py
   输入：所有中间输出 JSON
   输出：audit_trail.json
   逻辑：字段使用统计 + L1/L2/L3 分布统计 + 边界声明检查 + A+字数统计

⑥ scripts/export_docx.py
   输入：final_report.md + brand + site
   输出：Amazon_Listing_{brand}_{site}_v840.docx
   逻辑：Markdown → Word 转换，保留标题层级和表格格式
I-4. 改成固定输入模板的部分
以下逻辑适合固化为输入模板：

① run_config.json 模板
{
  "brand": "",
  "site": "DE",
  "language": "German",
  "selling_points": "",
  "specs_supplement": ""
}

② product_specs.txt 模板
品牌: {brand}
型号: {model}
分辨率: {resolution}
防抖: {stabilization_description}
防水: {waterproof_description}
屏幕: {screen_description}
连接: {connectivity}
电池: {battery_capacity}
重量: {weight}
尺寸: {dimensions}
配件: {accessories_list}

③ specs_supplement.txt 模板
参数约束（不建议宣传的能力）
- {capability}: {constraint_description}
  
参数补充（属性表未覆盖的信息）
- {parameter}: {value}
I-5. 需要增加中间审计输出的部分
以下环节在当前 Refly 版本中缺少中间审计，迁移时必须补充：

① Node 3 执行后：
   输出 csv_parsing_report.json
   记录：哪些列被成功映射 / 哪些列映射失败 / 实际读取的行数

② Node 6 执行后：
   输出 writing_policy_validation.json
   记录：四类 binding_type 是否全部覆盖 / 缺失的 binding_type 及原因

③ Node 7 执行后：
   输出 self_check_report.json（8项自检结果）
   记录：每项是否通过 / 未通过项的具体原因

④ Node 8 执行后：
   输出 scoring_detail.json（逐维度得分 + 说明简述）
   输出 audit_trail.json（全流程审计汇总）

⑤ 全流程结束后：
   输出 listing_field_traceability.json
   记录：每个 Listing 字段的关键词来源（如 title 中的 L1 词来自哪条 ABA 数据）
J. 验收标准
J-1. 输入完整时的预期输出
当以下输入全部提供且格式正确时：
- aba_keywords.csv（含关键词/搜索量/转化率）
- competitor_words.csv（含均价/购买率）
- product_specs.txt（键值对格式）
- full_dimension.csv（含差评关键词/高频问题）
- product_images/（≥1张）
- algorithm_rules_v2.md（Markdown章节结构）
- compliance_rules.txt
- brand_name / site / selling_points
  
预期输出：
① arsenal_output.json
- reserve_keywords 列表非空，含 L1/L2/L3 分级
- price_context.price_median 有具体数值
- competitor_brands 列表非空
- review_pain_points 列表非空
- circuit_breaker_applied = true（如有参数约束）
  
② strategy_profile.json
- writing_policy 5个子字段全部非空
- capability_scene_bindings 覆盖四类 binding_type
- faq_only_capabilities 包含受限能力
- bullet_slot_rules B1-B5 全部有规则
  
③ listing_draft.json
- self_check 8项全部为 true
- title 前80字符含品牌名+类目词+L1词+场景词
- search_terms 字节数 ≤ 250
- aplus_content 字数 ≥ 500
  
④ final_report.md
- 包含 Module 1-8 全部内容
- Module 8 输出逐维度得分表（非仅汇总分）
- 所有说明性文字为中文
- Listing 内容为目标语言
  
⑤ scoring_detail.json
- A10/COSMO/Rufus 三个维度各有逐项得分
- 价格竞争力有具体得分（非"数据缺失"）
- boundary_declaration_check.exists = true
- aplus_word_count_check.meets_minimum = true
  
⑥ audit_trail.json
- used_docs 包含所有输入文件
- ignored_docs 为空或仅含合理原因
- risk_flags 为空
- l1_l2_l3_distribution 中 search_terms.l3 > 0
J-2. 输入缺失时的降级行为
缺失必需输入时：
  → 立即终止，输出错误信息，不生成任何 Listing
  → 错误格式：MISSING_REQUIRED_INPUT: {input_name}
  → 不得静默失败

缺失可选输入时：
  competitor_words.csv 缺失：
    → price_context = null
    → Node 8 价格评分标注"数据缺失，跳过评分"
    → 总分分母从310降为300
    → audit_trail.missing_inputs 记录

  full_dimension.csv 缺失：
    → review_pain_points = []
    → FAQ 生成退化为基于属性表推断
    → audit_trail.missing_inputs 记录

  product_images 缺失：
    → visual_audit 跳过
    → strategy_profile.visual_tags = []
    → audit_trail.missing_inputs 记录

  specs_supplement 缺失：
    → 仅用 product_specs.txt 执行熔断
    → audit_trail.optional_missing 记录

CSV 字段映射失败时：
  → 跳过该字段，不终止执行
  → audit_trail.ignored_docs 记录失败原因
  → 不得用 LLM 推断替代缺失字段
J-3. 输出质量评估标准
Title 质量：
  ✅ 前80字符含品牌名 + 类目词 + L1词 + 最高优先级场景词
  ✅ 总字符数 ≤ 200
  ✅ 无 faq_only_capabilities 中的能力词
  ✅ 无 L3 长尾词
  ✅ 无竞品品牌名

Bullets 质量：
  ✅ B1-B5 每条满足 bullet_slot_rules 的强制规则
  ✅ B4 含边界声明句（"Optimized for X; not engineered for Y"格式）
  ✅ 每条 ≤ 250 chars
  ✅ 无 faq_only_capabilities 中的能力词
  ✅ 无 forbidden_pairs 中的能力组合同句出现

FAQ 质量：
  ✅ 覆盖防水/防抖/兼容性/电池/配件 5个类型
  ✅ 每个回答含具体数字或条件
  ✅ faq_only_capabilities 中的能力在此详细说明
  ✅ 无空洞回答（如"效果很好"）

Search Terms 质量：
  ✅ 字节数 ≤ 250（UTF-8编码验证）
  ✅ 无重复词
  ✅ 无品牌词
  ✅ 无 Title/Bullets 中已出现的词
  ✅ 含 L3 词

算法评分质量：
  ✅ 三个维度各有逐项得分（非仅汇总）
  ✅ 每个维度有说明简述
  ✅ 得分与文案内容一致（可人工抽查验证）
  ✅ 无明显抬分（如文案明显不满足规则但得满分）
J-4. 文档引用透明度判断标准
判断文档引用是否透明的方法：

① 检查 audit_trail.used_docs：
   所有声称使用的文档是否都在 used_docs 列表中
   used_docs 中的文档是否都有对应的输出字段

② 检查 audit_trail.ignored_docs：
   存在但未被使用的文档是否都有明确原因
   原因是否合理（如"字段映射失败"而非"无原因"）

③ 检查 arsenal_output.json：
   reserve_keywords 中的词是否能在 ABA CSV 中找到对应行
   price_context.price_median 是否能从竞品 CSV 的均价列计算得出
   review_pain_points 是否能在全维度表中找到来源

④ 检查 strategy_profile.verified_specs：
   所有参数是否都能在 product_specs.txt 中找到对应条目
   如有参数在属性表中不存在，标记为"编造参数"

⑤ 检查 listing_draft 的 self_check：
   8项自检是否都有明确的 true/false 结果
   如有 false 项，是否有对应的修正记录
J-5. 新工作流与当前版本能力一致性判断
使用同一组测试输入（DE站 TOSBARRFT 产品），对比以下指标：

关键词处理一致性：
  ✅ L1 词列表与当前版本基本一致（允许±1个词的差异）
  ✅ High-Conv 标记词与当前版本一致
  ✅ price_context 能被成功提取（当前版本未实现，新版本应修复）

writing_policy 一致性：
  ✅ scene_priority 顺序与当前版本一致
  ✅ faq_only_capabilities 包含"5K防抖"和"4K防抖效果对比"
  ✅ forbidden_pairs 包含["5K视频", "防抖"]
  ✅ 四类 binding_type 全部覆盖（当前版本已实现）

文案生成一致性：
  ✅ Title 前80字符结构与当前版本一致
  ✅ B4 含边界声明句（当前版本已实现）
  ✅ FAQ 第2条明确说明5K不支持防抖
  ✅ Search Terms 字节数 ≤ 250

评分一致性：
  ✅ Module 8 输出逐维度得分表（当前版本已实现）
  ✅ 价格竞争力评分有具体数值（当前版本未实现，新版本应修复）
  ✅ boundary_declaration_check 和 aplus_word_count_check 字段存在

新版本必须修复的问题（当前版本已知缺陷）：
  ✅ 竞品 CSV 被有效读取（price_context 有具体数值）
  ✅ 全维度表被有效读取（review_pain_points 非空）
  ✅ 站点文件不一致时输出 SITE_FILE_MISMATCH 警告
  ✅ audit_trail.json 作为强制输出项
PRD 文档完整输出结束。

全文共 10 个章节（A-J），覆盖：背景目标、12项输入定义、10项输出定义、5阶段11步骤流程、9个节点清单、10类规则系统、8个数据结构、5类问题与迁移建议、5类复刻方案、5维验收标准。所有逻辑均显式展开，可直接复制到 Claude Code 本地项目中使用。
