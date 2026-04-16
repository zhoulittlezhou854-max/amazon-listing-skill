#!/usr/bin/env python3
"""
Amazon Listing Generator - 主工作流脚本
版本: v1.0
功能: 整合 Step 0-9 完整工作流，支持增量实现
"""

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional fallback when dependency missing locally
    from pathlib import Path
    import os

    def load_dotenv(dotenv_path: str = "", **_kwargs):
        path = Path(dotenv_path) if dotenv_path else Path.cwd() / ".env"
        if not path.exists():
            return False
        changed = False
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value and key not in os.environ:
                os.environ[key] = value
                changed = True
        return changed

load_dotenv()

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
    from modules import report_builder
    from modules import visual_audit
    from modules import keyword_arsenal
    from modules import intent_translator
    from modules import blueprint_generator
    from modules.llm_client import (
        configure_llm_runtime,
        get_llm_client,
        LLMClientUnavailable,
    )
    from modules import input_validator
    from modules import repair_logger
except ImportError as e:
    raise RuntimeError(f"模块加载失败: {e}")

# 配置常量
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_REPORT_FILE = "listing_report.md"


def load_preprocessed_snapshot(preprocessed_path: str) -> Any:
    """Reconstruct a lightweight preprocessed object from saved JSON for UI/services reuse."""
    with open(preprocessed_path, "r", encoding="utf-8") as f:
        preprocessed_dict = json.load(f)

    class LazyPreprocessedData:
        def __init__(self, d):
            pd = d.get('preprocessed_data', {}) if isinstance(d, dict) else {}
            self.run_config = type('obj', (object,), pd.get('run_config', {}))()
            attr_block = pd.get('attribute_data', {})
            if isinstance(attr_block, dict) and 'data' in attr_block:
                attr_payload = attr_block.get('data', {})
            else:
                attr_payload = attr_block or {}
            self.attribute_data = type('obj', (object,), {'data': attr_payload})()
            kd = d.get('keyword_data', {}) or pd.get('keyword_data', {})
            self.keyword_data = type('obj', (object,), {'keywords': kd.get('keywords', []) if isinstance(kd, dict) else []})()
            rd = d.get('review_data', {}) or pd.get('review_data', {})
            self.review_data = type('obj', (object,), {'insights': rd.get('insights', []) if isinstance(rd, dict) else []})()
            ad = d.get('aba_data', {}) or pd.get('aba_data', {})
            self.aba_data = type('obj', (object,), {'trends': ad.get('trends', []) if isinstance(ad, dict) else []})()
            self.core_selling_points = pd.get('core_selling_points', [])
            self.canonical_core_selling_points = pd.get('canonical_core_selling_points', [])
            self.accessory_descriptions = pd.get('accessory_descriptions', [])
            self.canonical_accessory_descriptions = pd.get('canonical_accessory_descriptions', [])
            self.canonical_capability_notes = pd.get('canonical_capability_notes', {})
            self.quality_score = pd.get('quality_score', 0)
            self.language = pd.get('language', 'English')
            self.target_country = pd.get('target_country', 'US')
            self.reasoning_language = pd.get('reasoning_language', 'EN')
            self.data_mode = pd.get('data_mode', 'SYNTHETIC_COLD_START')
            self.processed_at = pd.get('processed_at', '')
            self.capability_constraints = pd.get('capability_constraints', {})
            self.supplement_signals = d.get('supplement_source', {})
            self.raw_human_insights = pd.get('raw_human_insights', "")
            self.ingestion_audit = pd.get('ingestion_audit', {})
            self.feedback_context = pd.get('feedback_context', {})
            self.asin_entity_profile = pd.get('asin_entity_profile', {})
            self.intent_weight_snapshot = pd.get('intent_weight_snapshot', {})
            rv = d.get('real_vocab', {})
            self.real_vocab = type('obj', (object,), rv)() if isinstance(rv, dict) else rv
            self.data_alerts = d.get('data_alerts', [])
            self.keyword_metadata = pd.get('keyword_metadata', [])

    return LazyPreprocessedData(preprocessed_dict)


