import pytest
from types import SimpleNamespace

from modules import copy_generation as cg


@pytest.fixture(autouse=True)
def disable_translator(monkeypatch):
    """Ensure tests exercise the rule-based path without hitting external APIs."""
    monkeypatch.setattr(cg, "_get_external_translator", lambda locale: None)


def _localize(text: str) -> str:
    return cg._localize_text_block(text, "French", "fr", ["TOSBARRFT"], [], "title")


@pytest.mark.parametrize(
    "source, expected",
    [
        ("30米", "30 m"),
        ("150分钟", "150 minutes"),
        ("12个月", "12 mois"),
        ("1.5公斤", "1.5 kg"),
    ],
)
def test_localize_replaces_zh_units(source, expected):
    localized = _localize(source)
    assert expected in localized


def test_localize_mixed_sentence_replaces_multiple_units():
    text = "防水深度30米，续航150分钟"
    localized = _localize(text)
    assert "30 m" in localized
    assert "150 minutes" in localized


def test_localize_preserves_brands_and_resolves_snake_case(monkeypatch):
    sample = "GoPro cycling_recording 30米"
    localized = _localize(sample)
    assert "GoPro" in localized  # brand should remain untouched
    assert "30 m" in localized
    assert "cycling_recording" not in localized
    assert "_" not in localized


def test_finalize_visible_text_removes_duplicate_phrases_and_dangling_connectors():
    cleaned = cg._finalize_visible_text(
        "camera sport caméra sport avec support guidon ou ,",
        "title",
        "French",
        audit_log=[],
    )
    assert cleaned == "camera sport avec support guidon,"


def test_should_run_localization_pass_skips_native_live_french_copy():
    text = "Caméra sport compacte avec WiFi et double écran pour filmer facilement vos sorties."
    assert cg._should_run_localization_pass(text, "French", llm_offline=False) is False


def test_should_run_localization_pass_detects_english_residue_in_non_english_copy():
    text = "## Brand Story Open the kit and find waterproof housing with quick-start guide ready for action."
    assert cg._should_run_localization_pass(text, "French", llm_offline=False) is True


def test_translate_capability_uses_canonical_locale_fallback():
    assert cg._translate_capability("easy operation", "French") == "utilisation simple"
    assert cg._translate_capability("high definition", "French") == "haute definition"
    assert cg._translate_capability("lightweight design", "French") == "design leger"


def test_french_bullet_binding_accepts_localized_capability_anchor():
    anchors = cg._build_localized_capability_anchors(
        ["easy operation", "long battery", "high definition"],
        "French",
    )
    payload = {
        "slot": "B2",
        "mandatory_keywords": [],
        "numeric_proof": "125 min",
        "localized_scene_anchors": ["trajets a velo"],
        "localized_capability_anchors": anchors,
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": True,
                "require_numeric_or_condition_slots": ["B2"],
                "condition_markers": [],
            },
        },
    }
    text = (
        "1080P EIS TRAJETS FLUIDES — Haute definition pour trajets a velo, "
        "jusqu'a 125 min en 1080P30 avec un usage simple au quotidien."
    )

    ok, reason = cg._bullet_candidate_meets_constraints(text, payload)

    assert ok, reason


def test_bullet_constraints_reject_fluency_header_preposition():
    payload = {
        "slot": "B5",
        "mandatory_keywords": ["body camera with audio"],
        "numeric_proof": "150 minutes",
        "localized_scene_anchors": ["commute"],
        "localized_capability_anchors": ["easy operation"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": False,
                "require_numeric_or_condition_slots": [],
                "condition_markers": [],
            },
        },
    }
    text = (
        "BODY CAMERA WITH — Document travel using a body camera with audio, easy operation, "
        "150 minutes so every clip feels ready to share."
    )

    ok, reason = cg._bullet_candidate_meets_constraints(text, payload)

    assert not ok
    assert reason.get("fluency_header_trailing_preposition") == "with"


def test_bullet_constraints_reject_lowercase_dash_tail_noun_phrase():
    payload = {
        "slot": "B3",
        "mandatory_keywords": ["thumb camera", "pov camera"],
        "numeric_proof": "150 minutes",
        "localized_scene_anchors": ["training"],
        "localized_capability_anchors": ["easy operation"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": False,
                "require_numeric_or_condition_slots": [],
                "condition_markers": [],
            },
        },
    }
    text = (
        "THUMB CAMERA SMOOTH CONTROL — Record training with thumb camera, easy operation, "
        "150 minutes so every clip feels ready to share – pov camera."
    )

    ok, reason = cg._bullet_candidate_meets_constraints(text, payload)

    assert not ok
    assert reason.get("fluency_dash_tail_without_predicate") is True


def test_english_capability_anchor_builder_expands_aliases():
    anchors = cg._build_localized_capability_anchors(
        ["long battery", "high definition"],
        "English",
    )

    assert "battery" in anchors
    assert "1080p" in [anchor.lower() for anchor in anchors]


def test_guarantee_mandatory_keywords_uses_sentence_not_dash_tail():
    text = "THUMB CAMERA CONTROL — Capture rides with stable footage."
    updated = cg._guarantee_mandatory_keywords(text, ["pov camera"], "English")

    assert "Includes pov camera." in updated
    assert " — pov camera." not in updated


def test_guarantee_mandatory_keywords_skips_semantically_present_phrase():
    text = "CRISP 1080P BODY CAMERA AUDIO — Record every commute with clear AAC audio."
    updated = cg._guarantee_mandatory_keywords(text, ["body camera with audio"], "English")

    assert updated == text


def test_title_generation_patches_missing_keywords_before_fallback(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_title",
        lambda payload: "TOSBARRFT mini camera, 1080p, 150 minutes, body camera",
    )
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "l1_keywords": ["mini camera"],
        "numeric_specs": ["1080p", "150 minutes"],
        "copy_contracts": {},
        "exact_match_keywords": [],
        "assigned_keywords": ["body camera"],
        "scene_priority": ["commuting_capture"],
        "max_length": 150,
    }

    title = cg._generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=["travel camera"],
        max_retries=1,
    )

    assert "travel camera" in title
    assert any(
        entry.get("field") == "title"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") in {"patched_missing_keywords", "post_retry_patch"}
        for entry in audit_log
    )


def test_repair_bullet_deterministic_frontload_avoids_header_duplicate():
    candidate = "FEATHERLIGHT TRAVEL CAMERA — Weighs just 0.1kg for commute capture."
    repaired = cg._repair_bullet_candidate_deterministically(
        candidate,
        {"frontload_anchor_missing": ["travel camera", "thumb camera"]},
        {
            "mandatory_keywords": ["travel camera", "thumb camera"],
            "localized_capability_anchors": ["lightweight design"],
            "localized_scene_anchors": ["commute"],
            "target_language": "English",
        },
    )

    assert "— travel camera" not in repaired.lower()
    assert "thumb camera" in repaired.lower()


