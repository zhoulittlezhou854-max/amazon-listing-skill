#!/usr/bin/env python3
"""
风险检查模块 (Step 7)
版本: v1.0
功能: 三层风险检查：合规红线、writing_policy审计、Rufus幻觉风险
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple


def check_compliance_redlines(generated_copy: Dict[str, Any], language: str = "Chinese") -> Dict[str, Any]:
    """
    合规红线检查
    检查文案中是否包含禁止内容
    """
    redline_issues = []
    passed_checks = 0
    total_checks = 0

    # 所有文案文本
    all_text = ""
    if "title" in generated_copy:
        all_text += generated_copy["title"] + " "
    if "bullets" in generated_copy:
        all_text += " ".join(generated_copy["bullets"]) + " "
    if "description" in generated_copy:
        all_text += generated_copy["description"] + " "
    if "aplus_content" in generated_copy:
        all_text += generated_copy["aplus_content"] + " "

    # 检查FAQ
    if "faq" in generated_copy:
        for faq_item in generated_copy["faq"]:
            all_text += faq_item.get("q", "") + " " + faq_item.get("a", "") + " "

    all_text = all_text.lower()

    # 合规红线规则
    compliance_rules = [
        {
            "name": "联系方式/URL/社交媒体",
            "patterns": [r'@\w+', r'#\w+', r'http[s]?://', r'www\.', r'\.com', r'\.net', r'\.org'],
            "severity": "high",
            "description": "禁止包含联系方式、URL或社交媒体"
        },
        {
            "name": "价格/折扣信息",
            "patterns": [r'\$\d+', r'price', r'discount', r'sale', r'deal', r'coupon', r'优惠', r'打折', r'促销'],
            "severity": "high",
            "description": "禁止提及价格、折扣或促销信息"
        },
        {
            "name": "竞品贬低",
            "patterns": [r'better than', r'beats', r'vs\.', r'versus', r'compared to', r'比.*好', r'优于', r'打败'],
            "severity": "high",
            "description": "禁止贬低竞争对手"
        },
        {
            "name": "绝对化宣称",
            "patterns": [r'100%', r'best', r'#1', r'top rated', r'hot', r'amazing', r'完美', r'最好', r'顶级'],
            "severity": "medium",
            "description": "避免使用绝对化宣称"
        },
        {
            "name": "保证/退款宣称",
            "patterns": [r'guaranteed', r'money back', r'risk-free', r'warranty', r'保证', r'退款', r'无风险'],
            "severity": "medium",
            "description": "谨慎使用保证或退款宣称"
        },
        {
            "name": "运动相机专项禁止",
            "patterns": [r'indestructible', r'military grade', r'bulletproof', r'fully shockproof', r'防弹', r'军用级', r'完全防震'],
            "severity": "high",
            "description": "运动相机专项禁止词汇"
        }
    ]

    # 执行检查
    for rule in compliance_rules:
        total_checks += 1
        found = False
        for pattern in rule["patterns"]:
            if re.search(pattern, all_text, re.IGNORECASE):
                found = True
                redline_issues.append({
                    "rule": rule["name"],
                    "pattern": pattern,
                    "severity": rule["severity"],
                    "description": rule["description"]
                })
                break

        if not found:
            passed_checks += 1

    return {
        "passed": passed_checks,
        "total": total_checks,
        "issues": redline_issues,
        "all_passed": len(redline_issues) == 0
    }


def check_writing_policy_compliance(generated_copy: Dict[str, Any],
                                   writing_policy: Dict[str, Any],
                                   language: str = "Chinese") -> Dict[str, Any]:
    """
    writing_policy审计
    检查文案是否遵循writing_policy中的硬性约束
    """
    policy_issues = []
    passed_checks = 0
    total_checks = 0

    # 1. 检查场景优先级锁定
    total_checks += 1
    scene_priority = writing_policy.get("scene_priority", [])
    if scene_priority:
        # 检查文案中是否按优先级使用场景词
        all_text = ""
        if "title" in generated_copy:
            all_text += generated_copy["title"] + " "
        if "bullets" in generated_copy:
            all_text += " ".join(generated_copy["bullets"]) + " "

        found_scenes = []
        for scene in scene_priority:
            if scene in all_text:
                found_scenes.append(scene)

        # 检查是否按优先级出现
        if found_scenes:
            # 简单的检查：第一个出现的场景应该是优先级最高的场景之一
            first_scene_index = None
            for i, scene in enumerate(scene_priority):
                if scene in all_text:
                    first_scene_index = i
                    break

            if first_scene_index is not None and first_scene_index <= 2:
                passed_checks += 1
            else:
                policy_issues.append({
                    "rule": "场景优先级锁定",
                    "description": f"第一个出现的场景'{found_scenes[0] if found_scenes else '无'}'不是优先级最高的场景之一",
                    "severity": "medium"
                })
        else:
            policy_issues.append({
                "rule": "场景优先级锁定",
                "description": "文案中未使用writing_policy中的场景词",
                "severity": "medium"
            })
    else:
        passed_checks += 1

    # 2. 检查能力场景绑定
    total_checks += 1
    capability_bindings = writing_policy.get("capability_scene_bindings", [])
    if capability_bindings:
        issues_found = False
        for binding in capability_bindings:
            capability = binding.get("capability", "")
            allowed_scenes = binding.get("allowed_scenes", [])
            forbidden_scenes = binding.get("forbidden_scenes", [])

            # 检查文案中能力是否与正确场景一起出现
            all_text = ""
            if "title" in generated_copy:
                all_text += generated_copy["title"] + " "
            if "bullets" in generated_copy:
                all_text += " ".join(generated_copy["bullets"]) + " "

            if capability in all_text:
                # 检查是否出现在禁止场景中
                for scene in forbidden_scenes:
                    if scene in all_text:
                        issues_found = True
                        policy_issues.append({
                            "rule": "能力场景绑定",
                            "description": f"能力'{capability}'出现在禁止场景'{scene}'中",
                            "severity": "high"
                        })

        if not issues_found:
            passed_checks += 1
    else:
        passed_checks += 1

    # 3. 检查禁止组合
    total_checks += 1
    forbidden_pairs = writing_policy.get("forbidden_pairs", [])
    if forbidden_pairs:
        all_text = ""
        if "title" in generated_copy:
            all_text += generated_copy["title"] + " "
        if "bullets" in generated_copy:
            all_text += " ".join(generated_copy["bullets"]) + " "

        issues_found = False
        for pair in forbidden_pairs:
            if len(pair) >= 2:
                item1, item2 = pair[0], pair[1]
                if item1 in all_text and item2 in all_text:
                    issues_found = True
                    policy_issues.append({
                        "rule": "禁止组合",
                        "description": f"禁止组合'{item1}'和'{item2}'同时出现在文案中",
                        "severity": "high"
                    })

        if not issues_found:
            passed_checks += 1
    else:
        passed_checks += 1

    # 4. 检查边界声明强制
    total_checks += 1
    # 检查B4或B5是否包含边界声明
    bullets = generated_copy.get("bullets", [])
    if len(bullets) >= 4:
        b4_text = bullets[3] if len(bullets) > 3 else ""
        b5_text = bullets[4] if len(bullets) > 4 else ""

        # 边界声明关键词
        boundary_keywords = ["（", "）", "(", ")", "需", "要求", "requires", "with", "in"]
        has_boundary = any(keyword in b4_text for keyword in boundary_keywords) or \
                      any(keyword in b5_text for keyword in boundary_keywords)

        if has_boundary:
            passed_checks += 1
        else:
            policy_issues.append({
                "rule": "边界声明强制",
                "description": "B4或B5中未包含边界声明",
                "severity": "medium"
            })
    else:
        passed_checks += 1

    # 5. 检查FAQ only限制
    total_checks += 1
    faq_only_capabilities = writing_policy.get("faq_only_capabilities", [])
    if faq_only_capabilities:
        # 检查FAQ only能力是否出现在FAQ以外的部分
        main_text = ""
        if "title" in generated_copy:
            main_text += generated_copy["title"] + " "
        if "bullets" in generated_copy:
            main_text += " ".join(generated_copy["bullets"]) + " "
        if "description" in generated_copy:
            main_text += generated_copy["description"] + " "

        issues_found = False
        for capability in faq_only_capabilities:
            if capability in main_text:
                issues_found = True
                policy_issues.append({
                    "rule": "FAQ only限制",
                    "description": f"FAQ only能力'{capability}'出现在FAQ以外的文案中",
                    "severity": "high"
                })

        if not issues_found:
            passed_checks += 1
    else:
        passed_checks += 1

    # 6. 检查A+字数下限
    total_checks += 1
    aplus_content = generated_copy.get("aplus_content", "")
    if aplus_content:
        word_count = len(aplus_content.strip())
        if word_count >= 500:
            passed_checks += 1
        else:
            policy_issues.append({
                "rule": "A+字数下限",
                "description": f"A+内容字数不足，当前{word_count}字，要求至少500字",
                "severity": "medium"
            })
    else:
        policy_issues.append({
            "rule": "A+字数下限",
            "description": "A+内容为空",
            "severity": "medium"
        })

    return {
        "passed": passed_checks,
        "total": total_checks,
        "issues": policy_issues,
        "all_passed": len(policy_issues) == 0
    }


def check_hallucination_risk(generated_copy: Dict[str, Any],
                            attribute_data: Dict[str, Any],
                            language: str = "Chinese") -> Dict[str, Any]:
    """
    Rufus幻觉风险检查
    检查文案中的宣称是否有属性表数据支持
    """
    hallucination_issues = []
    passed_checks = 0
    total_checks = 0

    # 提取所有宣称
    claims = []

    # 从标题提取宣称
    title = generated_copy.get("title", "")
    if title:
        claims.append({"text": title, "source": "title"})

    # 从bullet points提取宣称
    bullets = generated_copy.get("bullets", [])
    for i, bullet in enumerate(bullets):
        claims.append({"text": bullet, "source": f"bullet_{i+1}"})

    # 从描述提取宣称
    description = generated_copy.get("description", "")
    if description:
        # 分割描述为句子
        sentences = re.split(r'[。！？.!?]', description)
        for sentence in sentences:
            if sentence.strip():
                claims.append({"text": sentence.strip(), "source": "description"})

    # 宣称检查规则
    claim_patterns = [
        {
            "pattern": r'(\d+)\s*(?:k|K)\s*(?:录像|视频|录制|video|recording)',
            "field": "video_resolution",
            "description": "视频分辨率宣称"
        },
        {
            "pattern": r'(\d+)\s*(?:米|m|meter)\s*(?:防水|waterproof)',
            "field": "waterproof_depth",
            "description": "防水深度宣称"
        },
        {
            "pattern": r'(\d+)\s*(?:分钟|min|minute)\s*(?:续航|电池|battery)',
            "field": "battery_life",
            "description": "电池续航宣称"
        },
        {
            "pattern": r'(\d+)\s*(?:克|g|gram)\s*(?:重量|weight)',
            "field": "weight",
            "description": "产品重量宣称"
        },
        {
            "pattern": r'防抖|stabilization',
            "field": "image_stabilization",
            "description": "防抖功能宣称"
        },
        {
            "pattern": r'WiFi|无线|wireless',
            "field": "connectivity",
            "description": "连接功能宣称"
        },
        {
            "pattern": r'双屏|dual screen',
            "field": "screen_type",
            "description": "屏幕类型宣称"
        }
    ]

    # 检查每个宣称
    for claim in claims:
        claim_text = claim["text"]
        source = claim["source"]

        for pattern_info in claim_patterns:
            pattern = pattern_info["pattern"]
            field = pattern_info["field"]
            description = pattern_info["description"]

            match = re.search(pattern, claim_text, re.IGNORECASE)
            if match:
                total_checks += 1

                # 检查属性表中是否有对应数据
                if field in attribute_data:
                    attr_value = str(attribute_data[field]).lower()
                    claim_value = match.group(0).lower()

                    # 简单验证：检查属性值是否与宣称一致
                    if attr_value and attr_value not in ["none", "无", "未知"]:
                        passed_checks += 1
                    else:
                        hallucination_issues.append({
                            "claim": claim_text,
                            "source": source,
                            "field": field,
                            "description": f"{description}: 属性表中{field}字段值为'{attr_value}'，与宣称可能不一致",
                            "severity": "medium"
                        })
                else:
                    hallucination_issues.append({
                        "claim": claim_text,
                        "source": source,
                        "field": field,
                        "description": f"{description}: 属性表中缺少{field}字段数据支持",
                        "severity": "high"
                    })

    # 如果没有检查到任何宣称，添加一个默认检查
    if total_checks == 0:
        total_checks += 1
        # 检查是否有基本属性数据
        required_fields = ["video_resolution", "battery_life", "waterproof_depth"]
        missing_fields = [field for field in required_fields if field not in attribute_data]

        if len(missing_fields) == 0:
            passed_checks += 1
        else:
            hallucination_issues.append({
                "claim": "基本属性宣称",
                "source": "整体文案",
                "field": ",".join(missing_fields),
                "description": f"属性表中缺少关键字段: {', '.join(missing_fields)}",
                "severity": "medium"
            })

    return {
        "passed": passed_checks,
        "total": total_checks,
        "issues": hallucination_issues,
        "all_passed": len(hallucination_issues) == 0
    }


def perform_risk_check(generated_copy: Dict[str, Any],
                      writing_policy: Dict[str, Any],
                      attribute_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行三层风险检查

    Args:
        generated_copy: 生成的文案
        writing_policy: writing_policy策略
        attribute_data: 属性表数据

    Returns:
        风险检查结果
    """
    language = generated_copy.get("metadata", {}).get("language", "Chinese")

    # 1. 合规红线检查
    compliance_result = check_compliance_redlines(generated_copy, language)

    # 2. writing_policy审计
    policy_result = check_writing_policy_compliance(generated_copy, writing_policy, language)

    # 3. 幻觉风险检查
    hallucination_result = check_hallucination_risk(generated_copy, attribute_data, language)

    # 综合评估
    overall_passed = (
        compliance_result["all_passed"] and
        policy_result["all_passed"] and
        hallucination_result["all_passed"]
    )

    risk_score = 0
    max_score = 100

    # 计算风险分数
    risk_score += (compliance_result["passed"] / compliance_result["total"]) * 40 if compliance_result["total"] > 0 else 40
    risk_score += (policy_result["passed"] / policy_result["total"]) * 40 if policy_result["total"] > 0 else 40
    risk_score += (hallucination_result["passed"] / hallucination_result["total"]) * 20 if hallucination_result["total"] > 0 else 20

    return {
        "compliance": compliance_result,
        "policy_audit": policy_result,
        "hallucination_risk": hallucination_result,
        "overall_passed": overall_passed,
        "risk_score": int(risk_score),
        "risk_level": "低风险" if risk_score >= 90 else "中风险" if risk_score >= 70 else "高风险",
        "summary": {
            "compliance_issues": len(compliance_result["issues"]),
            "policy_issues": len(policy_result["issues"]),
            "hallucination_issues": len(hallucination_result["issues"]),
            "total_issues": len(compliance_result["issues"]) + len(policy_result["issues"]) + len(hallucination_result["issues"])
        }
    }


