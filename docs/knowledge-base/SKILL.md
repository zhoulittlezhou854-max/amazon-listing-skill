# SKILL: amazon-listing-generator

**版本**: v1.0
**日期**: 2026-04-01
**类目**: 运动相机（Action Camera）
**站点**: DE / FR / US / UK / ES / IT / JP
**维护说明**: 从 REFLY 工作流迁移，初始版本 v1

---

## 1. 用途说明

本 Skill 用于为亚马逊运动相机产品生成完整的 Listing 文案，包括：

- Title（标题）
- 5 条 Bullet Points（五点描述）
- Product Description（产品描述）
- FAQ（5 条问答）
- Search Terms（后台搜索词）
- A+ 内容文案

同时输出：

- 关键词军火库（L1/L2/L3 分级 + High-Conv 标记）
- 产品战略侧写（writing_policy）
- 算法对齐评分报告（A10 / COSMO / Rufus，总分 310+10）
- 合规检查报告

---

## 2. 触发条件

当用户提供以下输入时，执行本 Skill：

1. **基础数据文件**（必需）：
   - 本品属性表.txt（TXT，键值对格式，支持2列/3列）
   - 评论合并表.csv（CSV，多行文本，含Review_Insight数据）
   - ABA关键词表.csv（CSV，市场数据，支持两种格式）
   - 竞品出单词表.csv（CSV，关键词数据）

2. **填槽字段**（通过run_config提供）：
   - 上架国家（必填）：DE/FR/US/UK/ES/IT/JP等
   - 品牌名称（可选，默认"TOSBARRFT"）
   - 核心卖点（可选，可自动提取5-8个卖点）
   - 配件/参数补充（必填，可显式跳过，空字符串表示跳过）

3. **运行配置**：
   - 通过`run_config` JSON文件或直接参数传递
   - run_config schema详见附录A

---

## 3. 执行步骤

### Step 0: 数据预处理与填槽字段解析

**输入**：
- `run_config`: JSON配置，包含填槽字段
- 4个数据文件：本品属性表.txt、关键词表.csv、评论合并表.csv、ABA合并表.csv

**处理流程**：
1. **填槽字段解析**：
   - 上架国家 → 映射目标语言
   - 品牌名称 → 用户输入 > 属性表 > 默认"TOSBARRFT"
   - 核心卖点 → 用户输入（语义提取）或自动提取（属性表+评论）
   - 配件/参数补充 → 用户输入或自动提取（必填，可显式跳过）

2. **文件格式自适应**：
   - 属性表：支持2列/3列格式，模糊字段匹配
   - 关键词表：支持两种CSV格式，数值清洗，多值字段解析
   - 评论表：多行文本处理，分类字段映射

3. **优先级合并**：
   - 填槽信息 > 属性表 > 评论/关键词数据
   - 冲突解决规则应用

4. **质量评估**：
   - 核心卖点数量检查（5-8个）
   - 配件描述必填验证
   - 预处理质量评分计算

**输出**：`preprocessed_data` JSON，包含所有结构化数据

**约束处理**：
- 核心卖点为空时自动提取5-8个卖点
- 配件描述显式跳过时，Listing中不可新增配件场景
- 预处理质量评分输出到最终报告

**调用方式**：

预处理逻辑已实现为独立的 Python 脚本 `tools/preprocess.py`，可通过以下方式调用：

```bash
# 方式1: 使用所有参数
python tools/preprocess.py \
  --run-config path/to/run_config.json \
  --attribute-table path/to/本品属性表.txt \
  --keyword-table path/to/关键词表.csv \
  --review-table path/to/评论合并表.csv \
  --aba-merged path/to/ABA合并表.csv \
  --output preprocessed_data.json \
  --verbose

# 方式2: 使用run_config中的input_files字段
# 在run_config.json中指定文件路径：
# {
#   "target_country": "DE",
#   "brand_name": "MYBRAND",
#   "core_selling_points_raw": "双屏幕，EIS防抖",
#   "accessory_params_raw": "防水壳30米",
#   "input_files": {
#     "attribute_table": "path/to/本品属性表.txt",
#     "keyword_table": "path/to/关键词表.csv",
#     "review_table": "path/to/评论合并表.csv",
#     "aba_merged": "path/to/ABA合并表.csv"
#   }
# }

# 然后运行：
python tools/preprocess.py --run-config run_config.json --output preprocessed_data.json
```