def test_title_generation_swaps_missing_keywords_when_append_would_overflow(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_title",
        lambda payload: (
            "TOSBARRFT mini camera, 1080p, 150 minutes, body camera for commuting capture, vlog creator use"
        ),
    )
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "l1_keywords": ["mini camera"],
        "numeric_specs": ["1080p", "150 minutes"],
        "copy_contracts": {},
        "exact_match_keywords": [],
        "assigned_keywords": ["body camera"],
        "scene_priority": ["commuting_capture"],
        "max_length": 100,
    }

    title = cg._generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=["travel camera"],
        max_retries=1,
    )

    assert "travel camera" in title
    assert len(title) <= 100
    assert any(
        entry.get("field") == "title"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "patched_missing_keywords"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "title" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_title_generation_uses_payload_scaffold_before_fallback(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_title",
        lambda payload: "TOSBARRFT compact creator gear for commuting capture",
    )
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["mini camera"],
        "assigned_keywords": ["body camera", "vlogging camera"],
        "numeric_specs": ["1080p", "150 minutes"],
        "copy_contracts": {},
        "exact_match_keywords": [],
        "scene_priority": ["commuting_capture"],
        "max_length": 150,
    }

    title = cg._generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=["mini camera", "vlogging camera"],
        max_retries=1,
    )

    lowered = title.lower()
    assert "mini camera" in lowered
    assert "vlogging camera" in lowered
    assert any(
        entry.get("field") == "title"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "deterministic_repair"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "title" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_title_generation_trims_overlength_candidate_before_fallback(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_title",
        lambda payload: (
            "TOSBARRFT mini camera, 1080p, 150 minutes, body camera for commuting capture, travel creator setup, compact daily clip rig"
        ),
    )
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["mini camera"],
        "assigned_keywords": ["body camera"],
        "numeric_specs": ["1080p", "150 minutes"],
        "copy_contracts": {},
        "exact_match_keywords": [],
        "scene_priority": ["commuting_capture"],
        "max_length": 90,
    }

    title = cg._generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=["mini camera", "body camera"],
        max_retries=1,
    )

    lowered = title.lower()
    assert len(title) <= 90
    assert "mini camera" in lowered
    assert "body camera" in lowered
    assert any(
        entry.get("field") == "title"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "trimmed_length_repair"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "title" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_title_generation_uses_coordinated_repair_for_missing_keywords_and_length(monkeypatch):
    calls = {"count": 0}

    def _fake_generate(payload):
        calls["count"] += 1
        if payload.get("repair_context"):
            return "TOSBARRFT mini camera, vlogging camera, 1080p, 150 minutes"
        return (
            "TOSBARRFT mini camera, 1080p, 150 minutes, body camera for commuting capture, "
            "travel creator setup, compact daily clip rig"
        )

    monkeypatch.setattr(cg, "_llm_generate_title", _fake_generate)
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["mini camera"],
        "assigned_keywords": ["body camera"],
        "numeric_specs": ["1080p", "150 minutes"],
        "copy_contracts": {},
        "exact_match_keywords": [],
        "scene_priority": ["commuting_capture"],
        "max_length": 70,
    }

    title = cg._generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=["mini camera", "vlogging camera"],
        max_retries=1,
    )

    lowered = title.lower()
    assert "mini camera" in lowered
    assert "vlogging camera" in lowered
    assert len(title) <= 70
    assert calls["count"] >= 1
    assert any(
        entry.get("field") == "title"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") in {"coordinated_repair", "trimmed_length_repair"}
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "title" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_title_retries_when_live_error_is_retryable(monkeypatch):
    attempts = {"count": 0}

    def _fake_generate(payload):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise cg.LLMClientUnavailable(
                "Live LLM request returned no usable text (missing_output_text).",
                error_code="missing_output_text",
                retryable=True,
            )
        return "TOSBARRFT mini camera, 1080p, 150 minutes, travel camera"

    monkeypatch.setattr(cg, "_llm_generate_title", _fake_generate)
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "l1_keywords": ["mini camera"],
        "numeric_specs": ["1080p", "150 minutes"],
        "copy_contracts": {},
        "exact_match_keywords": [],
        "assigned_keywords": ["travel camera"],
        "scene_priority": ["commuting_capture"],
        "max_length": 150,
    }

    title = cg._generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=["travel camera"],
        max_retries=2,
    )

    lowered = title.lower()
    assert title.startswith("TOSBARRFT")
    assert "travel camera" in lowered
    assert "1080p" in lowered
    assert "150" in lowered
    assert attempts["count"] == 2
    assert any(
        entry.get("field") == "title"
        and entry.get("action") == "llm_retry"
        and entry.get("reason") == "missing_output_text"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "title" and entry.get("action") == "llm_unavailable"
        for entry in audit_log
    )


class _FakeBudgetClient:
    provider_label = "openai_compatible"
    base_url = "https://api.gptclubapi.xyz/openai"
    has_codex_exec_fallback = True


class _OverrideCaptureClient:
    def __init__(self):
        self.calls = []

    def generate_text(self, system_prompt, payload, temperature=0.35, override_model=None):
        self.calls.append(("title", override_model, payload.get("_llm_override_model")))
        return "TOSBARRFT Action Camera for Daily Capture with 150 Minutes Runtime"

    def generate_bullet(self, system_prompt, payload, temperature=0.35, override_model=None):
        self.calls.append(("bullet", override_model, payload.get("_llm_override_model")))
        return '{"text":"READY TO RECORD — Capture every ride with stable 1080P footage and 150 minutes of runtime.","capability_mapping":["4K recording"]}'


def test_budget_constrained_runtime_reduces_retry_budget(monkeypatch):
    monkeypatch.setenv("LISTING_STRICT_BUDGET_RUNTIME", "1")
    monkeypatch.setattr(cg, "get_llm_client", lambda: _FakeBudgetClient())
    assert cg._is_budget_constrained_live_runtime() is True
    assert cg._llm_retry_budget(3) == 1


def test_llm_generate_title_passes_override_model_to_client(monkeypatch):
    client = _OverrideCaptureClient()
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    title = cg._llm_generate_title(
        {
            "brand_name": "TOSBARRFT",
            "target_language": "English",
            "primary_category": "Action Camera",
            "l1_keywords": ["action camera"],
            "assigned_keywords": ["body camera"],
            "exact_match_keywords": ["action camera"],
            "required_keywords": ["action camera", "body camera"],
            "numeric_specs": ["150 minutes"],
            "core_capability": "150 Minutes Runtime",
            "_llm_override_model": "deepseek-reasoner",
        }
    )

    assert title.startswith("TOSBARRFT")
    assert client.calls == [("title", "deepseek-reasoner", "deepseek-reasoner")]


