# 亚马逊算法底层逻辑与3C数码Listing优化知识库 v2.0

> **用途说明**：本文档为Listing工作流AI知识库，面向3C数码品类（耳机/TWS、蓝牙音箱、充电器、移动电源、手机配件等），删除一切历史背景和前言段落，聚焦算法底层逻辑与可执行操作规则。

***

## 第一章：算法架构——三位一体的运作逻辑

### 1.1 A10：排序引擎（肌肉层）

A10的核心目标是最大化每次点击的购买转化概率。其排名信号权重分布如下：

| 排名信号 | 权重级别 | 3C品类关键动作 |
|---------|---------|-------------|
| **有机销量（Organic Sales）** | ★★★★★ 至高 | 自然搜索产生的购买是最强产品-市场匹配信号，必须优先优化长尾词转化 |
| **点击率（CTR）& 转化率（CVR）** | ★★★★ 极高 | 主图+标题前70字符构成点击钩子；进入页面后的停留时长是转化信号 |
| **PPC驱动销量** | ★★★ 中等 | A10大幅降低广告驱动权重，单靠广告无法"买"到第一位 |
| **站外流量（External Traffic）** | ★★★★ 关键 | Google、TikTok、YouTube等外部来源的转化获得"信任加权"，并带动语义词排名 |
| **卖家权威性（Seller Authority）** | ★★★★ 高 | ODR（订单缺陷率）、退货率、Feedback评分直接影响单品排名；库存深度影响配送确定性 |
| **用户行为深度** | ★★★ 中 | PDP停留时长、是否点击Q&A、是否观看视频，均为A10行为分析数据点 |

**3C品类特殊性**：A10对3C品类表现出"防御性"特征——因电子产品退货率高、参数复杂，算法特别看重"确定性信号"（参数具体、兼容性明确、承诺边界清晰）。

**外部流量信任背书机制**：来自高权重外域（The Verge、Tom's Guide、YouTube评测）的流量并产生转化时，A10会对该Listing追加信任加权，同时带动相关语义词的自然排名。A+页面的Alt Text现被Google索引，是外部流量进入的渠道之一。

***

### 1.2 COSMO：语义大脑（意图层）

**COSMO（Common Sense Knowledge Generation）** 是基于LLM训练的电商意图知识图谱，通过分析数亿次用户"搜索→购买"和"共同购买"行为，构建跨越"词汇鸿沟"的语义理解能力。

**核心规模参数**：
- 6.3亿个概念节点，覆盖产品属性、使用场景、目标人群
- 2900万条关系边（2490万来自共同购买行为，510万来自搜索后购买）
- 覆盖18个主要品类，含Electronics（电子）

**COSMO四类核心关联逻辑（对应Listing优化策略）**：

| 关联类型 | 定义 | 3C优化实例 |
|---------|------|----------|
| **used_for_func**（功能关联） | 产品功能性的常识关联 | 主动降噪耳机 → 覆盖"隔音、安静、专注"节点 |
| **used_for_eve**（事件关联） | 产品与特定事件/场合的关联 | 将充电宝与"商旅出差""长途飞行""户外节"挂钩 |
| **used_for_aud**（受众关联） | 产品与受众群体的常识匹配 | 明确写出"专为游戏玩家""通勤族首选""适合学生" |
| **capable_of**（能力推理） | 对产品潜在属性的常识推理 | 写"3,950mAh × 7 cells"而非"20000mAh"，提供底层能力证明 |

**COSMO推理案例（3C）**：
- 用户搜索："iPad Pro traveling charger"
- COSMO推理链：旅行 → 插座有限 → 需要多口；减重需求 → GaN技术；iPad Pro快充 → ≥30W
- 映射属性节点：【GaN】【Foldable Plug】【Multi-port】【>30W Output】
- 结果：即使标题没有"traveling"这个词，只要属性对齐，COSMO仍会推荐

***

### 1.3 Rufus：对话界面（交互层）

Rufus是基于**RAG（检索增强生成）架构**的AI购物助手，调用COSMO知识图谱+亚马逊实时数据库生成回答，运行在80,000+ AWS Trainium和Inferentia2芯片上，响应延迟控制在1秒内。

**Rufus数据抓取的优先级排序（置信度由高到低）**：

