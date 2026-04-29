from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "amz-image-master" / "config" / "image_handoff_template.md"
SPEC_PATH = REPO_ROOT / "amz-image-master" / "docs" / "workflows" / "listing_to_image_handoff_spec.md"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        pairs = []
        for key, val in value.items():
            text = _safe_str(val)
            if text:
                pairs.append(f"{key}={text}")
        return ", ".join(pairs)
    return str(value).strip()


def _clean_items(values: Iterable[Any]) -> List[str]:
    items: List[str] = []
    for value in values or []:
        if isinstance(value, dict):
            text = _safe_str(value.get("claim") or value.get("value") or value.get("theme") or value.get("title"))
        else:
            text = _safe_str(value)
        if text and text not in items:
            items.append(text)
    return items


def _extract_attribute_data(preprocessed_data: Any) -> Dict[str, Any]:
    return getattr(getattr(preprocessed_data, "attribute_data", None), "data", {}) or {}


def _extract_run_config(preprocessed_data: Any) -> Any:
    return getattr(preprocessed_data, "run_config", None)


def _extract_entity_profile(preprocessed_data: Any) -> Dict[str, Any]:
    return getattr(preprocessed_data, "asin_entity_profile", {}) or {}


def _marketplace_label(country_code: str) -> str:
    code = (country_code or "").strip().upper() or "US"
    return f"Amazon {code}"