def test_llm_generate_bullet_passes_override_model_to_client(monkeypatch):
    client = _OverrideCaptureClient()
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    bullet = cg._llm_generate_bullet(
        {
            "target_language": "English",
            "all_scenes": ["cycling_recording"],
            "all_capabilities": ["4K recording"],
            "mandatory_elements": [],
            "forbidden_visible_terms": [],
            "evidence_numeric_values": ["150 minutes"],
            "spec_dimension_target": "runtime",
            "spec_dimensions_used": [],
            "_llm_override_model": "deepseek-reasoner",
        }
    )

    assert "READY TO RECORD" in bullet
    assert client.calls == [("bullet", "deepseek-reasoner", "deepseek-reasoner")]


def test_aplus_short_circuits_to_fallback_on_budget_constrained_runtime(monkeypatch):
    monkeypatch.setenv("LISTING_STRICT_BUDGET_RUNTIME", "1")
    monkeypatch.setattr(cg, "get_llm_client", lambda: _FakeBudgetClient())
    monkeypatch.setattr(
        cg,
        "_llm_generate_aplus",
        lambda payload: pytest.fail("live A+ generation should be skipped on constrained runtime"),
    )
    audit_log = []
    payload = {
        "brand_name": "TOSBARRFT",
        "target_language": "English",
        "product_profile": {
            "core_capabilities": ["4K recording", "dual screen"],
            "scene_priority": ["travel_documentation", "cycling_recording"],
        },
        "capability_scene_bindings": [],
        "accessories": ["mount kit", "waterproof housing"],
    }

    text = cg._generate_and_audit_aplus(payload, audit_log)

    assert payload.get("_aplus_fallback") is True
    assert "##" in text
    assert any(
        entry.get("field") == "aplus_content"
        and entry.get("action") == "llm_fallback"
        and entry.get("reason") == "runtime_budget_preserve_core_copy"
        for entry in audit_log
    )


def test_title_fallback_trims_at_word_boundary():
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["action camera 4k"],
        "assigned_keywords": ["bike camera"],
        "core_capability": "150-Minute Runtime",
        "scene_priority": ["cycling_recording", "underwater_exploration"],
        "mandatory_keywords": ["action camera 4k", "bike camera"],
        "exact_match_keywords": ["action camera 4k", "bike camera", "helmet camera"],
    }

    text = cg._fallback_text_for_field("title", payload, ["4K 60FPS", "150-Minute Runtime"])

    assert len(text) <= 150
    assert text.startswith("TOSBARRFT")
    assert "action camera 4k" in text
    assert "bike camera" in text
    assert not text.endswith("bike ca")


def test_ensure_core_category_keyword_frontloads_title():
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["mini camera"],
        "scene_priority": ["cycling_recording"],
        "target_language": "English",
    }
    title = "TOSBARRFT Mini Camera for Travel Documentation, 1080P, WiFi Preview, 150 Minutes Runtime"

    frontloaded = cg._ensure_title_core_category_frontload(title, payload)

    assert "action camera" in frontloaded[:80].lower()
    assert frontloaded.startswith("TOSBARRFT")


def test_dedupe_exact_phrase_occurrences_keeps_first_exact_match():
    text = "TOSBARRFT bike camera action camera 4k, 150 Minutes Runtime, bike camera, helmet camera"
    cleaned = cg._dedupe_exact_phrase_occurrences(text, ["bike camera", "action camera 4k", "helmet camera"])

    assert cleaned.count("bike camera") == 1
    assert "action camera 4k" in cleaned


def test_finalize_visible_text_scrubs_absolute_claims():
    audit_log = []
    cleaned = cg._finalize_visible_text(
        "#1 best camera with guaranteed results for the best viewing experience",
        "description",
        "English",
        audit_log=audit_log,
    )

    lowered = cleaned.lower()
    assert "#1" not in cleaned
    assert "best" not in lowered
    assert "guaranteed" not in lowered
    assert any(
        entry.get("field") == "description"
        and entry.get("action") == "downgrade"
        for entry in audit_log
    )


def test_infer_spec_dimensions_detects_multiple_supported_dimensions():
    text = (
        "Record up to 150 minutes in 1080P, keep carry weight near 0.1 kg, "
        "capture wide angle scenes with WiFi transfer and 30 m waterproof support."
    )

    dimensions = cg._infer_spec_dimensions(text)

    assert {"runtime", "resolution", "weight", "view_angle", "waterproof", "connectivity"} <= set(dimensions)


def test_select_slot_spec_dimension_prefers_unused_dimension_from_bundle():
    slot_dimension = cg._select_slot_spec_dimension(
        slot_name="B3",
        capability="long battery runtime",
        capability_bundle=["long battery runtime", "lightweight design"],
        used_dimensions={"runtime", "resolution"},
    )

    assert slot_dimension == "weight"


def test_finalize_visible_text_strips_visual_brief_metadata():
    cleaned = cg._finalize_visible_text(
        (
            "## Brand Story\n"
            "[Visual Design Brief: Split-screen diagram vs. footage with text on the right.]\n"
            "```json\n"
            "{\"section\":\"Brand Story\",\"subject\":\"Diagram vs. footage\",\"text_placement\":\"right\"}\n"
            "```\n"
            "TOSBARRFT keeps every commute covered."
        ),
        "aplus_content",
        "English",
        audit_log=[],
    )

    assert "[Visual Design Brief:" not in cleaned
    assert "```json" not in cleaned
    assert "\"section\"" not in cleaned
    assert "vs." not in cleaned
    assert "TOSBARRFT keeps every commute covered." in cleaned


def test_extract_bullet_text_from_response_parses_code_fenced_json():
    payload = {}

    bullet = cg._extract_bullet_text_from_response(
        '```json\n{"text":"LONG BATTERY LIFE — Capture up to 150 minutes.","capability_mapping":["long battery"]}\n```',
        payload,
    )

    assert bullet == "LONG BATTERY LIFE — Capture up to 150 minutes."
    assert payload["_capability_mapping_result"] == ["long battery"]


def test_compose_exact_match_title_prioritizes_category_phrase(monkeypatch):
    monkeypatch.setattr(cg, "_format_scene_label", lambda scene_code, language: scene_code.replace("_", " ").title())
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "exact_match_keywords": ["bike camera", "action camera 4k", "helmet camera"],
        "numeric_specs": ["4K 60fps", "150-Minute Runtime"],
        "scene_priority": ["cycling_recording", "underwater_exploration"],
        "target_language": "English",
        "max_length": 150,
    }

    title = cg._compose_exact_match_title(payload)

    assert title.startswith("TOSBARRFT action camera 4k")
    assert "bike camera" in title
    assert "helmet camera" in title
    assert ", bike camera, helmet camera," not in title