| 优先级 | 数据来源 | 特征 | 关键执行规则 |
|--------|---------|------|------------|
| **P0 核心** | 结构化属性（Structured Data） | 被视为"已验证事实"，空值=数据盲区 | 空值即死亡（Death of Null）：未填写≠可能存在，Rufus会直接推荐竞品 |
| **P1 关键** | 买家评论（Reviews）& Q&A | "地面真理（Ground Truth）"，用于回答主观/体验问题 | 评论与Listing不一致时，Rufus引用评论并可能发出警告 |
| **P2 重点** | 五点描述（Bullet Points） | 功能/场景/利益的核心文本来源，偏好名词短语 | 每条Bullet必须是可独立被AI引用的"答案块" |
| **P3 支撑** | 图片（OCR）& A+内容 | 多模态：OCR读取图片文字，CV识别场景 | 图片关键参数需大字高对比度；A+需≥500字可索引文本 |
| **P4 补充** | 产品长描述（Description） | 最低权重，仅作语义补充 | 补充Bullet未覆盖的冷门长尾场景 |

**Rufus推荐的硬性过滤条件**：
- 评分 < 4.0分 → 直接不进入推荐候选池
- 缺货状态 → 直接排除
- Listing文案 ↔ 后台属性 ↔ 评论三方信息存在矛盾 → 降低推荐置信度

**Rufus Score权重模型（逆向工程推导）**：

| 维度 | 权重 | 计算逻辑 |
|------|------|---------|
| 语义匹配度 | 25% | 买家提问与Listing内容的语义向量余弦相似度，最关键维度 |
| 销量增长趋势 | 20% | 关注近期销量的Log增长率，而非累计总销量（对新品有利） |
| 品牌信任分 | 15% | 综合评分×评论数的权重组合，衡量市场验证充分程度 |
| 评分质量 | 12% | 使用评论数平方根作为置信度，过滤评论数极少的虚高分产品 |
| 价格竞争力 | 10% | 定价在品类中位数85%-110%的"甜蜜区"获得最优评分 |
| 流量覆盖深度 | 8% | 在不同语义节点上的自然曝光能力 |
| 新鲜度补偿 | 5% | 平衡老品优势，确保推荐池多样性 |
| 亚马逊自营加分 | 3% | FBA配送可靠性的隐性加权 |
| 协同过滤关联度 | 2% | 购物篮关联（买了A也买了B），增强品牌矩阵内推荐流 |

***

## 第二章：三系统协同关系

```
用户输入关键词/自然语言问题
        ↓
   A10（词法匹配+概率排序）
   → 生成候选商品池（基于倒排索引）
        ↓
   COSMO（意图语义扩展）
   → 用知识图谱扩展相关性，填补词汇鸿沟
   → 注入场景/人群/功能关联节点
        ↓
   Rufus（RAG生成回答）
   → 从候选池中检索证据源（评论/Q&A/Listing文本/图片OCR）
   → 生成自然语言推荐，直接引用Listing中的具体数据作为"证据"
```

**Listing的核心定位转变**：Listing不是给"人"看的广告单，而是给"机器"读的结构化知识库（Listing as a Datasource）。A10需要关键词覆盖+销量维持；COSMO需要场景定义+属性对齐；Rufus需要评价情绪+Q&A深度。

***

## 第三章：标题优化规则

### 3.1 标题生成公式

```
[品牌] + [核心产品名词短语] + [关键参数（带具体数字）] + [差异化卖点] + [兼容性]
```

**前70字符规则**：移动端视图仅显示前70字符，必须在此范围内包含：
- 核心钩子（如：200W、GaN、IPX5）
- 品牌名
- 最强差异化卖点

**有效 vs 无效示例**：

| ❌ 无效写法 | ✅ 有效写法 | 原因 |
|-----------|-----------|------|
| "Bluetooth Earbuds Wireless TWS Noise Cancelling Long Battery" | "True Wireless Earbuds, 40H Playtime ANC IPX5, for Commuting & Workout" | 有具体数据、明确场景 |
| "快充充电器 氮化镓 多口 便携" | "200W GaN Charger 4-Port, PD 3.1 Foldable Plug for MacBook & iPhone 15" | 参数量化、协议明确、兼容性枚举 |
| "quality earbuds best sound" | "ANC Earbuds -35dB Noise Reduction, 30H Battery, IPX5 for Open Office" | 绝对化描述改为量化证据 |