**脚本功能**：
1. 解析填槽字段（核心卖点、配件描述等）
2. 读取并标准化4种输入文件格式
3. 执行语义提取和自动提取算法
4. 计算预处理质量评分（0-100分）
5. 输出结构化JSON数据供后续步骤使用

**输出文件**：`preprocessed_data.json`，包含：
- 所有填槽字段的解析结果
- 标准化的产品属性、关键词、评论、ABA数据
- 质量评分及详细分项
- 语言映射结果

### Step 1: 输入解析

读取 run_config 或从文件路径推断：
- `site` → 映射目标语种（DE→German, FR→French, US/UK→English...）
- `brand` → 品牌名称

### Step 2: 字段提取

**ABA CSV 字段映射**：
| 标准字段 | 可接受列名 |
|---------|-----------|
| 关键词 | keyword / 关键词 / search_term |
| 月搜索量 | search_volume / 月搜索量 / volume |
| 购买率 | conversion_rate / 购买率 / cvr |

**Keyword Protocol 分级规则**：
- 先执行 quality gate：blocked / rejected / natural_only / watchlist 不进入 L1/L2/L3。
- 只对 `quality_status=qualified` 的词做国家/类目相对分层。
- L1：qualified 池中 Top 20% head traffic anchors，优先进入 Title。
- L2：qualified 池中 20%-60% 或 high-conv / blue-ocean conversion 词，优先进入 Bullets。
- L3：qualified 池中 residual / long-tail opportunity，优先进入 backend residual 或 Search Terms。
- 蓝海词不是低流量词；蓝海词 = 有真实需求 + 产品强匹配 + 点击/转化不差 + 竞争压力相对低。

**竞品 CSV 字段映射**：
| 标准字段 | 可接受列名 |
|---------|-----------|
| 均价 | avg_price / 均价 / price |
| 购买率 | conversion_rate / 购买率 |
| 月购买量 | monthly_purchases / 购买量 |

### Step 3: 能力熔断

基于本品属性表，执行以下熔断规则：

**运动相机专项规则**：
| 能力 | 条件 | 动作 |
|-----|------|------|
| 4K宣称 | specs.video_resolution ≥ 3840x2160 | ✅ ALLOW |
| 防水宣称 | specs.waterproof_case_max_depth_m ≥ 10 | ✅ ALLOW（需说明深度） |
| 防抖宣称 | specs.image_stabilization != "None" | 如为 "Digital" 则降级说明 |
| EIS | specs.image_stabilization == "EIS" | ✅ ALLOW |
| WiFi宣称 | specs.connectivity contains "WiFi" | ✅ ALLOW |

**熔断禁止**：
- ❌ "indestructible" / "military grade"
- ❌ "100% waterproof without housing"
- ❌ "fully shockproof"
- ❌ 任何未在属性表中标注的能力

### Step 4: COSMO 意图图谱

基于 High-Conv 关键词，分析：
- User Identity（谁在搜索）
- Purchase Intent（购买阶段）
- Pain Point（解决的问题）
- STAG Grouping（3-5 个场景分组）

### Step 5: writing_policy 生成

生成战略侧写 JSON，必须包含：

```json
{
  "scene_priority": ["户外运动", "骑行记录", "水下探索", ...],
  "capability_scene_bindings": [
    {
      "capability": "4K录像",
      "binding_type": "used_for_func",
      "allowed_scenes": ["户外运动", "水下探索"],
      "forbidden_scenes": []
    }
  ],
  "faq_only_capabilities": ["数字防抖限制说明"],
  "forbidden_pairs": [["5K", "防抖"]],  // 5K不支持防抖
  "bullet_slot_rules": {
    "B1": "挂载系统 + 主场景 + P0能力",
    "B2": "P0核心能力 + 量化参数",
    "B3": "P1竞品痛点对比 + 场景词",
    "B4": "P1/P2能力 + 边界声明句",
    "B5": "P2质保/售后/兼容性"
  }
}
```

### Step 6: 文案生成

**硬性约束（6条）**：
1. **场景优先级锁定**：严格按 scene_priority 顺序分配场景词
2. **能力场景绑定**：每个能力只能与 allowed_scenes 组合
3. **forbidden_pairs 禁止**：禁止能力组合在同一条文案中出现
4. **边界声明强制**：B4 或 B5 必须含边界声明句
5. **faq_only 限制**：faq_only_capabilities 中的能力只能出现在 FAQ
6. **A+ 字数下限**：≥500 字（英文）