def test_search_terms_density_fill_reaches_minimum_bytes():
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        capability_constraints={},
    )
    writing_policy = {
        "scene_priority": ["cycling_recording", "travel_documentation", "vlog_content_creation"],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
    }

    terms, trace = cg.generate_search_terms(
        preprocessed_data=preprocessed,
        writing_policy=writing_policy,
        title="TestBrand mini action camera for cycling and travel",
        bullets=["Hands-free travel clips", "Helmet POV capture"],
        description="Compact body camera for commuting, bike rides, and vlog recording.",
        language="English",
        tiered_keywords={"l1": [], "l2": [], "l3": []},
        keyword_slots={"search_terms": {"keywords": []}},
        audit_log=[],
        assignment_tracker=None,
    )

    assert trace["byte_length"] >= 150
    assert len(terms) >= 5


def test_search_terms_prioritize_backend_longtail_and_avoid_title_front_repeat():
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        capability_constraints={},
        core_selling_points=["wearable camera", "long battery life"],
    )
    tiered_keywords = {
        "l1": ["body camera"],
        "l2": ["travel camera"],
        "l3": [],
        "_metadata": {
            "chest camera": {"keyword": "chest camera", "tier": "L3", "source_type": "synthetic", "search_volume": 11889.0},
            "thumb action camera": {"keyword": "thumb action camera", "tier": "L3", "source_type": "synthetic", "search_volume": 4248.0},
            "small action camera": {"keyword": "small action camera", "tier": "L3", "source_type": "synthetic", "search_volume": 1548.0},
            "body mounted video cameras": {"keyword": "body mounted video cameras", "tier": "L3", "source_type": "synthetic", "search_volume": 2408.0},
            "travel vlog camera": {"keyword": "travel vlog camera", "tier": "L3", "source_type": "synthetic", "search_volume": 1800.0},
            "cycling action camera": {"keyword": "cycling action camera", "tier": "L3", "source_type": "synthetic", "search_volume": 1600.0},
            "compact vlog camera": {"keyword": "compact vlog camera", "tier": "L3", "source_type": "synthetic", "search_volume": 1700.0},
            "wearable action camera": {"keyword": "wearable action camera", "tier": "L3", "source_type": "synthetic", "search_volume": 1750.0},
            "mini action camera for cycling": {"keyword": "mini action camera for cycling", "tier": "L3", "source_type": "synthetic", "search_volume": 1200.0},
        },
        "_preferred_locale": "en",
    }
    writing_policy = {
        "scene_priority": ["cycling_recording", "travel_documentation", "vlog_content_creation"],
        "search_term_plan": {
            "backend_only_terms": [],
            "backend_longtail_keywords": [
                "mini action camera for cycling",
                "chest camera",
                "thumb action camera",
                "small action camera",
                "body mounted video cameras",
                "travel vlog camera",
                "cycling action camera",
                "compact vlog camera",
                "wearable action camera",
            ],
            "max_bytes": 249,
            "priority_tiers": ["l3"],
        },
        "keyword_slots": {"search_terms": {"keywords": ["mini action camera for cycling"]}},
    }
    assignment_tracker = cg.KeywordAssignmentTracker(tiered_keywords["_metadata"])

    terms, trace = cg.generate_search_terms(
        preprocessed_data=preprocessed,
        writing_policy=writing_policy,
        title="Mini action camera for cycling travel vlogs and commutes",
        bullets=["Hands-free POV clips for travel."],
        description="Compact clip-on camera for commuting rides and trip recording.",
        language="English",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
        audit_log=[],
        assignment_tracker=assignment_tracker,
    )

    assert "mini action camera for cycling" not in terms
    assert "chest camera" in terms
    assert "thumb action camera" in terms
    assert "small action camera" in terms
    assert trace["byte_length"] >= 200
    assert trace["byte_length"] <= 249
    assignments = assignment_tracker.as_list()
    assert any(row["keyword"] == "chest camera" and row["tier"] == "L3" and "search_terms" in row["assigned_fields"] for row in assignments)


def test_search_terms_pull_distinct_explicit_l3_keywords_from_policy_metadata():
    tracker = cg.KeywordAssignmentTracker(
        {
            "travel camera": {"keyword": "travel camera", "tier": "L2", "source_type": "keyword_table", "search_volume": 7000},
            "thumb camera": {"keyword": "thumb camera", "tier": "L2", "source_type": "keyword_table", "search_volume": 4600},
            "chest camera": {"keyword": "chest camera", "tier": "L3", "source_type": "synthetic", "search_volume": 11889},
            "thumb action camera": {"keyword": "thumb action camera", "tier": "L3", "source_type": "synthetic", "search_volume": 4248},
            "body mounted video cameras": {"keyword": "body mounted video cameras", "tier": "L3", "source_type": "synthetic", "search_volume": 2408},
        }
    )
    tracker.record("title", ["travel camera"])
    tracker.record("bullet_3", ["thumb camera"])
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        capability_constraints={},
        core_selling_points=["wearable camera"],
    )
    tiered_keywords = {
        "l1": ["body camera"],
        "l2": ["travel camera", "thumb camera"],
        "l3": [],
        "_metadata": dict(tracker._metadata_map),
        "_preferred_locale": "en",
    }
    writing_policy = {
        "scene_priority": ["cycling_recording", "travel_documentation"],
        "search_term_plan": {
            "backend_only_terms": [],
            "backend_longtail_keywords": ["body camera with audio"],
            "max_bytes": 249,
            "priority_tiers": ["l3"],
        },
        "keyword_metadata": [
            {"keyword": "travel camera", "tier": "L3", "search_volume": 7737, "source_type": "synthetic"},
            {"keyword": "thumb camera", "tier": "L3", "search_volume": 4681, "source_type": "synthetic"},
            {"keyword": "chest camera", "tier": "L3", "search_volume": 11889, "source_type": "synthetic"},
            {"keyword": "thumb action camera", "tier": "L3", "search_volume": 4248, "source_type": "synthetic"},
            {"keyword": "body mounted video cameras", "tier": "L3", "search_volume": 2408, "source_type": "synthetic"},
        ],
        "keyword_slots": {"search_terms": {"keywords": []}},
    }

    terms, _ = cg.generate_search_terms(
        preprocessed_data=preprocessed,
        writing_policy=writing_policy,
        title="TestBrand travel camera for daily commutes",
        bullets=["Thumb camera clips for rides."],
        description="Body camera for trip capture.",
        language="English",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
        audit_log=[],
        assignment_tracker=tracker,
    )

    assert "chest camera" in terms
    assert "thumb action camera" in terms
    assert "body mounted video cameras" in terms
    records = {row["keyword"]: row for row in tracker.as_list()}
    assert records["travel camera"]["tier"] == "L2"
    assert records["thumb camera"]["tier"] == "L2"
    assert records["chest camera"]["tier"] == "L3"
    assert "search_terms" in records["chest camera"]["assigned_fields"]