**禁止行为**：
- 重复堆砌同义形容词（Very fast / quick / rapid）
- 使用模糊边界词（"高质量""最好的""万能"）
- 标题内容与后台Count/Variant属性矛盾（如标题写"3 Pack"但后台Unit Count=1）

***

## 第四章：五点描述（Bullet Points）优化规则

### 4.1 RAG-Ready Bullet结构

每条Bullet必须是"可被Rufus直接提取并引用"的独立答案块，结构为：

```
[全大写功能名词短语]: [技术原理/规格数据] + [解决的具体痛点] + [支撑证据数据]
```

**必须使用完整句子**（破碎的关键词组合导致AI提取失败）。

**"疼痛/解决方案"矩阵示例（3C品类）**：

| 竞品常见差评痛点 | Bullet写法模板 |
|---------------|--------------|
| "线缆容易断裂" | **ULTRA-DURABLE BRAIDED NYLON**: Reinforced fiber core withstands 25,000+ bends, preventing fraying at the connector during daily charging. |
| "充电宝虚标容量" | **VERIFIED 27,650mAh CAPACITY**: Built with 3,950mAh × 7 cells (14.5Wh verified), charges iPhone 15 Pro 5× or MacBook Air M2 to 80%. |
| "充电头过热" | **ACTIVETEMPERATURE SHIELD**: Monitors device temperature 3 million times/day via GaNPrime tech, cutting off at 45°C to prevent overheating. |
| "降噪效果不稳定" | **ADAPTIVE ANC -35dB**: Dual microphone array auto-adjusts noise cancellation level for subway (85dB), open office (65dB), and flight (90dB) environments. |

### 4.2 五条Bullet的场景-意图分配（3C耳机示例）

| Bullet位置 | 覆盖意图维度 | 内容要求 |
|-----------|------------|---------|
| Bullet 1 | 核心功能+量化数据 | 最强卖点，含具体参数（dB、mW、ms等） |
| Bullet 2 | 使用场景A（运动/户外） | IPX等级+具体活动+测试条件 |
| Bullet 3 | 使用场景B（商务/通勤） | 麦克风质量+通话测试+续航数据 |
| Bullet 4 | 兼容性/人群定向 | 支持设备型号枚举+目标人群描述 |
| Bullet 5 | 边界声明+差异化 | 明确写出"不适合什么"，建立高确信度边界 |

**"边界声明"策略**：明确说"不适合什么"比模糊的正面承诺更有效。Rufus将有明确边界的描述判定为高可信度事实（如："Optimized for commuting noise; not engineered for professional studio recording"）。

***

## 第五章：后台属性字段——COSMO的精准数据源

### 5.1 完整性原则（空值即死亡）

所有非必填字段**严禁留空**。未填写字段在Rufus的逻辑里等于"不存在"，而非"可能存在"。

| 字段类型 | 3C关键字段 | 为什么不能为空 |
|---------|-----------|-------------|
| 技术规格 | 充电功率（W）、蓝牙版本、频率响应、续航时长 | Rufus用于精准筛选（"30W以上快充"） |
| 防护等级 | IPX等级（IPX4/IPX5/IP67） | 运动/户外场景匹配的硬性过滤条件 |
| 连接协议 | Qualcomm aptX/LDAC/AAC、PD协议版本 | 技术买家的精准搜索词 |
| 兼容性 | 支持设备型号（Top 50热门机型） | Rufus对"是否兼容X"做精确字符串匹配 |
| 使用场景 | Intended Use（Travel/Gaming/Business等，填满5个） | COSMO图谱节点挂载依据 |
| 目标人群 | 专业游戏/商务出行/运动健身 | COSMO人口统计学关系匹配 |
| 包装内容 | 线缆类型、附件清单 | 降低预期不符导致的退货 |

### 5.2 兼容性枚举规则

**禁止**：只写"Universal Compatibility"  
**要求**：枚举当前市场Top 50热门机型（iPhone 16/15/14、Galaxy S25/S24、MacBook Air M3/M4等）  
**原因**：Rufus处理"Does it work with X?"时做精确字符串匹配，模糊声明无法通过验证

***