def _language_label(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> str:
    metadata = generated_copy.get("metadata") or {}
    return _safe_str(metadata.get("target_language") or getattr(preprocessed_data, "language", "") or "EN")


def _model_name(preprocessed_data: Any) -> str:
    bundle_variant = getattr(preprocessed_data, "bundle_variant", {}) or {}
    return _safe_str(
        bundle_variant.get("model")
        or bundle_variant.get("version_name")
        or bundle_variant.get("bundle_name")
    )


def _version_name(preprocessed_data: Any) -> str:
    bundle_variant = getattr(preprocessed_data, "bundle_variant", {}) or {}
    return _safe_str(bundle_variant.get("version_name") or bundle_variant.get("name"))


def _bundle_type(preprocessed_data: Any) -> str:
    bundle_variant = getattr(preprocessed_data, "bundle_variant", {}) or {}
    return _safe_str(bundle_variant.get("bundle_type") or bundle_variant.get("variant_type"))


def _color_variants(attr_data: Dict[str, Any]) -> str:
    candidates = [
        attr_data.get("color"),
        attr_data.get("colour"),
        attr_data.get("color_variant"),
        attr_data.get("available_colors"),
    ]
    for candidate in candidates:
        text = _safe_str(candidate)
        if text:
            return text
    return ""


def _core_specs(attr_data: Dict[str, Any], entity_profile: Dict[str, Any]) -> Dict[str, str]:
    core_specs = entity_profile.get("core_specs", {}) or {}
    runtime = core_specs.get("runtime_minutes") or attr_data.get("battery_life") or attr_data.get("runtime_minutes")
    waterproof = core_specs.get("waterproof_depth_m") or attr_data.get("waterproof_depth") or attr_data.get("waterproof")
    if waterproof:
        waterproof = f"{waterproof}m" if str(waterproof).isdigit() else waterproof
        if core_specs.get("waterproof_requires_case"):
            waterproof = f"{waterproof} with case"
    return {
        "video": _safe_str(attr_data.get("video_resolution") or attr_data.get("video") or attr_data.get("resolution")),
        "photo": _safe_str(attr_data.get("photo_resolution") or attr_data.get("photo")),
        "battery": _safe_str(runtime),
        "waterproof": _safe_str(waterproof),
        "stabilization": _safe_str(attr_data.get("image_stabilization") or attr_data.get("stabilization")),
        "screen": _safe_str(attr_data.get("screen") or attr_data.get("display")),
        "material": _safe_str(attr_data.get("material")),
        "charging_port": _safe_str(attr_data.get("charging_port") or attr_data.get("port")),
        "storage_support": _safe_str(attr_data.get("max_storage") or attr_data.get("storage_support")),
        "wireless": _safe_str(attr_data.get("wireless") or attr_data.get("wifi") or attr_data.get("bluetooth")),
    }


def _dimensions(attr_data: Dict[str, Any]) -> Dict[str, str]:
    return {
        "length": _safe_str(attr_data.get("length_mm") or attr_data.get("length")),
        "width": _safe_str(attr_data.get("width_mm") or attr_data.get("width")),
        "height": _safe_str(attr_data.get("height_mm") or attr_data.get("height")),
        "weight": _safe_str(attr_data.get("weight_g") or attr_data.get("weight")),
    }


def _compatibility(attr_data: Dict[str, Any], preprocessed_data: Any, entity_profile: Dict[str, Any]) -> Dict[str, str]:
    supported_devices = _safe_str(
        attr_data.get("compatible_devices")
        or attr_data.get("compatibility")
        or attr_data.get("supported_devices")
    )
    supported_accessories = _safe_str(entity_profile.get("accessory_registry") or getattr(preprocessed_data, "accessory_descriptions", []))
    mount_standard = _safe_str(attr_data.get("mount_standard") or attr_data.get("mount_type"))
    not_compatible = _safe_str(attr_data.get("not_compatible_with") or attr_data.get("compatibility_exclusions"))
    return {
        "supported_devices": supported_devices,
        "supported_accessories": supported_accessories,
        "mount_standard": mount_standard,
        "not_compatible_with": not_compatible,
    }


def _package_contents(preprocessed_data: Any, entity_profile: Dict[str, Any]) -> str:
    bundle_variant = getattr(preprocessed_data, "bundle_variant", {}) or {}
    items = []
    for candidate in [
        bundle_variant.get("included_items"),
        entity_profile.get("accessory_registry"),
        getattr(preprocessed_data, "accessory_descriptions", []),
    ]:
        items.extend(_clean_items(candidate if isinstance(candidate, list) else [candidate]))
    return ", ".join(dict.fromkeys(items))


def _search_terms(generated_copy: Dict[str, Any]) -> Dict[str, str]:
    terms = [str(item).strip() for item in generated_copy.get("search_terms", []) or [] if str(item).strip()]
    primary = terms[:5]
    secondary = terms[5:15]
    backend = terms[15:]
    return {
        "primary": ", ".join(primary),
        "secondary": ", ".join(secondary),
        "backend": ", ".join(backend),
    }


def _best_hero_claim(generated_copy: Dict[str, Any], evidence_bundle: Dict[str, Any], preprocessed_data: Any) -> str:
    claims = evidence_bundle.get("claim_support_matrix", []) or []
    for row in claims:
        if str((row or {}).get("support_status") or "").lower() == "supported":
            return _safe_str((row or {}).get("claim"))
    bullet_blueprint = generated_copy.get("bullet_blueprint") or {}
    bullet_rows = bullet_blueprint.get("bullets") or []
    if bullet_rows:
        return _safe_str((bullet_rows[0] or {}).get("theme"))
    selling_points = list(getattr(preprocessed_data, "canonical_core_selling_points", []) or getattr(preprocessed_data, "core_selling_points", []) or [])
    return _safe_str(selling_points[:1])


def _spec_strength(specs: Dict[str, str]) -> str:
    populated = sum(1 for value in specs.values() if _safe_str(value))
    if populated >= 5:
        return "high"
    if populated >= 3:
        return "medium"
    if populated >= 1:
        return "low"
    return "unknown"


def _bool_label(value: bool) -> str:
    return "true" if value else "false"


def _preferred_visuals_for_claim(claim_text: str) -> str:
    lowered = (claim_text or "").lower()
    if any(token in lowered for token in ["runtime", "battery", "waterproof", "weight", "fps", "4k", "resolution", "storage", "screen", "port"]):
        return "feature / dimension / faq_trust"
    if any(token in lowered for token in ["commuting", "travel", "ride", "outdoor", "workout", "bike", "flight", "subway"]):
        return "scene / feature"
    return "feature / scene / package"


def _selling_points(generated_copy: Dict[str, Any], preprocessed_data: Any) -> List[Dict[str, str]]:
    evidence_bundle = generated_copy.get("evidence_bundle", {}) or {}
    claim_rows = evidence_bundle.get("claim_support_matrix", []) or []
    bullets = [str(item).strip() for item in generated_copy.get("bullets", []) or [] if str(item).strip()]
    blueprint_rows = ((generated_copy.get("bullet_blueprint") or {}).get("bullets") or [])
    points: List[Dict[str, str]] = []
    source_claims = claim_rows[:5] or [{"claim": bullet} for bullet in bullets[:5]]
    for idx, row in enumerate(source_claims[:5], start=1):
        bullet_text = bullets[idx - 1] if idx - 1 < len(bullets) else ""
        blueprint = blueprint_rows[idx - 1] if idx - 1 < len(blueprint_rows) else {}
        claim_text = _safe_str((row or {}).get("claim") or bullet_text or (blueprint or {}).get("theme"))
        if not claim_text:
            continue
        support_status = str((row or {}).get("support_status") or "").strip().lower()
        points.append(
            {
                "title": _safe_str((blueprint or {}).get("theme") or claim_text),
                "claim": claim_text,
                "benefit": bullet_text,
                "priority": str(idx),
                "preferred_visuals": _preferred_visuals_for_claim(claim_text),
                "headline": _safe_str((blueprint or {}).get("theme") or claim_text),
                "proof_points": _safe_str((blueprint or {}).get("proof_angle") or (blueprint or {}).get("mandatory_elements")),
                "must_include": _safe_str((blueprint or {}).get("mandatory_elements")),
                "must_avoid": _safe_str((blueprint or {}).get("negative_constraints")),
                "evidence_type": _safe_str((row or {}).get("source_type") or "claim_registry"),
                "evidence_value": support_status or "unknown",
                "evidence_source": _safe_str((row or {}).get("source") or "evidence_bundle.claim_support_matrix"),
                "evidence_confidence": "0.90" if support_status == "supported" else ("0.60" if support_status == "weakly_supported" else "0.30"),
            }
        )
    return points


def _common_questions(generated_copy: Dict[str, Any]) -> List[str]:
    questions = []
    for item in generated_copy.get("faq", []) or []:
        if isinstance(item, dict):
            q = _safe_str(item.get("q") or item.get("question"))
        else:
            q = _safe_str(item)
        if q:
            questions.append(q)
    return questions[:5]


def _common_objections(risk_report: Dict[str, Any]) -> List[str]:
    objections = []
    for issue in risk_report.get("issues", []) or []:
        text = _safe_str((issue or {}).get("message") or (issue or {}).get("reason"))
        if text:
            objections.append(text)
    listing_status = risk_report.get("listing_status", {}) or {}
    objections.extend(_clean_items(listing_status.get("blocking_reasons") or []))
    return objections[:5]


def _trust_builders(generated_copy: Dict[str, Any], evidence_bundle: Dict[str, Any]) -> List[str]:
    builders = []
    rufus = evidence_bundle.get("rufus_readiness", {}) or {}
    if rufus.get("supported_claim_count"):
        builders.append(f"Supported claims: {rufus.get('supported_claim_count')}/{rufus.get('total_claim_count')}")
    meta = generated_copy.get("metadata", {}) or {}
    if meta.get("generation_status"):
        builders.append(f"Generation status: {meta.get('generation_status')}")
    return builders[:4]


def build_image_handoff_markdown(
    *,
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any] | None = None,
    intent_graph: Dict[str, Any] | None = None,
    risk_report: Dict[str, Any] | None = None,
) -> str:
    writing_policy = writing_policy or {}
    intent_graph = intent_graph or {}
    risk_report = risk_report or {}
    attr_data = _extract_attribute_data(preprocessed_data)
    entity_profile = _extract_entity_profile(preprocessed_data)
    run_config = _extract_run_config(preprocessed_data)
    evidence_bundle = generated_copy.get("evidence_bundle", {}) or {}
    specs = _core_specs(attr_data, entity_profile)
    dims = _dimensions(attr_data)
    compatibility = _compatibility(attr_data, preprocessed_data, entity_profile)
    package_contents = _package_contents(preprocessed_data, entity_profile)
    keyword_groups = _search_terms(generated_copy)
    selling_points = _selling_points(generated_copy, preprocessed_data)
    questions = _common_questions(generated_copy)
    objections = _common_objections(risk_report)
    trust_builders = _trust_builders(generated_copy, evidence_bundle)
    input_files = getattr(run_config, "input_files", {}) or {}
    image_paths = input_files.get("product_images") or []
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    comparison_available = bool(input_files.get("competitor_images") or input_files.get("competitor_refs"))
    scene_available = any("scene" in str(path).lower() or "lifestyle" in str(path).lower() for path in image_paths)
    package_available = bool(package_contents)
    must_show = _clean_items([
        _best_hero_claim(generated_copy, evidence_bundle, preprocessed_data),
        specs.get("video"),
        specs.get("waterproof"),
        specs.get("battery"),
        compatibility.get("supported_devices"),
    ])[:5]
    forbidden = _clean_items(
        list((risk_report.get("forbidden_elements") or []))
        + list((writing_policy.get("forbidden_pairs") or []))
    )
    title = _safe_str(generated_copy.get("title"))
    bullets = [str(item).strip() for item in generated_copy.get("bullets", []) or [] if str(item).strip()]
    audience = _clean_items(
        list((intent_graph.get("audience_priority") or []))
        + list((writing_policy.get("audience_priority") or []))
    )
    scenes = _clean_items(
        list((intent_graph.get("scene_priority") or []))
        + list((writing_policy.get("scene_priority") or []))
    )
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8") if TEMPLATE_PATH.exists() else "# Image Handoff\n"
    lines: List[str] = []
    lines.append(template_text.splitlines()[0] if template_text else "# Image Handoff")
    lines.append("")
    lines.extend(
        [
            "> Generated from listing outputs using the amz-image-master handoff contract.",
            "",
            "## 1. Product Identity",
            "",
            f"- Product ID: {_safe_str(getattr(run_config, 'product_code', '') or entity_profile.get('product_code'))}",
            f"- SKU: {_safe_str(getattr(run_config, 'product_code', '') or entity_profile.get('product_code'))}",
            f"- Product Name: {_safe_str(title or attr_data.get('product_name') or entity_profile.get('category'))}",
            f"- Brand: {_safe_str(getattr(run_config, 'brand_name', '') or entity_profile.get('brand_name'))}",
            f"- Category: {_safe_str(entity_profile.get('category') or attr_data.get('category') or attr_data.get('product_type'))}",
            f"- Subcategory: {_safe_str(attr_data.get('subcategory') or attr_data.get('product_type'))}",
            f"- Marketplace: {_marketplace_label(getattr(preprocessed_data, 'target_country', '') or getattr(run_config, 'target_country', ''))}",
            f"- Language: {_language_label(preprocessed_data, generated_copy)}",
            f"- Model: {_model_name(preprocessed_data)}",
            f"- Version Name: {_version_name(preprocessed_data)}",
            f"- Bundle Type: {_bundle_type(preprocessed_data)}",
            f"- Color Variants: {_color_variants(attr_data)}",
            "",
            "## 2. Listing Copy",
            "",
            "### Title",
            "",
            title,
            "",
            "### Five Bullets",
            "",
        ]
    )
    for idx in range(5):
        bullet_text = bullets[idx] if idx < len(bullets) else ""
        lines.append(f"{idx + 1}. {bullet_text}")
    lines.extend(
        [
            "",
            "### Keywords",
            "",
            f"- Primary Keywords: {keyword_groups['primary']}",
            f"- Secondary Keywords: {keyword_groups['secondary']}",
            f"- Backend Search Terms: {keyword_groups['backend']}",
            "",
            "### Audience and Use Case",
            "",
            f"- Target Audience: {_safe_str(audience)}",
            f"- Use Case Summary: {_safe_str(scenes)}",
            f"- Short Selling Points: {_safe_str(_clean_items([point['title'] for point in selling_points]))}",
            "",
            "## 3. Selling Points With Evidence",
            "",
            "> One block per priority selling point. Prefer 3-5 points. Every point should include claim + benefit + evidence when possible.",
            "",
        ]
    )
    for idx, point in enumerate(selling_points[:5], start=1):
        lines.extend(
            [
                f"### Selling Point {idx}",
                "",
                f"- Title: {point['title']}",
                f"- Claim: {point['claim']}",
                f"- Benefit: {point['benefit']}",
                f"- Priority: {point['priority']}",
                f"- Preferred Visuals: {point['preferred_visuals']}",
                f"- Suggested Headline: {point['headline']}",
                f"- Suggested Proof Points: {point['proof_points']}",
                f"- Must Include: {point['must_include']}",
                f"- Must Avoid: {point['must_avoid']}",
                "",
                "Evidence:",
                f"- Type: {point['evidence_type']}",
                f"- Value: {point['evidence_value']}",
                f"- Source: {point['evidence_source']}",
                f"- Confidence: {point['evidence_confidence']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 4. Product Facts",
            "",
            "### Dimensions",
            "",
            f"- Length (mm): {dims['length']}",
            f"- Width (mm): {dims['width']}",
            f"- Height (mm): {dims['height']}",
            f"- Weight (g): {dims['weight']}",
            "",
            "### Core Specs",
            "",
            f"- Video: {specs['video']}",
            f"- Photo: {specs['photo']}",
            f"- Battery: {specs['battery']}",
            f"- Waterproof: {specs['waterproof']}",
            f"- Stabilization: {specs['stabilization']}",
            f"- Screen: {specs['screen']}",
            f"- Material: {specs['material']}",
            f"- Charging Port: {specs['charging_port']}",
            f"- Storage Support: {specs['storage_support']}",
            f"- Wireless: {specs['wireless']}",
            f"- Other Specs: {_safe_str(attr_data.get('other_specs') or attr_data.get('special_features'))}",
            "",
            "### Compatibility",
            "",
            f"- Supported Devices: {compatibility['supported_devices']}",
            f"- Supported Accessories: {compatibility['supported_accessories']}",
            f"- Mount Standard: {compatibility['mount_standard']}",
            f"- Not Compatible With: {compatibility['not_compatible_with']}",
            "",
            "## 5. Package Contents",
            "",
            f"- Included Items: {package_contents}",
            f"- Not Included Items: {_safe_str(attr_data.get('not_included_items'))}",
            f"- Warranty: {_safe_str(attr_data.get('warranty_period') or attr_data.get('warranty'))}",
            f"- Support Notes: {_safe_str(attr_data.get('support_notes'))}",
            "",
            "## 6. Image Planning Hints",
            "",
            f"- Best Hero Claim: {_best_hero_claim(generated_copy, evidence_bundle, preprocessed_data)}",
            f"- Must Show In Images: {_safe_str(must_show)}",
            f"- Comparison Available: {_bool_label(comparison_available)}",
            f"- Scene Assets Available: {_bool_label(scene_available)}",
            f"- Package Assets Available: {_bool_label(package_available)}",
            f"- Spec Strength: {_spec_strength(specs)}",
            f"- Compliance Notes: {_safe_str((risk_report.get('listing_status') or {}).get('blocking_reasons') or attr_data.get('compliance_notes'))}",
            f"- Forbidden Elements: {_safe_str(forbidden)}",
            "",
            "### Fallback Preferences",
            "",
            "- If No Comparison: usage_scene / feature_proof / faq_or_trust",
            "- If No Scene: feature_proof / package_or_trust",
            "- If Weak Specs: feature_proof / package_or_trust",
            "",
            "## 7. FAQ and Risk Reduction",
            "",
            f"- Common Questions: {_safe_str(questions)}",
            f"- Common Objections: {_safe_str(objections)}",
            f"- Trust Builders: {_safe_str(trust_builders)}",
            f"- Return Risk Notes: {_safe_str((risk_report.get('return_risk') or {}).get('summary') or attr_data.get('return_risk_notes'))}",
            "",
            "## 8. Source Tracking",
            "",
            "- Generated By: modules.image_handoff.build_image_handoff_markdown",
            f"- Generated At: {datetime.now(timezone.utc).isoformat()}",
            f"- Source Files: {_safe_str(input_files)}",
            f"- Notes: Template={TEMPLATE_PATH.relative_to(REPO_ROOT) if TEMPLATE_PATH.exists() else 'missing'}, Spec={SPEC_PATH.relative_to(REPO_ROOT) if SPEC_PATH.exists() else 'missing'}",
            "",
            "## 9. Minimal Quality Rules",
            "",
            "- Do not fabricate unsupported technical claims.",
            "- Prefer explicit enumerations over vague phrases.",
            "- If data is unknown, leave it blank instead of guessing.",
            "- If a claim has no evidence, mark it clearly or omit it.",
            "- Compatibility should be listed explicitly whenever possible.",
            "- Package contents should distinguish included vs not included.",
            "",
        ]
    )
    return "\n".join(lines)


def write_image_handoff(
    *,
    output_dir: Path | str,
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any] | None = None,
    intent_graph: Dict[str, Any] | None = None,
    risk_report: Dict[str, Any] | None = None,
) -> Path:
    output_path = Path(output_dir) / "image_handoff.md"
    content = build_image_handoff_markdown(
        preprocessed_data=preprocessed_data,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        intent_graph=intent_graph,
        risk_report=risk_report,
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path