def test_diversify_duplicate_bullet_dimensions_swaps_in_unused_capability():
    bullets = [
        "LIGHTWEIGHT CONTROL — Capture every commute with compact, lightweight handling.",
        "LIGHTWEIGHT EVERYDAY — Keep your travel clips easy to carry and easy to control.",
    ]
    bullet_trace = [
        {"slot": "B1", "scene_code": "cycling_recording", "capability": "lightweight design", "capability_mapping": ["lightweight design"]},
        {"slot": "B2", "scene_code": "travel_documentation", "capability": "lightweight design", "capability_mapping": ["lightweight design"]},
    ]
    diversified = cg._diversify_duplicate_bullet_dimensions(
        final_bullets=list(bullets),
        bullet_trace=bullet_trace,
        allowed_capabilities=["lightweight design", "long battery life", "dual screen"],
        slot_keyword_records={"B1": [], "B2": []},
        final_language="English",
        audit_log=[],
        attr_lookup={"battery_life": "150 minutes"},
        capability_constraints={"runtime_minutes": 150},
    )

    assert any("150 minutes" in bullet for bullet in diversified)
    assert diversified[1] != bullets[1]


def test_compose_exact_match_title_frames_secondary_keywords_more_naturally(monkeypatch):
    monkeypatch.setattr(cg, "_format_scene_label", lambda scene_code, language: scene_code.replace("_", " ").title())
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "exact_match_keywords": ["action camera 4k", "bike camera", "helmet camera"],
        "numeric_specs": ["150 minutes", "4K 60fps"],
        "scene_priority": ["cycling_recording", "travel_documentation"],
        "target_language": "English",
        "max_length": 150,
    }

    title = cg._compose_exact_match_title(payload)

    assert "bike camera for Cycling" in title
    assert "helmet camera for Helmet POV" in title
    assert "4K 60fps" in title


def test_dewater_title_preserves_exact_phrases():
    text = "TOSBARRFT action camera 4k, with 150-Minute Runtime, with bike camera, helmet camera"

    cleaned = cg._dewater_title_text(text, ["action camera 4k", "bike camera", "helmet camera"])

    assert "action camera 4k" in cleaned
    assert "bike camera" in cleaned
    assert cleaned.count("with") == 0


def test_scene_anchor_builder_prefers_natural_aliases_for_english():
    anchors = cg._build_localized_scene_anchors(["cycling_recording", "commuting_capture"], "English")

    assert "cycling" in [anchor.lower() for anchor in anchors]
    assert "commute" in " ".join(anchor.lower() for anchor in anchors)


def test_collect_bullet_quality_reasons_flags_dangling_tail_and_repeated_opener():
    reasons, opener = cg._collect_bullet_quality_reasons(
        "SMOOTH RIDES LONGER — Capture every route in 4K while WiFi and Bluetooth make.",
        "English",
        ["capture"],
    )

    assert opener == "capture"
    assert "unfinished_tail" in reasons
    assert "repetitive_opener:capture" in reasons