## 第六章：评论与Q&A管理——Rufus的"地面真理"

### 6.1 三方信息一致性原则

**核心规则**：Listing文案 × 后台属性 × 评论/Q&A 三方必须相互印证。

- Listing写"主动降噪"，但评论集中出现"噪音明显"→ Rufus降低推荐置信度
- 标题写"金色"，评论普遍反馈"实物偏绿"→ Rufus在摘要中自动发出警告
- 声称"防水"但评论出现"雨天进水"→ Rufus引用评论负面反馈，劝退用户

**解决方案**：在Listing中主动声明适用边界（如"IPX5 rain-resistant; not designed for submersion"），降低评论与文案的差距。

### 6.2 Q&A战略布局（主动喂食Rufus）

Q&A是卖家**唯一可以直接以"问答对"形式向Rufus灌输知识的渠道**，必须主动预埋。

**3C品类必埋Q&A类型**：

| Q&A类型 | 示例问题 | 优化写法要求 |
|---------|---------|------------|
| 飞行安全 | "Can I bring this on a plane?" | 明确写出："Yes, at 27,650mAh (99.35Wh), this is below the 100Wh airline limit. TSA-compliant." |
| 精确兼容性 | "Does this work with Samsung Galaxy S25?" | 明确肯定+说明支持的充电协议（如PPS 45W Super Fast 2.0） |
| 边充边放 | "Can I charge my laptop while charging the power bank?" | 明确说明pass-through charging的功率分配数据 |
| 具体场景 | "Will these earbuds stay in during intense workouts?" | 说明IPX5+耳翼设计+测试条件（跑步/跳绳） |
| 协议支持 | "Does it support LDAC for Sony WH-1000XM5?" | 明确肯定+说明适用设备和操作步骤 |

**预埋规则**：
- 使用包含长尾意图词的完整问句（而非简短模糊的问题）
- 回答必须包含具体数据，不能含糊
- 至少预埋5-10个覆盖高技术难度问题的Q&A对

### 6.3 评论引导策略

**目标**：引导带有具体使用场景的评论，而非"质量好"类通用好评

**插卡/邮件引导话术方向**：
- "您是在健身房使用还是日常通勤？我们很好奇它在您的场景下的表现"
- "如果您满意，能否分享一下您用它解决了什么具体问题？"

**有价值的评论特征**：包含具体场景（通勤/健身/出差）、提及具体功能（降噪效果/续航）、给出前后对比

***

## 第七章：图片与A+内容——机器可读的视觉语言

### 7.1 主图规则

- RGB纯白底（255, 255, 255），无阴影遮挡
- 产品100%可见，从多角度展示（如耳机：正面+充电盒打开状态）
- 不含促销文字、水印（主图）

### 7.2 副图优化策略（Rufus的多模态数据源）

Rufus具备**OCR文字识别**和**场景视觉理解**能力，图片内的文字和场景均被抓取。

| 图片位置 | 3C优化目标 | 具体执行规则 |
|---------|-----------|------------|
| 副图1 | 使用场景A（运动/户外） | 模特佩戴真实场景（跑步道/地铁），背景真实而非棚拍白底 |
| 副图2 | 使用场景B（办公/游戏） | 展示多设备连接、桌面环境、显示器旁使用 |
| 副图3 | 技术参数信息图（OCR关键） | 续航时长、ANC等级、防水等级以**60pt+大字、高对比度**标注 |
| 副图4 | 兼容性/尺寸对比 | 与常见机型/设备的接口/尺寸直观对比 |
| 视频 | 功能演示+场景验证 | 降噪效果前后对比、快充速度演示、佩戴稳定性测试 |

**OCR优化关键**：图片中的文字（如"ANC -35dB""IPX5""40H Battery"）会被Rufus直接读取，与Listing文案形成三方互证，提升推荐置信度。

**场景图规则**：若产品主打"露营"，背景必须是帐篷/户外场景；不能出现与声称场景矛盾的背景，否则CV会误判属性节点。

### 7.3 A+内容优化规则

A+内容是Rufus的二级信息来源，3C品类必须包含：

