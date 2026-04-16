from __future__ import annotations

from typing import Any, Dict


def build_entity_profile(preprocessed_data: Any) -> Dict[str, Any]:
    run_config = getattr(preprocessed_data, "run_config", None)
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    attribute_data = getattr(getattr(preprocessed_data, "attribute_data", None), "data", {}) or {}
    supplement_signals = getattr(preprocessed_data, "supplement_signals", {}) or {}
    canonical_capabilities = list(getattr(preprocessed_data, "canonical_core_selling_points", []) or [])
    raw_capabilities = list(getattr(preprocessed_data, "core_selling_points", []) or [])
    accessory_descriptions = list(getattr(preprocessed_data, "canonical_accessory_descriptions", []) or [])
    if not accessory_descriptions:
        accessory_descriptions = list(getattr(preprocessed_data, "accessory_descriptions", []) or [])
    bundle_variant = (
        getattr(preprocessed_data, "bundle_variant", None)
        or supplement_signals.get("bundle_variant")
        or {}
    )

    claim_registry = []
    for capability in canonical_capabilities or raw_capabilities:
        if capability:
            claim_registry.append({"claim": str(capability), "source_type": "selling_point"})

    if constraints.get("runtime_minutes"):
        claim_registry.append(
            {"claim": f"{constraints['runtime_minutes']} minute runtime", "source_type": "constraint"}
        )
    if constraints.get("waterproof_depth_m"):
        suffix = " with case" if constraints.get("waterproof_requires_case") else ""
        claim_registry.append(
            {
                "claim": f"{constraints['waterproof_depth_m']} m waterproof{suffix}",
                "source_type": "constraint",
            }
        )

    evidence_refs = []
    for insight in getattr(getattr(preprocessed_data, "review_data", None), "insights", []) or []:
        if not isinstance(insight, dict):
            continue
        field_name = str(insight.get("field_name") or "").strip()
        if field_name:
            evidence_refs.append({"type": "review_insight", "field_name": field_name})

    return {
        "product_code": getattr(run_config, "product_code", ""),
        "brand_name": getattr(run_config, "brand_name", "") or attribute_data.get("brand", ""),
        "category": attribute_data.get("category") or attribute_data.get("product_type") or "action_camera",
        "target_country": getattr(preprocessed_data, "target_country", ""),
        "language": getattr(preprocessed_data, "language", ""),
        "core_specs": {
            "runtime_minutes": constraints.get("runtime_minutes"),
            "waterproof_depth_m": constraints.get("waterproof_depth_m"),
            "waterproof_requires_case": constraints.get("waterproof_requires_case"),
        },
        "capability_registry": canonical_capabilities or raw_capabilities,
        "accessory_registry": accessory_descriptions,
        "bundle_variant": bundle_variant,
        "claim_registry": claim_registry,
        "compliance_constraints": {
            "waterproof_requires_case": constraints.get("waterproof_requires_case"),
        },
        "evidence_refs": evidence_refs,
    }