def test_generate_and_audit_bullet_repairs_missing_numeric_without_fallback(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_bullet",
        lambda payload: "LONG BATTERY LIFE — Capture rides with body camera with audio in a lightweight design.",
    )
    monkeypatch.setattr(
        cg,
        "_repair_bullet_candidate_with_llm",
        lambda candidate, failure_reason, payload: (
            "LONG BATTERY LIFE — Capture rides with body camera with audio in a lightweight design for up to 150 minutes."
        ),
    )
    audit_log = []
    payload = {
        "slot": "B2",
        "target_language": "English",
        "mandatory_keywords": ["body camera with audio"],
        "numeric_proof": "150 minutes",
        "localized_scene_anchors": ["rides"],
        "localized_capability_anchors": ["lightweight design"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": True,
                "require_numeric_or_condition_slots": ["B2"],
                "condition_markers": [],
            },
        },
    }

    bullet = cg._generate_and_audit_bullet(payload, audit_log, "B2")

    assert "150 minutes" in bullet
    assert any(
        entry.get("field") == "bullet_b2"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "repair_pass"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "bullet_b2" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_generate_and_audit_bullet_repairs_fluency_issue_without_fallback(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_bullet",
        lambda payload: (
            "BODY CAMERA WITH — Document travel using a body camera with audio, "
            "easy operation, 150 minutes so every clip feels ready to share."
        ),
    )
    monkeypatch.setattr(
        cg,
        "_repair_bullet_candidate_with_llm",
        lambda candidate, failure_reason, payload: (
            "BODY CAMERA CLARITY — Document travel with body camera with audio, "
            "easy operation, and up to 150 minutes runtime."
        ),
    )
    audit_log = []
    payload = {
        "slot": "B5",
        "target_language": "English",
        "mandatory_keywords": ["body camera with audio"],
        "numeric_proof": "150 minutes",
        "localized_scene_anchors": ["travel"],
        "localized_capability_anchors": ["easy operation"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": True,
                "require_numeric_or_condition_slots": ["B5"],
                "condition_markers": [],
            },
        },
    }

    bullet = cg._generate_and_audit_bullet(payload, audit_log, "B5")

    assert "BODY CAMERA CLARITY" in bullet
    assert "150 minutes" in bullet
    assert any(
        entry.get("field") == "bullet_b5"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "repair_pass"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "bullet_b5" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_generate_and_audit_bullet_accepts_code_fenced_json_repair(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_bullet",
        lambda payload: (
            '```json\n{"text":"THUMB CAMERA FOR TRAINING — Capture cycling sessions with easy operation.","capability_mapping":["easy operation"]}\n```'
        ),
    )
    monkeypatch.setattr(
        cg,
        "_repair_bullet_candidate_with_llm",
        lambda candidate, failure_reason, payload: (
            '```json\n{"text":"THUMB CAMERA FOR TRAINING — Capture cycling sessions with easy operation for up to 150 minutes.","capability_mapping":["easy operation"]}\n```'
        ),
    )
    audit_log = []
    payload = {
        "slot": "B3",
        "target_language": "English",
        "mandatory_keywords": ["thumb camera"],
        "numeric_proof": "150 minutes",
        "localized_scene_anchors": ["cycling"],
        "localized_capability_anchors": ["easy operation"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": True,
                "require_numeric_or_condition_slots": ["B3"],
                "condition_markers": [],
            },
        },
    }

    bullet = cg._generate_and_audit_bullet(payload, audit_log, "B3")

    assert bullet == "THUMB CAMERA FOR TRAINING — Capture cycling sessions with easy operation for up to 150 minutes."
    assert "```" not in bullet
    assert any(
        entry.get("field") == "bullet_b3"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "repair_pass"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "bullet_b3" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_generate_and_audit_bullet_uses_deterministic_frontload_repair_before_fallback(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_bullet",
        lambda payload: (
            "POV READY CLIP — Capture hands-free highlights for every workout, commute, and daily errand with dependable footage, thanks to easy operation on this compact body camera with audio."
        ),
    )
    monkeypatch.setattr(
        cg,
        "_repair_bullet_candidate_with_llm",
        lambda candidate, failure_reason, payload: candidate,
    )
    audit_log = []
    payload = {
        "slot": "B5",
        "target_language": "English",
        "mandatory_keywords": ["body camera with audio"],
        "numeric_proof": None,
        "localized_scene_anchors": ["sports"],
        "localized_capability_anchors": ["easy operation"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": True,
                "require_numeric_or_condition_slots": [],
                "condition_markers": [],
            },
        },
    }

    bullet = cg._generate_and_audit_bullet(payload, audit_log, "B5")

    assert "body camera with audio" in bullet.lower()
    assert any(
        entry.get("field") == "bullet_b5"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "deterministic_repair"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "bullet_b5" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


def test_generate_and_audit_bullet_uses_payload_scaffold_when_llm_contains_forbidden_term(monkeypatch):
    monkeypatch.setattr(
        cg,
        "_llm_generate_bullet",
        lambda payload: (
            "STABLE TRAVEL FOOTAGE — Use stabilization for every trip with smooth control."
        ),
    )
    monkeypatch.setattr(
        cg,
        "_repair_bullet_candidate_with_llm",
        lambda candidate, failure_reason, payload: candidate,
    )
    audit_log = []
    payload = {
        "slot": "B4",
        "target_language": "English",
        "mandatory_keywords": ["travel camera"],
        "forbidden_visible_terms": ["stabilization"],
        "numeric_proof": "1080P",
        "localized_scene_anchors": ["commute"],
        "localized_capability_anchors": ["high definition"],
        "copy_contracts": {
            "bullet_opening": {"header_required": True, "frontload_window_tokens": 16},
            "scene_capability_numeric_binding": {
                "require_scene_and_capability": True,
                "require_numeric_or_condition_slots": [],
                "condition_markers": [],
            },
        },
    }

    bullet = cg._generate_and_audit_bullet(payload, audit_log, "B4")

    assert "travel camera" in bullet.lower()
    assert "stabilization" not in bullet.lower()
    assert any(
        entry.get("field") == "bullet_b4"
        and entry.get("action") == "llm_success"
        and entry.get("attempt") == "deterministic_repair"
        for entry in audit_log
    )
    assert not any(
        entry.get("field") == "bullet_b4" and entry.get("action") == "llm_fallback"
        for entry in audit_log
    )


class _FakeOfflineClient:
    active_model = "offline"
    provider_label = "offline"
    mode_label = "offline"
    credential_source = "none"
    wire_api = "chat/completions"
    base_url = ""
    is_offline = True
    response_metadata = {}
    healthcheck_status = {}


def test_generate_listing_copy_can_resume_from_stage_artifacts(monkeypatch, tmp_path):
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand", product_name="Cam", category="Action Camera"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        core_selling_points=["4K recording"],
        canonical_core_selling_points=["4K recording"],
        accessory_descriptions=[],
        canonical_accessory_descriptions=[],
        canonical_capability_notes={},
        quality_score=80,
        language="English",
        processed_at="2026-04-13T00:00:00",
        data_mode="SYNTHETIC_COLD_START",
        capability_constraints={},
        raw_human_insights="",
        keyword_metadata=[],
        feedback_context={},
        real_vocab=None,
    )
    policy = {
        "scene_priority": ["cycling_recording", "travel_documentation"],
        "keyword_allocation_strategy": "balanced",
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {"backend_only_terms": []},
        "search_term_plan": {"backend_only_terms": []},
        "product_profile": {"reasoning_language": "EN"},
    }
    monkeypatch.setattr(cg, "get_llm_client", lambda: _FakeOfflineClient())
    monkeypatch.setattr(
        cg,
        "extract_tiered_keywords",
        lambda *_args, **_kwargs: {
            "l1": ["action camera 4k"],
            "l2": ["bike camera"],
            "l3": ["travel camera"],
            "_metadata": {},
            "_preferred_locale": "en",
        },
    )
    monkeypatch.setattr(cg, "build_keyword_slots", lambda *_args, **_kwargs: {"search_terms": {"keywords": []}})

    counts = {"title": 0, "bullets": 0, "description": 0, "faq": 0, "search_terms": 0, "aplus": 0}

    monkeypatch.setattr(cg, "generate_title", lambda *args, **kwargs: counts.__setitem__("title", counts["title"] + 1) or "TestBrand action camera 4k")
    monkeypatch.setattr(
        cg,
        "generate_bullet_points",
        lambda *args, **kwargs: counts.__setitem__("bullets", counts["bullets"] + 1)
        or (
            [f"HEADER — Reasoning {kwargs.get('slot_filter', ['B1'])[0]}."],
            [{"slot": kwargs.get("slot_filter", ["B1"])[0], "keywords": ["bike camera"], "scene_mapping": [], "capability_bundle": [], "capability": "", "numeric_source": None}],
            [f"HEADER — Bullet {kwargs.get('slot_filter', ['B1'])[0]} text."],
        ),
    )
    monkeypatch.setattr(cg, "generate_description", lambda *args, **kwargs: counts.__setitem__("description", counts["description"] + 1) or "Description text.")
    monkeypatch.setattr(cg, "generate_faq", lambda *args, **kwargs: counts.__setitem__("faq", counts["faq"] + 1) or [{"q": "Q", "a": "A"}])
    monkeypatch.setattr(
        cg,
        "generate_search_terms",
        lambda *args, **kwargs: counts.__setitem__("search_terms", counts["search_terms"] + 1) or (["travel camera"], {"byte_length": 12, "max_bytes": 249, "backend_only_used": 0}),
    )
    monkeypatch.setattr(
        cg,
        "generate_aplus_content",
        lambda *args, **kwargs: counts.__setitem__("aplus", counts["aplus"] + 1) or ("## A+\nBody", True, []),
    )

    artifact_dir = tmp_path / "artifacts"
    first = cg.generate_listing_copy(preprocessed, policy, language="English", artifact_dir=str(artifact_dir), resume_existing=True)
    assert first["title"] == "TestBrand action camera 4k"
    assert counts == {"title": 1, "bullets": 5, "description": 1, "faq": 1, "search_terms": 1, "aplus": 1}
    assert (artifact_dir / "title.json").exists()
    assert (artifact_dir / "bullet_b1.json").exists()
    assert (artifact_dir / "bullet_b5.json").exists()
    assert (artifact_dir / "partial_generated_copy.json").exists()

    monkeypatch.setattr(cg, "generate_title", lambda *args, **kwargs: pytest.fail("title should resume from artifact"))
    monkeypatch.setattr(cg, "generate_bullet_points", lambda *args, **kwargs: pytest.fail("bullets should resume from artifact"))
    monkeypatch.setattr(cg, "generate_description", lambda *args, **kwargs: pytest.fail("description should resume from artifact"))
    monkeypatch.setattr(cg, "generate_faq", lambda *args, **kwargs: pytest.fail("faq should resume from artifact"))
    monkeypatch.setattr(cg, "generate_search_terms", lambda *args, **kwargs: pytest.fail("search_terms should resume from artifact"))
    monkeypatch.setattr(cg, "generate_aplus_content", lambda *args, **kwargs: pytest.fail("aplus should resume from artifact"))

    second = cg.generate_listing_copy(preprocessed, policy, language="English", artifact_dir=str(artifact_dir), resume_existing=True)
    assert second["title"] == "TestBrand action camera 4k"
    assert second["metadata"]["field_generation_trace"]["title"]["status"] == "resumed"
    assert second["metadata"]["field_generation_trace"]["bullet_b1"]["status"] == "resumed"
    assert second["metadata"]["field_generation_trace"]["aplus"]["status"] == "resumed"