1. **对比表（Comparison Chart）**：横向对比自家不同型号的核心参数（功率/容量/重量/价格）。Rufus在回答"XX和YY有什么区别"时直接提取表格数据。利用"锚定效应"将本品与低阶产品对比（突出优势）。
2. **场景故事模块**："通勤族的一天" / "商旅人士的出行方案"，图文展示多场景使用。
3. **技术规格深度解析**：用自然语言解释参数（如"什么是ANC？我们如何实现-35dB"），提升AI的语义可读性。
4. **Alt Text工程化**：每张A+图片必须填写自然语言描述，格式："[品牌][产品名]在[场景]中[动作]，用于[目的]"。例如："Anker Prime power bank on a desk charging a laptop and phone simultaneously for office productivity." Alt Text被Google索引，是外部SEO的重要渠道。

***

## 第八章：关键词策略——L1-L3三级矩阵

### 8.1 关键词分级结构

| 层级 | 类型 | 作用 | 3C示例 |
|------|------|------|--------|
| **L1** | 一级核心词 | 提供基础曝光，维持类目权重 | bluetooth earbuds, TWS headphones, USB-C charger |
| **L2** | 二级场景词 | 精准匹配规格需求，转化率主力 | noise cancelling earbuds for commuting, 65W GaN charger for MacBook |
| **L3** | 三级长尾意图词 | 直接响应Rufus语义查询，GEO竞争核心 | earbuds that stay in during marathon, fast charger compatible with Galaxy S25 Ultra PPS |

**L3关键词是Rufus时代最高价值词**：意图极强、竞争低、直接与用户对话匹配。

### 8.2 后台Search Terms填写规则

- 填入COSMO场景节点词：Office、Commute、Gaming、Content Creation、Travel
- 填入受众词：Gamers、Travelers、Students、Remote Workers
- 不需要重复标题和Bullet中已有的词（亚马逊会自动索引前端内容）
- 不填竞品品牌词（违规风险）

***

## 第九章：PPC广告策略——AI时代的精准投放

### 9.1 广告类型与执行逻辑（3C数码）

| 广告类型 | 3C执行策略 | 核心KPI |
|---------|-----------|--------|
| **Sponsored Products - 精准词** | L2+L3场景意图词（如"ANC earbuds for commuting"） | ACOS < 毛利率 |
| **Sponsored Products - 竞品ASIN** | 投放同价位直接竞品ASIN | 点击成本 vs 转化率比 |
| **Sponsored Brands** | 品牌词防御性出价 + 品类词拦截 | 新客获取率 |
| **Sponsored Display - 再营销** | 访问过但未购买的用户 | ROAS |
| **Sponsored Prompts（2025年新）** | 在竞品页触发Rufus对话，弹出场景化问题引导推荐 | 曝光率+对话参与率 |

**Sponsored Prompts关键规则**：排名不完全依赖出价，**评分、评论质量、Listing完整度**是核心权重因子。评分未达4.0时投放此类广告位会浪费预算。

### 9.2 目标ACOS参考基准

| 阶段 | 目标ACOS | 说明 |
|------|---------|------|
| 新品期 | ≤35% | 与毛利率持平，以销量信号为主目标 |
| 成长期 | 15%-25% | 广告与有机协同增长 |
| 成熟期 | 10%-20% | 以利润优化为主 |

**关键指标**：TACoS（总广告销售占比）随时间下降 = 广告正在驱动有机排名提升，是健康增长的核心标志。

### 9.3 场景词广告策略

将Rufus对话中提取的高频场景问题转化为广告关键词：
- "earbuds for zoom calls" / "commute subway noise earbuds"
- "charger for gaming setup multi-port"
- "power bank airline approved under 100wh"

这类词成本低、意图精准，COSMO会将广告点击和转化快速绑定到对应场景节点。

***

## 第十章：站外流量——A10的重要加权

### 10.1 外部流量的算法价值

来自Google、TikTok、YouTube的自然流量对排名提升效果**优于相同量级的PPC**，原因：外部流量用户的购买意图更强，转化率信号质量更高。

### 10.2 Brand Referral Bonus（品牌推荐奖金）

- 品牌注册卖家通过Attribution链接导流产生的销售，亚马逊返还约**10%销售额**
- TikTok带货+Attribution链接=外部流量信号+排名提升+10%返还，三重收益
- 站外销售计入销售速度，间接提升关键词自然排名