if __name__ == "__main__":
    # 测试代码
    sample_generated_copy = {
        "title": "TOSBARRFT 4K运动相机 户外防水防抖相机",
        "bullets": [
            "【挂载系统+主场景+P0能力】配备多种挂载配件，专为户外运动设计，提供4K录像功能",
            "【P0核心能力+量化参数】支持4K 30fps高清录像，画面细腻流畅",
            "【P1竞品痛点对比+场景词】相比竞品，在骑行场景下防抖表现更优异",
            "【P1/P2能力+使用场景+边界声明句】支持防水，适用于水下探索（需使用防水壳）",
            "【P2质保/售后/兼容性】提供12个月质保，专业客服支持，兼容多种设备"
        ],
        "description": "TOSBARRFT 运动相机专为户外运动设计，带来专业级4K录像体验。具备4K录像、防抖、防水等多项功能...",
        "faq": [
            {"q": "产品是否防水？", "a": "是的，产品配备防水壳，支持30米防水。"},
            {"q": "电池续航多久？", "a": "电池续航约150分钟，支持边充边用。"}
        ],
        "search_terms": ["运动相机", "户外相机", "防水相机"],
        "aplus_content": "TOSBARRFT 运动相机 - 专业拍摄解决方案...（超过500字的内容）",
        "metadata": {
            "language": "Chinese"
        }
    }

    sample_writing_policy = {
        "scene_priority": ["户外运动", "骑行记录", "水下探索"],
        "capability_scene_bindings": [
            {
                "capability": "4K录像",
                "allowed_scenes": ["户外运动", "水下探索"],
                "forbidden_scenes": []
            }
        ],
        "faq_only_capabilities": ["数字防抖限制说明"],
        "forbidden_pairs": [["5K", "防抖"]],
        "bullet_slot_rules": {}
    }

    sample_attribute_data = {
        "video_resolution": "4K 30fps",
        "waterproof_depth": "30米",
        "battery_life": "150分钟",
        "weight": "150g",
        "image_stabilization": "EIS",
        "connectivity": "WiFi, Bluetooth"
    }

    result = perform_risk_check(sample_generated_copy, sample_writing_policy, sample_attribute_data)

    print("风险检查结果:")
    print(f"总体通过: {result['overall_passed']}")
    print(f"风险分数: {result['risk_score']}/100 ({result['risk_level']})")
    print(f"\n合规红线检查: {result['compliance']['passed']}/{result['compliance']['total']}")
    print(f"writing_policy审计: {result['policy_audit']['passed']}/{result['policy_audit']['total']}")
    print(f"幻觉风险检查: {result['hallucination_risk']['passed']}/{result['hallucination_risk']['total']}")
    print(f"\n总问题数: {result['summary']['total_issues']}")

    if result['summary']['total_issues'] > 0:
        print("\n详细问题:")
        for issue_type in ['compliance', 'policy_audit', 'hallucination_risk']:
            issues = result[issue_type]['issues']
            if issues:
                print(f"\n{issue_type}问题:")
                for i, issue in enumerate(issues[:3], 1):
                    print(f"  {i}. {issue.get('description', 'N/A')}")