def test_generate_listing_copy_attaches_evidence_bundle(monkeypatch):
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand", product_name="Cam", category="Action Camera"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        core_selling_points=["4K recording"],
        canonical_core_selling_points=["4K recording"],
        accessory_descriptions=[],
        canonical_accessory_descriptions=[],
        canonical_capability_notes={},
        quality_score=80,
        language="English",
        processed_at="2026-04-13T00:00:00",
        data_mode="SYNTHETIC_COLD_START",
        capability_constraints={},
        raw_human_insights="",
        keyword_metadata=[],
        feedback_context={},
        real_vocab=None,
        asin_entity_profile={"product_code": "T70", "claim_registry": [{"claim": "150 minute runtime"}]},
    )
    policy = {
        "scene_priority": ["cycling_recording"],
        "keyword_allocation_strategy": "balanced",
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {"backend_only_terms": []},
        "search_term_plan": {"backend_only_terms": []},
        "product_profile": {"reasoning_language": "EN"},
    }
    monkeypatch.setattr(cg, "get_llm_client", lambda: _FakeOfflineClient())
    monkeypatch.setattr(
        cg,
        "extract_tiered_keywords",
        lambda *_args, **_kwargs: {"l1": [], "l2": [], "l3": [], "_metadata": {}, "_preferred_locale": "en"},
    )
    monkeypatch.setattr(cg, "build_keyword_slots", lambda *_args, **_kwargs: {"search_terms": {"keywords": []}})
    monkeypatch.setattr(cg, "generate_title", lambda *args, **kwargs: "TestBrand action camera")
    monkeypatch.setattr(
        cg,
        "generate_bullet_points",
        lambda *args, **kwargs: (
            [f"HEADER — Reasoning {kwargs.get('slot_filter', ['B1'])[0]}."],
            [{"slot": kwargs.get("slot_filter", ["B1"])[0], "keywords": [], "scene_mapping": [], "capability_bundle": [], "capability": "", "numeric_source": None}],
            [f"HEADER — Bullet {kwargs.get('slot_filter', ['B1'])[0]} text."],
        ),
    )
    monkeypatch.setattr(cg, "generate_description", lambda *args, **kwargs: "Description text.")
    monkeypatch.setattr(cg, "generate_faq", lambda *args, **kwargs: [{"q": "Q", "a": "A"}])
    monkeypatch.setattr(cg, "generate_search_terms", lambda *args, **kwargs: (["travel camera"], {"byte_length": 12, "max_bytes": 249, "backend_only_used": 0}))
    monkeypatch.setattr(cg, "generate_aplus_content", lambda *args, **kwargs: ("## A+\nBody", True, []))
    monkeypatch.setattr(
        cg,
        "build_evidence_bundle",
        lambda preprocessed_data, entity_profile: {
            "attribute_evidence": {},
            "review_positive_clusters": [],
            "review_negative_clusters": [],
            "qa_clusters": [],
            "claim_support_matrix": [{"claim": "150 minute runtime", "support_status": "supported"}],
            "rufus_readiness": {"score": 1.0, "supported_claim_count": 1, "total_claim_count": 1},
        },
    )

    result = cg.generate_listing_copy(preprocessed, policy, language="English")

    assert result["evidence_bundle"]["claim_support_matrix"][0]["support_status"] == "supported"
    assert result["metadata"]["unsupported_claim_count"] == 0


class _FakeLiveReasonerClient:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error
        self._meta = {}
        self._offline = False
        self.provider_label = "deepseek"
        self.mode_label = "live"
        self.credential_source = "env"
        self.active_model = "deepseek-chat"
        self.wire_api = "chat/completions"
        self.base_url = "https://api.deepseek.com/v1"

    @property
    def response_metadata(self):
        return dict(self._meta)

    @property
    def healthcheck_status(self):
        return {}

    def generate_text(self, system_prompt, payload, temperature=0.35, override_model=None):
        self._meta = {
            "configured_model": override_model or "deepseek-chat",
            "returned_model": override_model or "deepseek-chat",
            "success": self._error is None,
            "error": "" if self._error is None else str(self._error),
        }
        if self._error is not None:
            raise self._error
        return self._text


def _sample_preprocessed():
    return SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand", product_name="Cam", category="Action Camera"),
        attribute_data=SimpleNamespace(data={"battery_life": "150 minutes"}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        core_selling_points=["4K recording", "150-minute runtime"],
        canonical_core_selling_points=["4K recording", "150-minute runtime"],
        accessory_descriptions=[],
        canonical_accessory_descriptions=[],
        canonical_capability_notes={},
        quality_score=80,
        language="English",
        processed_at="2026-04-17T00:00:00",
        data_mode="SYNTHETIC_COLD_START",
        capability_constraints={},
        raw_human_insights="",
        keyword_metadata=[],
        feedback_context={},
        real_vocab=None,
        asin_entity_profile={},
    )


def _sample_policy():
    return {
        "scene_priority": ["cycling_recording", "travel_documentation"],
        "keyword_allocation_strategy": "balanced",
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {"backend_only_terms": []},
        "search_term_plan": {"backend_only_terms": []},
        "product_profile": {"reasoning_language": "EN"},
        "copy_contracts": {},
    }