**3C数码最有效的站外渠道**：YouTube产品评测视频（高权重外域，产生转化后带动相关语义词排名）、科技博客（Tom's Guide类媒体背书）、TikTok场景测评。

***

## 第十一章：Rufus逆向分析工作流

### 11.1 竞品分析四步法

**第一步：模拟用户对话，绘制意图漏斗**
- 宽泛问题："推荐一款蓝牙耳机"
- 加场景条件："专门用于通勤的主动降噪TWS，预算$80"
- 进一步收窄："适合安卓手机、支持LDAC、轻量"
- 记录每轮被持续推荐的ASIN，分析哪类条件触发过滤

**第二步：解剖持续被推荐的竞品**
- 检查COSMO三类意图（功能/情境/人口统计）各覆盖了哪些维度
- 统计评论中高频正面关键词（与Listing一致的词）
- 查看后台属性填写完整度
- 分析Q&A预埋的问题类型

**第三步：找出自身意图覆盖盲区**
- 对比竞品已覆盖而自身未覆盖的场景词
- 列出后台属性中未填写的字段
- 识别Q&A中缺失的关键问题类型

**第四步：修改后验证效果**
- 等待5-7天（系统数据更新周期）
- 以相同问题再次询问Rufus，观察是否出现在推荐结果中

***

## 第十二章：Rufus幻觉风险规避协议

当Listing信息不完整或存在矛盾时，Rufus会产生"幻觉"（Hallucination）——给出错误或保守的回答，通常表现为"不确定"或直接推荐竞品。

| 风险点 | Rufus的错误反应 | 纠正规则 |
|--------|--------------|---------|
| **兼容性字段留空** | "不确定是否兼容X，建议查看竞品" | 强制填充后台Compatibility字段，枚举Top 50机型 |
| **只写"Fast Charging"无数据** | 仅复述"充电快"，无法成为说服用户的证据 | 写"Charges iPhone 15 from 0% to 50% in 30 minutes" |
| **评论中出现"Fire/Hot"** | 直接发出安全警告，劝退用户 | 在五点中强调"Fireproof Materials (UL94 V-0)"和"Temperature Monitoring System" |
| **标题"3 Pack"但后台Unit Count=1** | 判定信息不可信，整体降权 | AI需校验前端文案与后台Unit Count属性的完全一致性 |
| **声称"100%防水"** | 违规被标记（绝对化声明），影响账户健康 | 改为客观参数声明："IPX5 water-resistant (can withstand heavy rain; not submersion)" |
| **场景图与声称场景矛盾** | CV误判属性节点，挂载错误的意图关系 | 确保生活方式图片场景与Listing声称的使用场景严格对应 |

***

## 第十三章：3C品类特殊规则与高频误区

### 13.1 3C品类必遵规则

1. **协议声明要精确**：写"Bluetooth 5.3"比"最新蓝牙"价值高；写"PD 3.0, 65W, 20V/3.25A"比"快充"价值高
2. **防水等级要量化**：写"IPX5"比"防水"价值高；必须在后台填写对应属性字段
3. **续航数据要测试条件**：写"40H total (10H buds + 30H case, at 50% volume, ANC off)"比"40小时续航"价值高
4. **兼容性声明要枚举具体型号**："Compatible with iPhone 16/15/14 Pro, Galaxy S25/S24"比"兼容所有手机"价值高
5. **安全类数据要有认证背书**：充电器/移动电源要写出"UL, CE, FCC certified"并在后台填写认证字段
6. **自造技术名词可建立COSMO独立节点**：如"GaNPrime""ActiveShield 2.0"——这类品牌化技术词在知识图谱中成为独立实体，当用户问Rufus"哪款最安全"时，有具体数据支撑的专有名词置信度远高于通用描述

### 13.2 高频失败误区

| 误区 | 实际损害 |
|------|---------|
| 仍以关键词密度为核心优化 | COSMO识别为"意图不明确"，降低推荐权重 |
| Listing宣称与评论内容不符 | 三方信息不一致，Rufus降低推荐置信度 |
| 评分低于4.0时大力推广 | Rufus直接过滤出推荐池，广告费打水漂 |
| 只优化传统搜索，忽视Rufus对话入口 | 流失增速最快、转化率最高的流量渠道 |
| A+图片不写Alt Text | 损失亚马逊收录+Google SEO双重机会 |
| Q&A等买家自然发问 | 放弃了唯一可以主动向Rufus灌输知识的渠道 |
| 价格定在品类中位数115%以上 | Rufus的价格竞争力维度直接降权（偏离甜蜜区） |

