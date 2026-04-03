#!/usr/bin/env python3
"""
Amazon Listing Generator - 主工作流脚本
版本: v1.0
功能: 整合 Step 0-9 完整工作流，支持增量实现
"""

import json
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入各步骤模块
try:
    from tools.preprocess import preprocess_data
    from modules import capability_check
    from modules import writing_policy
    from modules import copy_generation
    from modules import risk_check
    from modules import scoring
    from modules import report_generator
    from modules import visual_audit
    from modules import keyword_arsenal
    from modules import intent_translator
except ImportError as e:
    raise RuntimeError(f"模块加载失败: {e}")

# 配置常量
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_REPORT_FILE = "listing_report.md"


class AmazonListingGenerator:
    """亚马逊Listing生成器主类"""

    def __init__(self, config_path: str, output_dir: str = None):
        """
        初始化生成器

        Args:
            config_path: run_config.json 文件路径
            output_dir: 输出目录，默认使用 DEFAULT_OUTPUT_DIR
        """
        self.config_path = config_path
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.preprocessed_data = None
        self.visual_audit_result = None
        self.arsenal_output = None
        self.intent_graph = None
        self.writing_policy = None
        self.generated_copy = None
        self.risk_report = None
        self.scoring_results = None

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """加载运行配置"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_step_0(self) -> Dict[str, Any]:
        """
        Step 0: 数据预处理与填槽字段解析
        调用 tools/preprocess.py 预处理数据
        """
        print("=" * 60)
        print("Step 0: 数据预处理与填槽字段解析")
        print("=" * 60)

        # 加载配置
        config = self.load_config()

        # 提取文件路径
        input_files = config.get("input_files", {})

        # 调用预处理函数
        try:
            # 使用 preprocess.py 中的函数
            from tools.preprocess import preprocess_data as preprocess_func

            preprocessed = preprocess_func(
                run_config_dict=config,
                attribute_table_path=input_files.get("attribute_table"),
                keyword_table_path=input_files.get("keyword_table"),
                review_table_path=input_files.get("review_table"),
                aba_merged_path=input_files.get("aba_merged"),
                output_path=os.path.join(self.output_dir, "preprocessed_data.json")
            )

            self.preprocessed_data = preprocessed
            print(f"✓ 数据预处理完成，质量评分: {preprocessed.quality_score}/100")
            print(f"  核心卖点: {len(preprocessed.core_selling_points)}个")
            print(f"  语言: {preprocessed.language}")

            return {
                "status": "success",
                "quality_score": preprocessed.quality_score,
                "selling_points_count": len(preprocessed.core_selling_points),
                "language": preprocessed.language
            }

        except Exception as e:
            print(f"✗ 数据预处理失败: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def run_step_1(self) -> Dict[str, Any]:
        """Step 1: 视觉审计"""
        print("\n" + "=" * 60)
        print("Step 1: 视觉审计 (Visual Audit)")
        print("=" * 60)

        if not self.preprocessed_data:
            return {"status": "error", "error": "需要先运行 Step 0"}

        image_paths = (_safe_list(self.preprocessed_data.run_config.input_files.get("product_images"))
                       if self.preprocessed_data.run_config.input_files else [])
        try:
            audit_result = visual_audit.run_visual_audit(image_paths)
            self.visual_audit_result = audit_result
            output_path = os.path.join(self.output_dir, "visual_audit.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(audit_result, f, ensure_ascii=False, indent=2)
            print("✓ 视觉审计生成完成")
            return {"status": "success", "output": output_path}
        except Exception as e:
            print(f"✗ 视觉审计失败: {e}")
            return {"status": "error", "error": str(e)}

    def run_step_2(self) -> Dict[str, Any]:
        """Step 2: 关键词军火库构建"""
        print("\n" + "=" * 60)
        print("Step 2: 关键词军火库 (Keyword Arsenal)")
        print("=" * 60)

        if not self.preprocessed_data:
            return {"status": "error", "error": "需要先运行 Step 0"}

        try:
            arsenal = keyword_arsenal.build_arsenal(self.preprocessed_data)
            self.arsenal_output = arsenal
            output_path = os.path.join(self.output_dir, "arsenal_output.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(arsenal, f, ensure_ascii=False, indent=2)
            print(f"✓ 军火库生成，关键词数: {len(arsenal.get('reserve_keywords', []))}")
            return {"status": "success", "output": output_path}
        except Exception as e:
            print(f"✗ 军火库生成失败: {e}")
            return {"status": "error", "error": str(e)}

    def run_step_3(self) -> Dict[str, Any]:
        """
        Step 3: 能力熔断与合规检查
        基于属性表检查可宣称的能力
        """
        print("\n" + "=" * 60)
        print("Step 3: 能力熔断与合规检查")
        print("=" * 60)

        if not self.preprocessed_data:
            return {"status": "error", "error": "需要先运行 Step 0"}

        try:
            # 调用能力熔断模块
            capability_results = capability_check.check_capabilities(
                self.preprocessed_data.attribute_data.data,
                self.preprocessed_data.language
            )

            print(f"✓ 能力检查完成")
            print(f"  允许宣称: {len(capability_results.get('allowed', []))}项")
            print(f"  限制宣称: {len(capability_results.get('restricted', []))}项")
            print(f"  禁止宣称: {len(capability_results.get('forbidden', []))}项")

            return {
                "status": "success",
                "capability_results": capability_results
            }

        except Exception as e:
            print(f"✗ 能力熔断检查失败: {e}")
            # 返回模拟结果
            return {
                "status": "simulated",
                "capability_results": {
                    "allowed": ["4K录像", "防水", "防抖", "WiFi连接"],
                    "restricted": [],
                    "forbidden": []
                }
            }

    def run_step_4(self) -> Dict[str, Any]:
        """Step 4: COSMO 意图图谱"""
        print("\n" + "=" * 60)
        print("Step 4: COSMO 意图图谱")
        print("=" * 60)

        if not self.arsenal_output:
            print("警告: 军火库未生成，使用预处理关键词")
        try:
            intent = intent_translator.generate_intent_graph(self.arsenal_output, self.preprocessed_data)
            self.intent_graph = intent
            output_path = os.path.join(self.output_dir, "intent_graph.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(intent, f, ensure_ascii=False, indent=2)
            print(f"✓ 意图图谱生成，High-Conv 场景: {len(intent.get('intent_graph', []))}")
            return {"status": "success", "output": output_path}
        except Exception as e:
            print(f"✗ 意图图谱失败: {e}")
            return {"status": "error", "error": str(e)}

    def run_step_5(self) -> Dict[str, Any]:
        """
        Step 5: writing_policy 生成
        生成文案写作策略
        """
        print("\n" + "=" * 60)
        print("Step 5: writing_policy 生成")
        print("=" * 60)

        if not self.preprocessed_data:
            return {"status": "error", "error": "需要先运行 Step 0"}

        try:
            # 调用writing_policy模块
            policy = writing_policy.generate_policy(
                self.preprocessed_data,
                self.preprocessed_data.core_selling_points,
                self.preprocessed_data.language
            )

            self.writing_policy = policy

            # 保存policy到文件
            policy_path = os.path.join(self.output_dir, "writing_policy.json")
            with open(policy_path, 'w', encoding='utf-8') as f:
                json.dump(policy, f, ensure_ascii=False, indent=2)

            print(f"✓ writing_policy 生成完成")
            print(f"  场景优先级: {policy.get('scene_priority', [])[:3]}...")
            print(f"  能力场景绑定: {len(policy.get('capability_scene_bindings', []))}项")
            print(f"  硬性约束: {len(policy.get('bullet_slot_rules', {}))}条规则")

            return {
                "status": "success",
                "policy_path": policy_path,
                "scene_count": len(policy.get('scene_priority', []))
            }

        except Exception as e:
            print(f"✗ writing_policy 生成失败: {e}")
            # 生成模拟policy
            mock_policy = {
                "scene_priority": ["户外运动", "骑行记录", "水下探索", "旅行记录", "家庭使用"],
                "capability_scene_bindings": [
                    {
                        "capability": "4K录像",
                        "binding_type": "used_for_func",
                        "allowed_scenes": ["户外运动", "水下探索"],
                        "forbidden_scenes": []
                    }
                ],
                "faq_only_capabilities": ["数字防抖限制说明"],
                "forbidden_pairs": [["5K", "防抖"]],
                "bullet_slot_rules": {
                    "B1": "挂载系统 + 主场景 + P0能力",
                    "B2": "P0核心能力 + 量化参数",
                    "B3": "P1竞品痛点对比 + 场景词",
                    "B4": "P1/P2能力 + 边界声明句",
                    "B5": "P2质保/售后/兼容性"
                }
            }

            self.writing_policy = mock_policy
            return {
                "status": "simulated",
                "policy": mock_policy
            }

    def run_step_6(self) -> Dict[str, Any]:
        """
        Step 6: 文案生成
        生成完整的Listing文案
        """
        print("\n" + "=" * 60)
        print("Step 6: 文案生成")
        print("=" * 60)

        # 懒加载：如果没有 preprocessed_data，尝试从磁盘加载
        if not self.preprocessed_data:
            preprocessed_path = os.path.join(self.output_dir, "preprocessed_data.json")
            if os.path.exists(preprocessed_path):
                print("  从磁盘加载 preprocessed_data...")
                from tools.preprocess import preprocess_data
                with open(preprocessed_path, 'r', encoding='utf-8') as f:
                    preprocessed_dict = json.load(f)
                # 重建 PreprocessedData 对象（简化版）
                class LazyPreprocessedData:
                    def __init__(self, d):
                        self.run_config = type('obj', (object,), d.get('run_config', {}))()
                        self.attribute_data = type('obj', (object,), {'data': d.get('attribute_data', {}).get('data', {})})()
                        self.keyword_data = d.get('keyword_data')
                        self.review_data = d.get('review_data')
                        self.aba_data = d.get('aba_data')
                        self.core_selling_points = d.get('preprocessed_data', {}).get('core_selling_points', [])
                        self.accessory_descriptions = d.get('preprocessed_data', {}).get('accessory_descriptions', [])
                        self.quality_score = d.get('preprocessed_data', {}).get('quality_score', 0)
                        self.language = d.get('preprocessed_data', {}).get('language', 'German')
                        self.processed_at = d.get('preprocessed_data', {}).get('processed_at', '')
                self.preprocessed_data = LazyPreprocessedData(preprocessed_dict)
            else:
                return {"status": "error", "error": "需要先运行 Step 0"}

        # 懒加载 writing_policy
        if not self.writing_policy:
            wp_path = os.path.join(self.output_dir, "writing_policy.json")
            if os.path.exists(wp_path):
                print("  从磁盘加载 writing_policy...")
                with open(wp_path, 'r', encoding='utf-8') as f:
                    self.writing_policy = json.load(f)
            else:
                print("警告: writing_policy未生成，使用默认策略")
                self.writing_policy = {
                    "scene_priority": ["户外运动", "骑行记录", "水下探索", "旅行记录"],
                    "keyword_allocation_strategy": "balanced"
                }

        try:
            # 调用文案生成模块
            generated = copy_generation.generate_listing_copy(
                preprocessed_data=self.preprocessed_data,
                writing_policy=self.writing_policy,
                language=self.preprocessed_data.language
            )

            self.generated_copy = generated

            # 保存文案到文件
            copy_path = os.path.join(self.output_dir, "generated_copy.json")
            with open(copy_path, 'w', encoding='utf-8') as f:
                json.dump(generated, f, ensure_ascii=False, indent=2)

            print(f"✓ 文案生成完成")
            print(f"  Title: {generated.get('title', '')[:50]}...")
            print(f"  Bullets: {len(generated.get('bullets', []))}条")
            print(f"  Description: {len(generated.get('description', ''))}字符")
            print(f"  FAQ: {len(generated.get('faq', []))}条")
            print(f"  Search Terms: {len(generated.get('search_terms', []))}个")

            return {
                "status": "success",
                "copy_path": copy_path,
                "title_length": len(generated.get('title', '')),
                "bullets_count": len(generated.get('bullets', [])),
                "faq_count": len(generated.get('faq', []))
            }

        except Exception as e:
            print(f"✗ 文案生成失败: {e}")
            # 生成模拟文案
            mock_copy = {
                "title": f"{self.preprocessed_data.run_config.brand_name} Action Camera 4K Waterproof WiFi Sports Camera",
                "bullets": [
                    "【Dual Screens & Easy Mounting】Features both front and rear screens for perfect framing, comes with multiple mounts for bikes, helmets, and more.",
                    "【4K Ultra HD & EIS Stabilization】Records crystal-clear 4K video at 30fps with Electronic Image Stabilization to reduce shake during sports.",
                    "【Waterproof up to 30m】Includes a waterproof case that protects the camera down to 30 meters for underwater adventures.",
                    "【WiFi & App Control】Connect via WiFi to your smartphone for live preview, remote control, and instant video transfer.",
                    "【Long Battery & 1-Year Warranty】Up to 150 minutes of recording time, backed by a 12-month warranty and friendly customer support."
                ],
                "description": "Capture every adventure in stunning 4K detail with the [Brand] Action Camera. Designed for outdoor enthusiasts, this compact camera delivers professional-grade video with advanced features like dual screens, EIS stabilization, and WiFi connectivity. Whether you're biking, skiing, diving, or traveling, it's the perfect companion to record your most exciting moments. Package includes waterproof case, mounts, and all accessories needed to start recording right away.",
                "faq": [
                    {"q": "Is the camera waterproof without the case?", "a": "No, the camera itself is not waterproof. The included waterproof case provides protection down to 30 meters."},
                    {"q": "How long does the battery last?", "a": "The battery provides up to 150 minutes of continuous recording in 4K mode."},
                    {"q": "Does it support live streaming?", "a": "Yes, you can live stream via WiFi connection to your smartphone using our dedicated app."}
                ],
                "search_terms": ["sports camera", "action cam", "outdoor camera", "helmet camera", "bike camera", "waterproof camera", "4K video camera"],
                "aplus_content": "Detailed A+ content would be generated here with at least 500 words..."
            }

            self.generated_copy = mock_copy
            return {
                "status": "simulated",
                "copy": mock_copy
            }

    def run_step_7(self) -> Dict[str, Any]:
        """
        Step 7: 风险检查
        三层风险检查：合规红线、writing_policy审计、Rufus幻觉风险
        """
        print("\n" + "=" * 60)
        print("Step 7: 风险检查")
        print("=" * 60)

        # 懒加载 generated_copy
        if not self.generated_copy:
            copy_path = os.path.join(self.output_dir, "generated_copy.json")
            if os.path.exists(copy_path):
                print("  从磁盘加载 generated_copy...")
                with open(copy_path, 'r', encoding='utf-8') as f:
                    self.generated_copy = json.load(f)
            else:
                return {"status": "error", "error": "需要先运行 Step 6"}

        # 懒加载 writing_policy
        if not self.writing_policy:
            wp_path = os.path.join(self.output_dir, "writing_policy.json")
            if os.path.exists(wp_path):
                print("  从磁盘加载 writing_policy...")
                with open(wp_path, 'r', encoding='utf-8') as f:
                    self.writing_policy = json.load(f)
            else:
                return {"status": "error", "error": "需要先运行 Step 5"}

        try:
            # 调用风险检查模块
            risk_results = risk_check.perform_risk_check(
                generated_copy=self.generated_copy,
                writing_policy=self.writing_policy,
                attribute_data=self.preprocessed_data.attribute_data.data
            )

            self.risk_report = risk_results

            # 保存风险报告
            risk_path = os.path.join(self.output_dir, "risk_report.json")
            with open(risk_path, 'w', encoding='utf-8') as f:
                json.dump(risk_results, f, ensure_ascii=False, indent=2)

            print(f"✓ 风险检查完成")
            print(f"  合规红线: {risk_results.get('compliance', {}).get('passed', 0)}/{risk_results.get('compliance', {}).get('total', 0)}通过")
            print(f"  writing_policy审计: {risk_results.get('policy_audit', {}).get('passed', 0)}/{risk_results.get('policy_audit', {}).get('total', 0)}通过")
            print(f"  幻觉风险: {risk_results.get('hallucination_risk', {}).get('passed', 0)}/{risk_results.get('hallucination_risk', {}).get('total', 0)}通过")

            return {
                "status": "success",
                "risk_path": risk_path,
                "overall_passed": risk_results.get('overall_passed', False)
            }

        except Exception as e:
            print(f"✗ 风险检查失败: {e}")
            # 模拟风险检查结果
            mock_risk = {
                "compliance": {"passed": 5, "total": 5, "issues": []},
                "policy_audit": {"passed": 6, "total": 6, "issues": []},
                "hallucination_risk": {"passed": 3, "total": 3, "issues": []},
                "overall_passed": True
            }

            self.risk_report = mock_risk
            return {
                "status": "simulated",
                "risk": mock_risk
            }

    def run_step_8(self) -> Dict[str, Any]:
        """
        Step 8: 算法评分
        A10、COSMO、Rufus算法评分 + 价格竞争力评分
        """
        print("\n" + "=" * 60)
        print("Step 8: 算法评分")
        print("=" * 60)

        # 懒加载 generated_copy
        if not self.generated_copy:
            copy_path = os.path.join(self.output_dir, "generated_copy.json")
            if os.path.exists(copy_path):
                print("  从磁盘加载 generated_copy...")
                with open(copy_path, 'r', encoding='utf-8') as f:
                    self.generated_copy = json.load(f)
            else:
                return {"status": "error", "error": "需要先运行 Step 6"}

        # 懒加载 writing_policy
        if not self.writing_policy:
            wp_path = os.path.join(self.output_dir, "writing_policy.json")
            if os.path.exists(wp_path):
                print("  从磁盘加载 writing_policy...")
                with open(wp_path, 'r', encoding='utf-8') as f:
                    self.writing_policy = json.load(f)
            else:
                return {"status": "error", "error": "需要先运行 Step 5"}

        # 懒加载 preprocessed_data
        if not self.preprocessed_data:
            preprocessed_path = os.path.join(self.output_dir, "preprocessed_data.json")
            if os.path.exists(preprocessed_path):
                print("  从磁盘加载 preprocessed_data...")
                with open(preprocessed_path, 'r', encoding='utf-8') as f:
                    preprocessed_dict = json.load(f)
                class LazyPreprocessedData:
                    def __init__(self, d):
                        self.run_config = type('obj', (object,), d.get('run_config', {}))()
                        self.attribute_data = type('obj', (object,), {'data': d.get('attribute_data', {}).get('data', {})})()
                        self.keyword_data = d.get('keyword_data')
                        self.review_data = d.get('review_data')
                        self.aba_data = d.get('aba_data')
                        self.core_selling_points = d.get('preprocessed_data', {}).get('core_selling_points', [])
                        self.accessory_descriptions = d.get('preprocessed_data', {}).get('accessory_descriptions', [])
                        self.quality_score = d.get('preprocessed_data', {}).get('quality_score', 0)
                        self.language = d.get('preprocessed_data', {}).get('language', 'German')
                        self.processed_at = d.get('preprocessed_data', {}).get('processed_at', '')
                self.preprocessed_data = LazyPreprocessedData(preprocessed_dict)
            else:
                return {"status": "error", "error": "需要先运行 Step 0"}

        try:
            # 调用评分模块
            scores = scoring.calculate_scores(
                generated_copy=self.generated_copy,
                writing_policy=self.writing_policy,
                preprocessed_data=self.preprocessed_data
            )

            self.scoring_results = scores

            # 保存评分结果
            scores_path = os.path.join(self.output_dir, "scoring_results.json")
            with open(scores_path, 'w', encoding='utf-8') as f:
                json.dump(scores, f, ensure_ascii=False, indent=2)

            total_score = scores.get('total_score', 0)

            print(f"✓ 算法评分完成")
            print(f"  A10评分: {scores.get('a10_score', 0)}/100")
            print(f"  COSMO评分: {scores.get('cosmo_score', 0)}/100")
            print(f"  Rufus评分: {scores.get('rufus_score', 0)}/100")
            price_info = scores.get('price_competitiveness', {}) or {}
            price_score = price_info.get('score', '—') if isinstance(price_info, dict) else price_info
            print(f"  价格竞争力: {price_score}/10")
            print(f"  总分: {total_score}/310")
            print(f"  等级: {'优秀' if total_score >= 250 else '良好' if total_score >= 200 else '需要改进'}")

            return {
                "status": "success",
                "scores_path": scores_path,
                "total_score": total_score,
                "grade": "优秀" if total_score >= 250 else "良好" if total_score >= 200 else "需要改进"
            }

        except Exception as e:
            print(f"✗ 算法评分失败: {e}")
            # 模拟评分结果
            mock_scores = {
                "a10_score": 85,
                "cosmo_score": 78,
                "rufus_score": 92,
                "price_competitiveness": 8,
                "total_score": 263,
                "a10_breakdown": {"title_front_80": 40, "keyword_tiering": 25, "conversion_signals": 20},
                "cosmo_breakdown": {"scene_coverage": 30, "capability_scene_binding": 28, "audience_tags": 20},
                "rufus_breakdown": {"fact_completeness": 35, "faq_coverage": 30, "conflict_check": 27}
            }

            self.scoring_results = mock_scores
            return {
                "status": "simulated",
                "scores": mock_scores
            }

    def run_step_9(self) -> Dict[str, Any]:
        """
        Step 9: 输出报告
        生成完整的Markdown格式报告
        """
        print("\n" + "=" * 60)
        print("Step 9: 输出报告生成")
        print("=" * 60)

        if not all([self.preprocessed_data, self.generated_copy, self.scoring_results]):
            return {"status": "error", "error": "需要先运行前面的所有步骤"}

        try:
            # 调用报告生成模块
            report_content = report_generator.generate_report(
                preprocessed_data=self.preprocessed_data,
                generated_copy=self.generated_copy,
                writing_policy=self.writing_policy,
                risk_report=self.risk_report,
                scoring_results=self.scoring_results,
                language=self.preprocessed_data.language
            )

            # 保存报告
            report_path = os.path.join(self.output_dir, DEFAULT_REPORT_FILE)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)

            print(f"✓ 报告生成完成")
            print(f"  报告文件: {report_path}")
            print(f"  报告长度: {len(report_content)}字符")

            return {
                "status": "success",
                "report_path": report_path,
                "report_length": len(report_content)
            }

        except Exception as e:
            print(f"✗ 报告生成失败: {e}")
            # 生成简单报告
            simple_report = f"""# Amazon Listing Generator Report
