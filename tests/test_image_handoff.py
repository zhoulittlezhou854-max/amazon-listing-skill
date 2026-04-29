from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from modules.image_handoff import build_image_handoff_markdown, write_image_handoff


def _sample_preprocessed() -> SimpleNamespace:
    return SimpleNamespace(
        run_config=SimpleNamespace(
            product_code="H91LITE",
            brand_name="TOSBARRFT",
            target_country="US",
            input_files={
                "attribute_table": "config/products/H91lite_US/attrs.txt",
                "product_images": ["assets/hero_main.jpg", "assets/scene_bike.jpg"],
            },
        ),
        target_country="US",
        language="EN",
        bundle_variant={"model": "H91 Lite", "version_name": "Standard Kit", "bundle_type": "single_camera"},
        attribute_data=SimpleNamespace(
            data={
                "category": "action_camera",
                "product_type": "sports_camera",
                "video_resolution": "4K60FPS",
                "battery_life": "150 minutes",
                "waterproof_depth": "131FT with case",
                "image_stabilization": "EIS",
                "max_storage": "512GB",
                "charging_port": "USB-C",
                "weight_g": "145",
                "color": "Black",
                "compatible_devices": "iPhone 16, Galaxy S25, MacBook Air M4",
                "warranty_period": "12 months",
            }
        ),
        asin_entity_profile={
            "product_code": "H91LITE",
            "brand_name": "TOSBARRFT",
            "category": "action_camera",
            "core_specs": {"runtime_minutes": 150, "waterproof_depth_m": 40, "waterproof_requires_case": True},
            "accessory_registry": ["waterproof case", "helmet mount", "battery"],
            "claim_registry": [
                {"claim": "4K60FPS recording", "source_type": "selling_point"},
                {"claim": "150 minute runtime", "source_type": "constraint"},
            ],
        },
        core_selling_points=["4K60FPS recording", "EIS stabilization", "131FT waterproof with case"],
        canonical_core_selling_points=["4K60FPS recording", "EIS stabilization", "131FT waterproof with case"],
        accessory_descriptions=["waterproof case", "helmet mount", "battery"],
    )


def _sample_generated_copy() -> dict:
    return {
        "title": "TOSBARRFT H91 Lite 4K60FPS Action Camera with EIS and Waterproof Case",
        "bullets": [
            "Record 4K60FPS video with smoother motion for outdoor rides and travel.",
            "Use EIS stabilization to reduce shake on bike trails and ski runs.",
            "Go up to 131FT underwater with the included waterproof case.",
        ],
        "search_terms": ["action camera", "4k action camera", "waterproof camera", "bike camera"],
        "faq": [
            {"q": "Can I use this underwater?", "a": "Yes, with the included waterproof case."},
            {"q": "Does it support large storage cards?", "a": "Supports up to 512GB microSD."},
        ],
        "bullet_blueprint": {
            "bullets": [
                {"theme": "4K60FPS action capture", "proof_angle": "resolution + motion smoothness", "mandatory_elements": ["4K60FPS", "outdoor ride"]},
                {"theme": "EIS stabilization", "proof_angle": "shake reduction", "mandatory_elements": ["EIS", "bike trail"]},
                {"theme": "Underwater recording", "proof_angle": "depth with case", "mandatory_elements": ["131FT", "waterproof case"]},
            ]
        },
        "metadata": {"target_language": "EN", "generation_status": "live_success"},
        "evidence_bundle": {
            "claim_support_matrix": [
                {"claim": "4K60FPS recording", "source_type": "selling_point", "support_status": "supported"},
                {"claim": "150 minute runtime", "source_type": "constraint", "support_status": "supported"},
            ],
            "rufus_readiness": {"supported_claim_count": 2, "total_claim_count": 2},
        },
    }


def test_build_image_handoff_markdown_contains_required_sections() -> None:
    markdown = build_image_handoff_markdown(
        preprocessed_data=_sample_preprocessed(),
        generated_copy=_sample_generated_copy(),
        writing_policy={"scene_priority": ["cycling", "travel"]},
        intent_graph={"audience_priority": ["young riders", "entry users"]},
        risk_report={"listing_status": {"blocking_reasons": []}},
    )

    assert "# Image Handoff" in markdown
    assert "## 1. Product Identity" in markdown
    assert "## 3. Selling Points With Evidence" in markdown
    assert "TOSBARRFT H91 Lite 4K60FPS Action Camera" in markdown
    assert "4K60FPS recording" in markdown
    assert "Supported claims: 2/2" in markdown


def test_write_image_handoff_writes_markdown_file(tmp_path: Path) -> None:
    output_path = write_image_handoff(
        output_dir=tmp_path,
        preprocessed_data=_sample_preprocessed(),
        generated_copy=_sample_generated_copy(),
        writing_policy={},
        intent_graph={},
        risk_report={},
    )

    assert output_path == tmp_path / "image_handoff.md"
    assert output_path.exists()
    assert "## 6. Image Planning Hints" in output_path.read_text(encoding="utf-8")