***

## 第十四章：产品实体知识库模板（LLM喂料格式）

在为每个ASIN生成Listing前，应先构建如下结构化知识库作为输入：

```markdown
## 基础属性（符号层 - 面向A10）
- 品牌：
- 类目节点（如：TWS Earbuds / GaN Charger / Power Bank）：
- 核心规格：[功率W] [蓝牙版本] [IPX等级] [续航时长] [重量g]
- 认证：[CE] [FCC] [UL] [航空<100Wh]

## 意图映射（语义层 - 面向COSMO）
- 使用场景：[通勤] [运动] [商旅] [居家办公] [游戏]
- 解决的核心痛点：[具体问题1] [具体问题2] [具体问题3]
- 受众定位：[通勤族/商务人士/学生/游戏玩家/旅行者]
- 核心名词短语（NPO）：[2-3个高意图密度短语]

## 社会证明（验证层 - 面向Rufus RAG）
- 正面评论高频词：[待填入实际评论分析结果]
- 预判差评关键词：[可能出现的负面词]
- 差评免疫说明：[针对预判差评的主动声明策略]
- Q&A预埋问题列表：[5-10个高技术难度问题]

## 兼容性枚举
- 手机型号：[iPhone 16/15/14/13, Galaxy S25/S24/S23, Pixel 9/8...]
- 电脑型号：[MacBook Air M3/M4, MacBook Pro 14/16, Dell XPS, Surface Pro...]
- 支持协议：[PD 3.1 / PPS 45W / Qi2 / LDAC / aptX Adaptive...]
```

***

## 附录A：COSMO意图映射快查表（3C品类）

| 用户搜索意图 | COSMO推断的隐含属性节点 | Listing必须包含的短语/字段 |
|------------|----------------------|------------------------|
| "iPad Pro traveling charger" | GaN, Foldable Plug, Multi-port, >30W | "GaN Technology", "Foldable Prongs", "PD 3.1 30W+", "Compact for Travel" |
| "Power bank for flight" | <100Wh, Compact, TSA Compliant | "Airline Approved", "TSA Friendly", "Below 100Wh limit", 后台Wh字段 |
| "Charger for Samsung S25 super fast" | PPS Protocol, Super Fast 2.0, 45W | "PPS Supported", "45W Super Fast Charging 2.0", "Optimized for Galaxy" |
| "Earbuds for open office zoom calls" | Noise reduction, Mic quality, Multi-device | "ENC Microphone", "Voice Clarity for Calls", "Multipoint Pairing" |
| "Gaming headset low latency" | <40ms, Virtual surround, USB/3.5mm | "≤40ms Gaming Mode", "7.1 Virtual Surround", "Dual Mode USB+3.5mm" |
| "Earbuds that stay in during running" | IPX rating, ear tip design, stability | "IPX5 Sweat-proof", "Memory Foam Ear Tips", "Secure Fit Wing" |
| "Laptop emergency power bank" | >65W PD, High capacity, Pass-through | "100W PD Output", "20,000mAh+", "Charge While Charging", "Emergency Mode" |
| "Wireless charger for nightstand" | Qi2, Low noise, Multi-device | "Qi2 15W Certified", "Silent Fan-free Design", "3-in-1 Stand" |

***

## 附录B：Rufus"幻觉风险"规避速查表

| 风险场景 | Rufus的错误行为 | AI生成时的规避动作 |
|---------|--------------|-----------------|
| Wattage字段未填 | 回答"无法确认功率"→推荐竞品 | 强制填写后台Wattage(W)字段，精确到具体数值 |
| Compatible Devices为空 | 回答"不确定是否兼容X" | 列举具体型号，不写"all devices" |
| 评论含"overheating" | 警告用户安全风险 | Bullet中加入"Temperature Monitoring"+"认证背书" |
| 标题/属性不一致 | 降低整体listing可信度 | AI生成后需做一致性校验（前端文案 vs 后台属性） |
| 图片场景与声称不符 | CV误判意图节点 | 生活方式图场景必须与Listing主要场景100%对应 |