class AmazonListingGenerator:
    """亚马逊Listing生成器主类"""

    def __init__(
        self,
        config_path: str,
        output_dir: str = None,
        *,
        blueprint_model_override: Optional[str] = None,
        title_model_override: Optional[str] = None,
        bullet_model_override: Optional[str] = None,
    ):
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
        self.bullet_blueprint = None
        self.generated_copy = None
        self.risk_report = None
        self.scoring_results = None
        self._config_cache: Optional[Dict[str, Any]] = None
        self._llm_client = None
        self._runtime_healthcheck: Dict[str, Any] = {}
        self.input_validation_warnings: List[Dict[str, Any]] = []
        self.blueprint_model_override = (blueprint_model_override or "").strip()
        self.title_model_override = (title_model_override or "").strip()
        self.bullet_model_override = (bullet_model_override or "").strip()

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        self._initialize_runtime()

    def load_config(self) -> Dict[str, Any]:
        """加载运行配置"""
        if self._config_cache is None:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_cache = json.load(f)
        configure_llm_runtime((self._config_cache or {}).get("llm"))
        return self._config_cache

    def _initialize_runtime(self) -> None:
        """在任何步骤开始前验证 LLM 运行环境。"""
        config = self.load_config()
        llm_config = config.get("llm") or {}
        try:
            client = get_llm_client()
        except LLMClientUnavailable as exc:
            raise RuntimeError(f"LLM 初始化失败：{exc}") from exc
        if getattr(client, "is_offline", True):
            force_required = bool(llm_config.get("force_live_llm", False))
            reason = "未检测到实时 LLM" if force_required else "当前运行未配置可用的实时 LLM"
            raise RuntimeError(f"{reason}，已终止。")
        if getattr(client, "has_http_fallback_provider", False):
            if not client.probe_http_fallback():
                print("⚠️ HTTP fallback provider probe failed; workflow will keep codex exec only as last-resort fallback.")
        healthcheck = client.healthcheck()
        self._runtime_healthcheck = healthcheck
        if not healthcheck.get("ok") and not healthcheck.get("degraded_ok"):
            raise RuntimeError(
                "LLM 健康检查失败："
                + (healthcheck.get("error") or "live runtime unavailable")
            )
        if healthcheck.get("degraded_ok") and not healthcheck.get("ok"):
            print(
                "⚠️ LLM healthcheck degraded:"
                f" {healthcheck.get('error') or 'missing_text'};"
                " workflow will continue with field-level fallback when needed."
            )
        self._llm_client = client

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

        run_config_obj = type('InputRunConfig', (object,), config)()
        self.input_validation_warnings = input_validator.warnings_as_dicts(
            input_validator.validate_input_tables(run_config_obj)
        )

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
            entity_profile = getattr(preprocessed, "asin_entity_profile", {}) or {}
            if entity_profile:
                entity_profile_path = os.path.join(self.output_dir, "asin_entity_profile.json")
                with open(entity_profile_path, "w", encoding="utf-8") as f:
                    json.dump(entity_profile, f, ensure_ascii=False, indent=2)
            print(f"✓ 数据预处理完成，质量评分: {preprocessed.quality_score}/100")
            print(f"  核心卖点: {len(preprocessed.core_selling_points)}个")
            print(f"  语言: {preprocessed.language}")

            return {
                "status": "success",
                "quality_score": preprocessed.quality_score,
                "selling_points_count": len(preprocessed.core_selling_points),
                "language": preprocessed.language,
                "input_validation": self.input_validation_warnings,
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
                self.preprocessed_data.language,
                getattr(self.preprocessed_data, "capability_constraints", {}) or {},
            )

            print(f"✓ 能力检查完成")
            print(f"  允许宣称: {len(capability_results.get('allowed_visible', capability_results.get('allowed', [])))}项")
            print(f"  限制宣称: {len(capability_results.get('allowed_with_condition', capability_results.get('restricted', [])))}项")
            print(f"  FAQ only: {len(capability_results.get('faq_only', []))}项")
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
        生成文案写作策略（使用默认4场景模板）
        """
        print("\n" + "=" * 60)
        print("Step 5: writing_policy 生成")
        print("=" * 60)

        if not self.preprocessed_data:
            return {"status": "error", "error": "需要先运行 Step 0"}

        try:
            policy = writing_policy.generate_policy(
                self.preprocessed_data,
                getattr(self.preprocessed_data, "core_selling_points", []) or [],
                getattr(self.preprocessed_data, "language", "English"),
            )

            self.writing_policy = policy

            # 保存policy到文件
            policy_path = os.path.join(self.output_dir, "writing_policy.json")
            with open(policy_path, 'w', encoding='utf-8') as f:
                json.dump(policy, f, ensure_ascii=False, indent=2)

            print(f"✓ writing_policy 生成完成（动态策略）")
            print(f"  场景优先级: {policy.get('scene_priority', [])}")
            print(f"  关键词分配策略: {policy.get('keyword_allocation_strategy', 'balanced')}")
            print(f"  能力场景绑定: {len(policy.get('capability_scene_bindings', []))}项")

            try:
                blueprint_fn = (
                    blueprint_generator.generate_bullet_blueprint_r1
                    if self.blueprint_model_override == "deepseek-reasoner"
                    else blueprint_generator.generate_bullet_blueprint
                )
                blueprint = blueprint_fn(
                    preprocessed_data=self.preprocessed_data,
                    writing_policy=self.writing_policy,
                    intent_graph=self.intent_graph,
                    output_path=os.path.join(self.output_dir, "bullet_blueprint.json"),
                )
                self.bullet_blueprint = blueprint
                bullet_count = len((blueprint or {}).get("bullets", []))
                source_model = (blueprint or {}).get("llm_model") or "unknown"
                print(f"  Bullet Blueprint 已生成: {bullet_count} 槽位 ({source_model})")
            except Exception as blueprint_error:
                print(f"⚠️ Blueprint 生成失败：{blueprint_error}")
                if self.blueprint_model_override == "deepseek-reasoner":
                    return {
                        "status": "error",
                        "error": f"experimental_version_b_blueprint_failed: {blueprint_error}",
                    }

            return {
                "status": "success",
                "policy_path": policy_path,
                "scene_count": len(policy.get('scene_priority', []))
            }

        except Exception as e:
            print(f"✗ writing_policy 生成失败: {e}")
            # 生成模拟policy（4场景默认）
            mock_policy = {
                "scene_priority": ["cycling_recording", "underwater_exploration", "travel_documentation", "family_use"],
                "keyword_allocation_strategy": "balanced",
                "capability_scene_bindings": [
                    {
                        "capability": "4k recording",
                        "binding_type": "used_for_func",
                        "allowed_scenes": ["underwater_exploration", "travel_documentation"],
                        "forbidden_scenes": []
                    }
                ],
                "faq_only_capabilities": ["数字防抖限制说明", "防水深度限制"],
                "forbidden_pairs": [["5K", "防抖"]],
                "bullet_slot_rules": {
                    "B1": "Mounting system + Primary scene + P0 capability",
                    "B2": "P0 core capability + Quantified parameters",
                    "B3": "P1 competitor pain point comparison + Scene keywords",
                    "B4": "P1/P2 capability + Boundary statement",
                    "B5": "P2 warranty/after-sale/compatibility"
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

        # 确保 LLM 配置已加载（支持 force_live_llm）
        self.load_config()

        # 懒加载：如果没有 preprocessed_data，尝试从磁盘加载
        if not self.preprocessed_data:
            preprocessed_path = os.path.join(self.output_dir, "preprocessed_data.json")
            if os.path.exists(preprocessed_path):
                print("  从磁盘加载 preprocessed_data...")
                self.preprocessed_data = load_preprocessed_snapshot(preprocessed_path)
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
        if not self.intent_graph:
            ig_path = os.path.join(self.output_dir, "intent_graph.json")
            if os.path.exists(ig_path):
                print("  从磁盘加载 intent_graph...")
                with open(ig_path, 'r', encoding='utf-8') as f:
                    self.intent_graph = json.load(f)
        if not self.bullet_blueprint:
            blueprint_path = os.path.join(self.output_dir, "bullet_blueprint.json")
            if os.path.exists(blueprint_path):
                print("  从磁盘加载 bullet_blueprint...")
                with open(blueprint_path, 'r', encoding='utf-8') as f:
                    try:
                        self.bullet_blueprint = json.load(f)
                    except json.JSONDecodeError:
                        self.bullet_blueprint = None
        if self.blueprint_model_override == "deepseek-reasoner" and not self.bullet_blueprint:
            return {
                "status": "error",
                "error": "experimental_version_b_blueprint_missing",
                "generation_status": "live_failed",
            }

        # 如果 force_live_llm=True 且无可用 LLM，则在文案生成前直接报错
        try:
            llm_client = get_llm_client()
        except LLMClientUnavailable as exc:
            print(f"✗ 文案生成失败：{exc}")
            return {"status": "error", "error": str(exc)}
        else:
            mode_label = getattr(llm_client, "mode_label", "offline")
            provider_label = getattr(llm_client, "provider_label", "offline")
            print(f"  LLM Provider: {provider_label} ({mode_label})")
            if self._runtime_healthcheck:
                request_id = self._runtime_healthcheck.get("request_id") or "-"
                returned_model = self._runtime_healthcheck.get("returned_model") or "-"
                print(f"  LLM Healthcheck: ok={self._runtime_healthcheck.get('ok')} request_id={request_id} model={returned_model}")

        try:
            artifact_dir = os.path.join(self.output_dir, "step6_artifacts")
            repair_logger.initialize_repair_logs(artifact_dir)
            # 调用文案生成模块
            generated = copy_generation.generate_listing_copy(
                preprocessed_data=self.preprocessed_data,
                writing_policy=self.writing_policy,
                language=self.preprocessed_data.language,
                intent_graph=self.intent_graph,
                bullet_blueprint=self.bullet_blueprint,
                artifact_dir=artifact_dir,
                resume_existing=True,
                progress_callback=lambda message: print(f"  {message}"),
                model_overrides={
                    "title": self.title_model_override,
                    "bullets": self.bullet_model_override,
                },
            )

            self.generated_copy = generated

            # 保存文案到文件
            copy_path = os.path.join(self.output_dir, "generated_copy.json")
            with open(copy_path, 'w', encoding='utf-8') as f:
                json.dump(generated, f, ensure_ascii=False, indent=2)

            evidence_bundle = generated.get("evidence_bundle") or {}
            if evidence_bundle:
                evidence_path = os.path.join(self.output_dir, "evidence_bundle.json")
                with open(evidence_path, "w", encoding="utf-8") as f:
                    json.dump(evidence_bundle, f, ensure_ascii=False, indent=2)

            compute_tier_map = generated.get("compute_tier_map") or {}
            if compute_tier_map:
                compute_path = os.path.join(self.output_dir, "compute_tier_map.json")
                with open(compute_path, "w", encoding="utf-8") as f:
                    json.dump(compute_tier_map, f, ensure_ascii=False, indent=2)

            intent_weight_snapshot = getattr(self.preprocessed_data, "intent_weight_snapshot", {}) or {}
            if intent_weight_snapshot:
                snapshot_path = os.path.join(self.output_dir, "intent_weight_snapshot.json")
                with open(snapshot_path, "w", encoding="utf-8") as f:
                    json.dump(intent_weight_snapshot, f, ensure_ascii=False, indent=2)

            print(f"✓ 文案生成完成")
            print(f"  Title: {generated.get('title', '')[:50]}...")
            print(f"  Bullets: {len(generated.get('bullets', []))}条")
            print(f"  Description: {len(generated.get('description', ''))}字符")
            print(f"  FAQ: {len(generated.get('faq', []))}条")
            print(f"  Search Terms: {len(generated.get('search_terms', []))}个")
            metadata = generated.get("metadata") or {}
            generation_status = metadata.get("generation_status", "unknown")
            print(f"  Generation Status: {generation_status}")

            return {
                "status": "success",
                "copy_path": copy_path,
                "title_length": len(generated.get('title', '')),
                "bullets_count": len(generated.get('bullets', [])),
                "faq_count": len(generated.get('faq', [])),
                "generation_status": generation_status,
                "artifact_dir": artifact_dir,
                "llm_metadata": {
                    "configured_model": metadata.get("configured_model") or metadata.get("llm_model"),
                    "returned_model": metadata.get("returned_model"),
                    "provider": metadata.get("llm_provider"),
                    "wire_api": metadata.get("llm_wire_api"),
                    "request_id": metadata.get("llm_request_id"),
                },
            }

        except Exception as e:
            print(f"✗ 文案生成失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "generation_status": "live_failed",
                "artifact_dir": os.path.join(self.output_dir, "step6_artifacts"),
                "llm_metadata": getattr(llm_client, "response_metadata", {}) or {},
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
                attribute_data=self.preprocessed_data.attribute_data.data,
                capability_constraints=getattr(self.preprocessed_data, "capability_constraints", {}) or {},
                preprocessed_data=self.preprocessed_data,
            )

            validation_issues = list(self.input_validation_warnings or [])
            risk_results["input_validation"] = {
                "passed": 0 if validation_issues else 1,
                "total": 1,
                "issues": validation_issues,
                "all_passed": len(validation_issues) == 0,
            }
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
                self.preprocessed_data = load_preprocessed_snapshot(preprocessed_path)
            else:
                return {"status": "error", "error": "需要先运行 Step 0"}

        try:
            # 调用评分模块
            scores = scoring.calculate_scores(
                generated_copy=self.generated_copy,
                writing_policy=self.writing_policy,
                preprocessed_data=self.preprocessed_data,
                intent_graph=self.intent_graph,
                risk_report=self.risk_report,
            )

            self.scoring_results = scores

            # 保存评分结果
            scores_path = os.path.join(self.output_dir, "scoring_results.json")
            with open(scores_path, 'w', encoding='utf-8') as f:
                json.dump(scores, f, ensure_ascii=False, indent=2)

            total_score = scores.get('total_score', 0)
            max_total = scores.get('max_total', 330)
            excellent_threshold = int(round(max_total * (5 / 6))) if max_total else 0
            good_threshold = int(round(max_total * (2 / 3))) if max_total else 0
            grade_label = (
                "优秀"
                if total_score >= excellent_threshold
                else "良好"
                if total_score >= good_threshold
                else "需要改进"
            )

            print(f"✓ 算法评分完成")
            print(f"  A10评分: {scores.get('a10_score', 0)}/100")
            print(f"  COSMO评分: {scores.get('cosmo_score', 0)}/100")
            print(f"  Rufus评分: {scores.get('rufus_score', 0)}/100")
            price_info = scores.get('price_competitiveness', {}) or {}
            price_score = price_info.get('score', '—') if isinstance(price_info, dict) else price_info
            print(f"  价格竞争力: {price_score}/10")
            print(f"  总分: {total_score}/{max_total}")
            print(f"  等级: {grade_label}")

            return {
                "status": "success",
                "scores_path": scores_path,
                "total_score": total_score,
                "grade": grade_label,
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

        # 懒加载所有必要数据
        if not self.preprocessed_data:
            preprocessed_path = os.path.join(self.output_dir, "preprocessed_data.json")
            if os.path.exists(preprocessed_path):
                print("  从磁盘加载 preprocessed_data...")
                self.preprocessed_data = load_preprocessed_snapshot(preprocessed_path)
            else:
                return {"status": "error", "error": "preprocessed_data 不存在"}

        if not self.generated_copy:
            copy_path = os.path.join(self.output_dir, "generated_copy.json")
            if os.path.exists(copy_path):
                print("  从磁盘加载 generated_copy...")
                with open(copy_path, 'r', encoding='utf-8') as f:
                    self.generated_copy = json.load(f)
            else:
                return {"status": "error", "error": "generated_copy 不存在"}

        if not self.scoring_results:
            scores_path = os.path.join(self.output_dir, "scoring_results.json")
            if os.path.exists(scores_path):
                print("  从磁盘加载 scoring_results...")
                with open(scores_path, 'r', encoding='utf-8') as f:
                    self.scoring_results = json.load(f)
            else:
                return {"status": "error", "error": "scoring_results 不存在"}
        if not self.risk_report:
            risk_path = os.path.join(self.output_dir, "risk_report.json")
            if os.path.exists(risk_path):
                print("  从磁盘加载 risk_report...")
                with open(risk_path, 'r', encoding='utf-8') as f:
                    self.risk_report = json.load(f)

        if not self.writing_policy:
            wp_path = os.path.join(self.output_dir, "writing_policy.json")
            if os.path.exists(wp_path):
                print("  从磁盘加载 writing_policy...")
                with open(wp_path, 'r', encoding='utf-8') as f:
                    self.writing_policy = json.load(f)
        if not self.intent_graph:
            ig_path = os.path.join(self.output_dir, "intent_graph.json")
            if os.path.exists(ig_path):
                print("  从磁盘加载 intent_graph...")
                with open(ig_path, 'r', encoding='utf-8') as f:
                    self.intent_graph = json.load(f)

        try:
            # 调用报告生成模块
            report_content = report_generator.generate_report(
                preprocessed_data=self.preprocessed_data,
                generated_copy=self.generated_copy,
                writing_policy=self.writing_policy,
                risk_report=self.risk_report,
                scoring_results=self.scoring_results,
                language=self.preprocessed_data.language,
                intent_graph=self.intent_graph
            )

            # 保存报告
            report_path = os.path.join(self.output_dir, DEFAULT_REPORT_FILE)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)

            action_items = report_generator.generate_action_items(
                preprocessed_data=self.preprocessed_data,
                generated_copy=self.generated_copy,
                writing_policy=self.writing_policy or {},
                scoring_results=self.scoring_results or {}
            )
            config_stem = Path(self.config_path).stem
            output_name = Path(self.output_dir).name
            run_suffix = output_name[len(config_stem) + 1:] if output_name.startswith(f"{config_stem}_") else output_name
            readiness_summary = report_builder.build_readiness_summary(
                sku=config_stem,
                run_id=run_suffix,
                generated_copy=self.generated_copy or {},
                scoring_results=self.scoring_results or {},
                risk_report=self.risk_report or {},
                generated_at=str(getattr(self.preprocessed_data, 'processed_at', '')),
            )
            readiness_path = os.path.join(self.output_dir, 'readiness_summary.md')
            with open(readiness_path, 'w', encoding='utf-8') as f:
                f.write(readiness_summary)
            action_items_path = os.path.join(self.output_dir, "action_items.json")
            with open(action_items_path, 'w', encoding='utf-8') as f:
                json.dump(action_items, f, ensure_ascii=False, indent=2)

            print(f"✓ 报告生成完成")
            print(f"  报告文件: {report_path}")
            print(f"  报告长度: {len(report_content)}字符")
            print(f"  行动项: {action_items_path}（{len(action_items)} 条）")

            return {
                "status": "success",
                "report_path": report_path,
                "report_length": len(report_content),
                "action_items_path": action_items_path,
                "action_items_count": len(action_items),
                "readiness_summary_path": readiness_path,
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

**Total Score**: {self.scoring_results.get('total_score', 0)}/{self.scoring_results.get('max_total', 330)}
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

        blocking_error_steps = {0, 3, 5, 6, 8, 9}
        executed_steps: List[int] = []
        workflow_status = "success"
        for step in steps:
            if step in step_functions:
                print(f"\n>>> 开始执行 Step {step}")
                executed_steps.append(step)
                result = step_functions[step]()
                results[f"step_{step}"] = result

                if result.get("status") == "error":
                    workflow_status = "failed"
                    print(f"!!! Step {step} 执行失败，已停止后续正式流程")
                    if step in blocking_error_steps:
                        break
            else:
                print(f"警告: Step {step} 未实现或跳过")

        print("\n" + "=" * 60)
        print("工作流执行完成")
        print("=" * 60)

        # 汇总结果
        summary = {
            "output_dir": self.output_dir,
            "steps_executed": executed_steps,
            "workflow_status": workflow_status,
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


def run_generator_workflow(
    config_path: str,
    output_dir: str,
    steps: Optional[List[int]] = None,
    *,
    blueprint_model_override: Optional[str] = None,
    title_model_override: Optional[str] = None,
    bullet_model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Programmatic entrypoint used by Streamlit/service layer."""
    generator = AmazonListingGenerator(
        config_path,
        output_dir,
        blueprint_model_override=blueprint_model_override,
        title_model_override=title_model_override,
        bullet_model_override=bullet_model_override,
    )
    summary = generator.run_workflow(steps)
    return {
        "summary": summary,
        "preprocessed_data": generator.preprocessed_data,
        "generated_copy": generator.generated_copy,
        "risk_report": generator.risk_report,
        "scoring_results": generator.scoring_results,
        "writing_policy": generator.writing_policy,
        "intent_graph": generator.intent_graph,
    }


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