**生成顺序**：Title → B1-B5 → Description → FAQ → Search Terms → A+

### Step 7: 风险检查

**三层检查**：

1. **合规红线**：
   - 无联系方式/URL/社交媒体
   - 无价格/库存宣称
   - 无竞品贬低
   - 无绝对化宣称（100% waterproof / unbreakable）

2. **writing_policy 审计**：
   - 6 条硬性约束逐条核查

3. **Rufus 幻觉风险**：
   - 兼容性字段无空值风险
   - 模糊描述有数据支撑
   - 前端文案与属性表一致

### Step 8: 算法评分

| 算法 | 维度 | 满分 |
|-----|------|------|
| **A10** | title_front_80 / keyword_tiering / conversion_signals | 100 |
| **COSMO** | scene_coverage / capability_scene_binding / audience_tags | 100 |
| **Rufus** | fact_completeness / faq_coverage / conflict_check | 100 |
| **价格竞争力** | price_context 对比 | 10 |
| **总分** | | **310+** |

### Step 9: 输出报告

生成 Markdown 格式报告，包含：
- Module 1: 最终 Listing（目标语言）
- Module 2: 关键词覆盖审计表
- Module 3: 合规红线检查
- Module 4: writing_policy 执行审计
- Module 5: 算法评分详细表 + 优化建议

---

## 4. 核心规则引用

### 4.1 标题规则
- 格式：`[Brand] + [L1关键词] + [场景词] + [核心能力+参数] + [差异化特征]`
- 前80字符：品牌名 + 类目词 + L1能力词 + 场景词
- 字符限制：≤200 chars
- 禁止：faq_only_capabilities / L3长尾词 / 竞品品牌名

### 4.2 Bullet 规则
- B1：挂载系统/主场景 + P0能力 + 参数（大写开头）
- B2：P0核心能力 + 量化参数
- B3：P1竞品痛点对比 + 场景词
- B4：P1/P2能力 + 使用场景 + **边界声明句**
- B5：P2质保/售后/兼容性
- 每条 ≤250 chars

### 4.3 搜索词规则
- ≤250 bytes
- 使用未进 Title/Bullets 的 L2/L3 词
- 无重复，无品牌词

### 4.4 合规禁词

**绝对禁止**：
- contact info / URL / email / social media
- price / discount / sale / deal / coupon
- "better than X" / "beats X"
- best / #1 / top rated / hot / amazing
- guaranteed / 100% guaranteed / money back / risk-free
- competitor brand names

**运动相机专项禁止**：
- bulletproof / indestructible / military grade
- waterproof without housing / fully shockproof

---

## 5. 失败处理

| 失败场景 | 处理方式 |
|---------|---------|
| 必需输入缺失 | 终止执行，要求补充 |
| CSV 无表头 | 跳过该文件，继续执行 |
| price_context 无法提取 | 标注"数据缺失"，价格评分跳过 |
| writing_policy 不完整 | 降级处理，标注风险项 |

---

## 附录A: run_config schema 与填槽字段处理