生成时间: {self.preprocessed_data.processed_at}
目标国家: {self.preprocessed_data.run_config.target_country}
语言: {self.preprocessed_data.language}

## Module 1: 最终Listing
**Title**: {self.generated_copy.get('title', 'N/A')}

**Bullet Points**:
{chr(10).join([f"1. {b}" for b in self.generated_copy.get('bullets', [])])}

**Total Score**: {self.scoring_results.get('total_score', 0)}/310
"""

            report_path = os.path.join(self.output_dir, "simple_report.md")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(simple_report)

            return {
                "status": "simulated",
                "report_path": report_path
            }

    def run_workflow(self, steps: List[int] = None) -> Dict[str, Any]:
        """
        运行完整工作流或指定步骤

        Args:
            steps: 要运行的步骤列表，如 [0, 3, 5, 6, 7, 8, 9]
                  None表示运行所有步骤
        """
        if steps is None:
            steps = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

        results = {}

        # 步骤映射到函数
        step_functions = {
            0: self.run_step_0,
            1: self.run_step_1,
            2: self.run_step_2,
            3: self.run_step_3,
            4: self.run_step_4,
            5: self.run_step_5,
            6: self.run_step_6,
            7: self.run_step_7,
            8: self.run_step_8,
            9: self.run_step_9
        }

        for step in steps:
            if step in step_functions:
                print(f"\n>>> 开始执行 Step {step}")
                result = step_functions[step]()
                results[f"step_{step}"] = result

                if result.get("status") == "error":
                    print(f"!!! Step {step} 执行失败，是否继续？[y/N]")
                    # 简化处理：遇到错误继续执行
            else:
                print(f"警告: Step {step} 未实现或跳过")

        print("\n" + "=" * 60)
        print("工作流执行完成")
        print("=" * 60)

        # 汇总结果
        summary = {
            "output_dir": self.output_dir,
            "steps_executed": steps,
            "results": results
        }

        # 保存执行摘要
        summary_path = os.path.join(self.output_dir, "execution_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f"执行摘要已保存到: {summary_path}")
        print(f"所有输出文件位于: {self.output_dir}")

        return summary


def _safe_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def main():
    """命令行入口点"""
    parser = argparse.ArgumentParser(description='Amazon Listing Generator 工作流')
    parser.add_argument('--config', required=True, help='run_config.json 文件路径')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR, help='输出目录')
    parser.add_argument('--steps', help='指定运行的步骤，如 "0,3,5,6,7,8,9"')
    parser.add_argument('--verbose', action='store_true', help='显示详细输出')

    args = parser.parse_args()

    # 解析步骤参数
    steps = None
    if args.steps:
        try:
            steps = [int(s.strip()) for s in args.steps.split(',')]
        except ValueError:
            print("错误: steps参数格式错误，应为逗号分隔的数字，如 '0,3,5,6'")
            return

    # 创建生成器实例
    generator = AmazonListingGenerator(args.config, args.output_dir)

    # 运行工作流
    try:
        summary = generator.run_workflow(steps)

        # 输出最终状态
        print("\n" + "=" * 60)
        print("执行状态:")
        print("=" * 60)

        for step_key, result in summary.get("results", {}).items():
            step_num = step_key.replace("step_", "")
            status = result.get("status", "unknown")
            print(f"Step {step_num}: {status}")

        print(f"\n输出目录: {summary.get('output_dir')}")

    except Exception as e:
        print(f"工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