def test_generate_listing_copy_uses_pure_r1_batch_for_visible_copy(monkeypatch):
    client = _FakeLiveReasonerClient(
        text=(
            '{"title":"TestBrand Action Camera for Daily Rides with 150-Minute Runtime",'
            '"bullets":['
            '"READY TO RIDE — Capture every commute with stable 1080P footage and 150 minutes of runtime.",'
            '"EVIDENCE READY — Clip on for work shifts when clear first-person recording matters.",'
            '"TRAVEL LIGHT — Slip the mini camera into a pocket for quick scenic clips.",'
            '"USE IT RIGHT — Best for walking, commuting, and steady handheld moments.",'
            '"VALUE KIT — Start fast with the included essentials for everyday recording."'
            "]}"
        )
    )
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)
    monkeypatch.setattr(
        cg,
        "extract_tiered_keywords",
        lambda *_args, **_kwargs: {
            "l1": ["action camera", "mini camera", "body camera"],
            "l2": ["bike camera"],
            "l3": ["travel camera"],
            "_metadata": {},
            "_preferred_locale": "en",
        },
    )
    monkeypatch.setattr(cg, "build_keyword_slots", lambda *_args, **_kwargs: {"search_terms": {"keywords": []}})
    monkeypatch.setattr(cg, "generate_title", lambda *args, **kwargs: pytest.fail("single-field title path should be skipped"))
    monkeypatch.setattr(cg, "generate_bullet_points", lambda *args, **kwargs: pytest.fail("single-field bullet path should be skipped"))
    monkeypatch.setattr(cg, "_polish_bullet_quality_with_llm", lambda *args, **kwargs: pytest.fail("pure R1 batch bullets should not be re-polished"))
    monkeypatch.setattr(cg, "generate_description", lambda *args, **kwargs: "Description text.")
    monkeypatch.setattr(cg, "generate_faq", lambda *args, **kwargs: [{"q": "Q", "a": "A"}])
    monkeypatch.setattr(cg, "generate_search_terms", lambda *args, **kwargs: (["travel camera"], {"byte_length": 12, "max_bytes": 249, "backend_only_used": 0}))
    monkeypatch.setattr(cg, "generate_aplus_content", lambda *args, **kwargs: ("## A+\nBody", True, []))
    monkeypatch.setattr(
        cg,
        "build_evidence_bundle",
        lambda *_args, **_kwargs: {
            "claim_support_matrix": [],
            "rufus_readiness": {"score": 1.0},
        },
    )

    result = cg.generate_listing_copy(
        _sample_preprocessed(),
        _sample_policy(),
        language="English",
        model_overrides={"title": "deepseek-reasoner", "bullets": "deepseek-reasoner"},
    )

    assert result["title"].startswith("TestBrand Action Camera")
    assert len(result["bullets"]) == 5
    assert result["metadata"]["generation_status"] == "live_success"
    assert result["metadata"]["llm_fallback_count"] == 0
    assert result["metadata"]["field_generation_trace"]["visible_copy_batch"]["status"] == "success"
    assert result["metadata"]["field_generation_trace"]["title"]["status"] == "success"
    assert result["metadata"]["field_generation_trace"]["bullet_b1"]["status"] == "success"


def test_generate_listing_copy_raises_when_pure_r1_batch_times_out(monkeypatch):
    client = _FakeLiveReasonerClient(
        error=cg.LLMClientUnavailable("r1 timeout", error_code="timed_out", retryable=True)
    )
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)
    monkeypatch.setattr(
        cg,
        "extract_tiered_keywords",
        lambda *_args, **_kwargs: {
            "l1": ["action camera", "mini camera", "body camera"],
            "l2": ["bike camera"],
            "l3": ["travel camera"],
            "_metadata": {},
            "_preferred_locale": "en",
        },
    )
    monkeypatch.setattr(cg, "build_keyword_slots", lambda *_args, **_kwargs: {"search_terms": {"keywords": []}})
    monkeypatch.setattr(cg, "generate_title", lambda *args, **kwargs: pytest.fail("fallback title path should stay disabled"))
    monkeypatch.setattr(cg, "generate_bullet_points", lambda *args, **kwargs: pytest.fail("fallback bullet path should stay disabled"))

    with pytest.raises(RuntimeError, match="R1 batch visible copy generation failed"):
        cg.generate_listing_copy(
            _sample_preprocessed(),
            _sample_policy(),
            language="English",
            model_overrides={"title": "deepseek-reasoner", "bullets": "deepseek-reasoner"},
        )


def test_generate_faq_uses_question_bank_context(monkeypatch):
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={"battery_life": "150 minutes"}),
        capability_constraints={},
        language="English",
    )
    writing_policy = {
        "compliance_directives": {},
        "faq_only_capabilities": [],
        "intent_graph": [],
        "question_bank_context": {
            "questions": [
                {
                    "topic": "battery_in_cold_weather",
                    "question": "Can it record reliably in cold outdoor conditions?",
                    "market": "DE",
                    "priority": "high",
                }
            ],
            "evidence_hints": ["150 minute runtime"],
        },
    }

    captured = {}

    def _fake_generate_and_audit(payload, fallback_entries, audit_log):
        captured["payload"] = payload
        captured["fallback_entries"] = fallback_entries
        return fallback_entries

    monkeypatch.setattr(cg, "_generate_and_audit_faq", _fake_generate_and_audit)

    faq = cg.generate_faq(preprocessed, writing_policy, language="English", audit_log=[])

    assert captured["payload"]["question_bank_context"]["questions"][0]["topic"] == "battery_in_cold_weather"
    assert faq[0]["q"] == "Can it record reliably in cold outdoor conditions?"


def test_bullet_fallback_rotates_template_shapes_by_slot():
    base_payload = {
        "target_language": "English",
        "mandatory_keywords": ["travel camera"],
        "capability": "easy operation",
        "localized_capability_anchors": ["easy operation"],
        "localized_scene_anchors": ["commute"],
        "scene_context": "commuting_capture",
    }

    bullet_b1 = cg._fallback_text_for_field("bullet_b1", {**base_payload, "slot": "B1"}, ["150 minutes"])
    bullet_b2 = cg._fallback_text_for_field("bullet_b2", {**base_payload, "slot": "B2"}, ["150 minutes"])
    bullet_b3 = cg._fallback_text_for_field("bullet_b3", {**base_payload, "slot": "B3"}, ["150 minutes"])

    assert bullet_b1 != bullet_b2 != bullet_b3
    assert "—" in bullet_b1 and "—" in bullet_b2 and "—" in bullet_b3
    assert not all("so every clip feels ready to share" in bullet for bullet in [bullet_b1, bullet_b2, bullet_b3])