### run_config JSON schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Amazon Listing Generator Run Config",
  "type": "object",
  "required": ["target_country"],
  "properties": {
    "target_country": {
      "type": "string",
      "enum": ["US", "UK", "DE", "FR", "IT", "ES", "CA", "AU", "JP"],
      "description": "上架国家代码"
    },
    "brand_name": {
      "type": "string",
      "default": "TOSBARRFT",
      "description": "品牌名称，默认TOSBARRFT"
    },
    "core_selling_points_raw": {
      "type": "string",
      "description": "核心卖点自由文本（逗号分隔），可空，自动提取5-8个卖点"
    },
    "accessory_params_raw": {
      "type": "string", 
      "description": "配件/参数补充自由文本，必填但可显式跳过（空字符串\"\"）"
    },
    "input_files": {
      "type": "object",
      "properties": {
        "attribute_table": {"type": "string"},
        "keyword_table": {"type": "string"},
        "review_table": {"type": "string"},
        "aba_merged": {"type": "string"}
      },
      "description": "输入文件路径（可自动检测）"
    }
  }
}
```

### 填槽字段处理规则

#### 1. 核心卖点处理
- **用户提供文本**：使用增强语义提取（支持口语化汉语、中英文混合）
- **用户输入空/未提供**：自动从属性表和评论中提取5-8个卖点
- **数量约束**：最终输出5-8个卖点，不足时补充通用卖点
- **优先级**：用户输入 > 属性表special_feature > 评论Feature_Praise

#### 2. 配件/参数补充处理  
- **用户提供文本**：增强语义提取，解析配件类型、功能、限制
- **显式跳过（空字符串\"\"）**：跳过配件描述，Listing中不可新增配件场景
- **未提供输入**：从属性表included_components字段自动提取
- **必填验证**：必须提供信息或显式跳过

#### 3. 信息优先级规则
```
填槽字段（用户输入） > 本品属性表 > 评论/关键词数据
```

#### 4. 口语化模式库（示例）
```python
# 核心卖点口语化模式
SELLING_POINT_PATTERNS = {
    "双屏幕": [r'两[个]?屏幕', r'双屏[幕]?', r'前后屏'],
    "防抖": [r'防抖(效果)?(很|非常)?(好|不错|强)', r'EIS防抖'],
    "WiFi连接": [r'Wi[-\s]?Fi[连接]?', r'无线[连接]?', r'手机[连]?接'],
    "4K画质": [r'4K[视频]?', r'超高清', r'高清画质'],
    "长续航": [r'电池[续航]?(长|久)', r'续航[时间]?长', r'150分钟'],
    "轻便": [r'轻[便]?', r'小巧', r'便携', r'方便携带'],
    "防水": [r'防水', r'防泼溅', r'雨天可用', r'waterproof'],
    "易操作": [r'容易[使用]?', r'简单[操作]?', r'一键[录制]?']
}
```

#### 5. 自动提取算法实现

**核心卖点自动提取流程**：
```python
def extract_core_selling_points_auto(attr_data, review_insights):
    """从属性表和评论中自动提取5-8个核心卖点"""
    
    selling_points = []
    
    # 1. 从属性表提取（优先级最高）
    if attr_data:
        # special_feature字段（逗号分隔）
        if "special_feature" in attr_data:
            points = attr_data["special_feature"].split(",")
            selling_points.extend([p.strip() for p in points if p.strip()])
        
        # product_features字段
        if "product_features" in attr_data:
            points = attr_data["product_features"].split(",")
            selling_points.extend([p.strip() for p in points if p.strip()])
    
    # 2. 从评论中补充（优先级较低）
    if review_insights and not selling_points:
        # 收集Feature_Praise评论
        praise_comments = []
        for review in review_insights:
            if (review.get("Data_Type") == "Review_Insight" and 
                review.get("Field_Name") == "Feature_Praise"):
                praise_comments.append(review.get("Content_Text", ""))
        
        # 提取高频正面特征
        if praise_comments:
            common_features = extract_common_features_from_reviews(praise_comments)
            selling_points.extend(common_features)
    
    # 3. 去重、排序、限制数量
    selling_points = list(dict.fromkeys(selling_points))  # 保持顺序去重
    selling_points = selling_points[:8]  # 最多8个
    
    # 4. 数量约束：确保5-8个卖点
    if len(selling_points) < 5:
        generic_points = ["高清视频录制", "便携设计", "长续航电池", "易于操作", "多场景适用"]
        for generic in generic_points:
            if generic not in selling_points and len(selling_points) < 8:
                selling_points.append(generic)
    
    return selling_points
```

**配件自动提取算法**：
```python
def extract_accessories_from_attributes(attr_data):
    """从属性表included_components字段自动提取配件描述"""
    
    if not attr_data or "included_components" not in attr_data:
        return []
    
    components_text = attr_data["included_components"]
    descriptions = []
    
    # 常见配件类型映射
    ACCESSORY_TYPES = {
        "body camera": "主机",
        "back clip": "背夹", 
        "card reader": "读卡器",
        "magnetic neck strap": "磁吸挂绳",
        "waterproof case": "防水壳",
        "data cable": "数据线",
        "user manual": "用户手册"
    }
    
    # 分割逗号分隔的列表
    components = [c.strip() for c in components_text.split(",") if c.strip()]
    
    for comp in components:
        # 查找配件类型
        accessory_type = None
        for eng, chi in ACCESSORY_TYPES.items():
            if eng.lower() in comp.lower():
                accessory_type = chi
                break
        
        descriptions.append({
            "name": accessory_type or "其他配件",
            "specification": comp,
            "original": comp
        })
    
    return descriptions
```

#### 6. 预处理质量评分（0-100分）
- **核心卖点完整性** (30分)：数量、质量、来源
- **配件描述明确性** (20分)：信息完整性或显式跳过
- **产品属性完整性** (25分)：关键字段覆盖率
- **关键词数据可用性** (15分)：数据完整度
- **评论洞察可用性** (10分)：评论数据存在性

#### 6. 输出到最终报告
预处理质量评分作为Module 0输出到最终报告，包含各维度详细评分。

---

### 测试用例设计

#### 测试场景矩阵
| 场景 | 核心卖点输入 | 配件描述输入 | 属性表 | 预期结果 |
|------|-------------|-------------|--------|----------|
| TC01 | 完整输入 | 完整输入 | 完整 | 完全使用用户输入 |
| TC02 | 空字符串 | 完整输入 | 完整 | 自动提取5-8个卖点 |
| TC03 | 未提供 | 空字符串("") | 完整 | 自动提取卖点，显式跳过配件 |
| TC04 | 口语化输入 | 口语化输入 | 不完整 | 语义提取，补充缺失字段 |
| TC05 | 中英文混合 | 未提供 | 完整 | 双语提取，自动提取配件 |

#### 具体测试用例示例

**TC01-完整用户输入**
```json
{
  "run_config": {
    "target_country": "DE",
    "brand_name": "MYBRAND",
    "core_selling_points_raw": "双屏幕，EIS防抖，4K录制",
    "accessory_params_raw": "防水壳30米，磁吸挂绳"
  },
  "expected": {
    "selling_points_count": 3,
    "selling_points_source": "user_input",
    "accessory_status": "parsed",
    "quality_score_min": 80
  }
}
```

**TC02-卖点自动提取**
```json
{
  "run_config": {
    "target_country": "US",
    "core_selling_points_raw": "",
    "accessory_params_raw": "标准配件"
  },
  "expected": {
    "selling_points_count": ">=5",
    "selling_points_source": "auto_extracted",
    "accessory_status": "parsed"
  }
}
```

**TC03-配件显式跳过**
```json
{
  "run_config": {
    "target_country": "UK",
    "core_selling_points_raw": "轻便设计，长续航",
    "accessory_params_raw": ""
  },
  "expected": {
    "selling_points_count": 2,
    "accessory_status": "explicitly_skipped",
    "accessory_listing_impact": "no_new_scenes"
  }
}
```

**边界条件测试**
- 空属性表处理
- 缺失关键词文件处理  
- 非法国家代码处理
- 超长文本输入处理
- 特殊字符输入处理

---

## 6. 版本历史

| 版本 | 日期 | 说明 |
|-----|------|------|
| v1.0 | 2026-04-01 | 初始版本，从 REFLY 迁移 |
| v1.1 | 2026-04-02 | 新增Step 0: 数据预处理与填槽字段解析，支持口语化汉语语义提取、自动提取算法、预处理质量评分，包含独立Python脚本 `tools/preprocess.py` |

---

## 7. 使用方式

```
用户提供输入文件路径和填槽字段 → Claude 执行 Step 0-9 → 输出包含预处理质量评分的完整报告
```

**可选独立执行**：
Step 0（数据预处理）可作为独立脚本执行：
```bash
python tools/preprocess.py --run-config run_config.json --output preprocessed_data.json
```
详见 Step 0 中的调用方式说明。

**完整工作流**：
1. **Step 0**: 数据预处理与填槽字段解析
2. **Step 1**: 输入解析与语言映射
3. **Step 2**: 字段提取与关键词分级
4. **Step 3**: 能力熔断与合规检查
5. **Step 4**: COSMO意图图谱分析
6. **Step 5**: writing_policy生成
7. **Step 6**: 文案生成（Title/Bullets/Description/FAQ/Search Terms/A+）
8. **Step 7**: 三层风险检查
9. **Step 8**: 算法评分（A10/COSMO/Rufus）
10. **Step 9**: 输出报告（包含Module 0预处理质量）

典型对话：
```
用户: 我有 H88 产品的数据，在 /path/to/H88/
Claude: 读取所有输入文件，执行工作流，输出 Listing 报告
用户: B2 的场景词需要调整...
Claude: 根据反馈修改，重新生成
```
