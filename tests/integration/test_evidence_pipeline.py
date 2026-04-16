import json
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import main as app_main
from tools import preprocess as preprocess_module


def test_load_preprocessed_snapshot_preserves_entity_profile(tmp_path: Path):
    path = tmp_path / "preprocessed_data.json"
    path.write_text(
        json.dumps(
            {
                "preprocessed_data": {
                    "run_config": {"product_code": "T70", "brand_name": "TOSBARRFT"},
                    "attribute_data": {"data": {"brand": "TOSBARRFT"}},
                    "core_selling_points": ["4K"],
                    "canonical_core_selling_points": ["4k recording"],
                    "accessory_descriptions": [],
                    "canonical_accessory_descriptions": [],
                    "quality_score": 88,
                    "language": "German",
                    "target_country": "DE",
                    "asin_entity_profile": {
                        "product_code": "T70",
                        "claim_registry": [{"claim": "150 minute runtime"}],
                    },
                },
                "keyword_data": {"keywords": []},
                "review_data": {"insights": []},
                "aba_data": {"trends": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = app_main.load_preprocessed_snapshot(str(path))

    assert loaded.asin_entity_profile["product_code"] == "T70"
    assert loaded.asin_entity_profile["claim_registry"][0]["claim"] == "150 minute runtime"


def test_run_step_0_persists_asin_entity_profile_artifact(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "DE",
                "brand_name": "TOSBARRFT",
                "product_code": "T70",
                "input_files": {},
                "llm": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main.AmazonListingGenerator, "_initialize_runtime", lambda self: None)

    def _fake_preprocess(**kwargs):
        output_path = kwargs["output_path"]
        Path(output_path).write_text(json.dumps({"preprocessed_data": {}}, ensure_ascii=False), encoding="utf-8")
        return SimpleNamespace(
            quality_score=92,
            core_selling_points=["4K recording"],
            language="German",
            asin_entity_profile={"product_code": "T70", "claim_registry": [{"claim": "4k recording"}]},
        )

    monkeypatch.setattr(preprocess_module, "preprocess_data", _fake_preprocess)

    generator = app_main.AmazonListingGenerator(str(config_path), str(tmp_path / "output"))
    result = generator.run_step_0()

    entity_profile_path = tmp_path / "output" / "asin_entity_profile.json"
    assert result["status"] == "success"
    assert entity_profile_path.exists()
    payload = json.loads(entity_profile_path.read_text(encoding="utf-8"))
    assert payload["product_code"] == "T70"


def test_generator_init_allows_degraded_live_healthcheck(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "US",
                "brand_name": "TOSBARRFT",
                "product_code": "SMOKE",
                "input_files": {},
                "llm": {"force_live_llm": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _LiveButDegradedClient:
        is_offline = False

        def healthcheck(self):
            return {
                "ok": False,
                "degraded_ok": True,
                "error": "missing_output_text",
                "provider": "openai_compatible",
            }

    monkeypatch.setattr(app_main, "get_llm_client", lambda: _LiveButDegradedClient())
    monkeypatch.setattr(app_main, "configure_llm_runtime", lambda *_args, **_kwargs: None)

    generator = app_main.AmazonListingGenerator(str(config_path), str(tmp_path / "output"))

    assert generator._runtime_healthcheck["degraded_ok"] is True


def test_run_step_6_persists_sidecar_artifacts(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "US",
                "brand_name": "TOSBARRFT",
                "product_code": "SMOKE",
                "input_files": {},
                "llm": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _FakeLiveClient:
        provider_label = "openai_compatible"
        mode_label = "live"
        response_metadata = {}

    monkeypatch.setattr(app_main.AmazonListingGenerator, "_initialize_runtime", lambda self: None)
    monkeypatch.setattr(app_main, "get_llm_client", lambda: _FakeLiveClient())

    monkeypatch.setattr(
        app_main.copy_generation,
        "generate_listing_copy",
        lambda **kwargs: {
            "title": "Test title",
            "bullets": ["B1"],
            "description": "Description",
            "faq": [],
            "search_terms": [],
            "metadata": {"generation_status": "live_with_fallback"},
            "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
            "compute_tier_map": {"title": {"tier_used": "native", "rerun_recommended": False}},
        },
    )

    generator = app_main.AmazonListingGenerator(str(config_path), str(tmp_path / "output"))
    generator.preprocessed_data = SimpleNamespace(
        language="English",
        run_config=SimpleNamespace(brand_name="TOSBARRFT"),
        attribute_data=SimpleNamespace(data={}),
    )
    generator.writing_policy = {"target_language": "English"}

    result = generator.run_step_6()

    assert result["status"] == "success"
    assert (tmp_path / "output" / "generated_copy.json").exists()
    assert (tmp_path / "output" / "evidence_bundle.json").exists()
    assert (tmp_path / "output" / "compute_tier_map.json").exists()
    repair_log_path = tmp_path / "output" / "repair_log.jsonl"
    repair_summary_path = tmp_path / "output" / "repair_summary.json"
    assert repair_log_path.exists()
    assert repair_summary_path.exists()
    assert isinstance(json.loads(repair_summary_path.read_text(encoding="utf-8")), dict)


def test_run_step_8_uses_scoring_max_total_in_console_output(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "US",
                "brand_name": "TOSBARRFT",
                "product_code": "SMOKE",
                "input_files": {},
                "llm": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main.AmazonListingGenerator, "_initialize_runtime", lambda self: None)
    monkeypatch.setattr(
        app_main.scoring,
        "calculate_scores",
        lambda **kwargs: {
            "a10_score": 70,
            "cosmo_score": 80,
            "rufus_score": 90,
            "price_competitiveness": {"score": None},
            "total_score": 240,
            "max_total": 300,
            "grade": "良好",
        },
    )

    generator = app_main.AmazonListingGenerator(str(config_path), str(tmp_path / "output"))
    generator.generated_copy = {"metadata": {}}
    generator.writing_policy = {"market_pack": {"locale": "US"}}
    generator.preprocessed_data = SimpleNamespace()
    generator.risk_report = {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}}

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = generator.run_step_8()

    assert result["status"] == "success"
    assert "总分: 240/300" in buffer.getvalue()


def test_run_step_7_persists_input_validation_into_risk_report(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "US",
                "brand_name": "TOSBARRFT",
                "product_code": "SMOKE",
                "input_files": {},
                "llm": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main.AmazonListingGenerator, "_initialize_runtime", lambda self: None)
    monkeypatch.setattr(
        app_main.risk_check,
        "perform_risk_check",
        lambda **kwargs: {
            "compliance": {"passed": 1, "total": 1, "issues": []},
            "policy_audit": {"passed": 1, "total": 1, "issues": []},
            "hallucination_risk": {"passed": 1, "total": 1, "issues": []},
            "overall_passed": True,
        },
    )

    generator = app_main.AmazonListingGenerator(str(config_path), str(tmp_path / "output"))
    generator.generated_copy = {"metadata": {"generation_status": "live_success"}}
    generator.writing_policy = {"target_language": "English"}
    generator.preprocessed_data = SimpleNamespace(attribute_data=SimpleNamespace(data={}), capability_constraints={})
    generator.input_validation_warnings = [
        {"table": "keyword_table", "severity": "high", "message": "keyword_table 缺少必填列：['search_volume']"}
    ]

    result = generator.run_step_7()

    assert result["status"] == "success"
    risk = json.loads((tmp_path / "output" / "risk_report.json").read_text(encoding="utf-8"))
    assert "input_validation" in risk
    assert risk["input_validation"]["issues"][0]["table"] == "keyword_table"


def test_run_step_9_writes_readiness_summary(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "US",
                "brand_name": "TOSBARRFT",
                "product_code": "SMOKE",
                "input_files": {},
                "llm": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main.AmazonListingGenerator, "_initialize_runtime", lambda self: None)
    monkeypatch.setattr(app_main.report_generator, "generate_report", lambda **kwargs: "# Full Report")
    monkeypatch.setattr(app_main.report_generator, "generate_action_items", lambda **kwargs: [])

    generator = app_main.AmazonListingGenerator(str(config_path), str(tmp_path / "output"))
    generator.preprocessed_data = SimpleNamespace(
        processed_at="2026-04-15",
        language="English",
        run_config=SimpleNamespace(target_country="US", product_code="SMOKE"),
    )
    generator.generated_copy = {
        "title": "Test title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "search_terms": ["body camera"],
        "metadata": {"generation_status": "live_success"},
    }
    generator.risk_report = {"review_queue": []}
    generator.scoring_results = {
        "listing_status": "READY_FOR_LISTING",
        "dimensions": {
            "traffic": {"label": "A10", "score": 100, "max": 100, "status": "pass"},
            "content": {"label": "COSMO", "score": 100, "max": 100, "status": "pass"},
            "conversion": {"label": "Rufus", "score": 100, "max": 100, "status": "pass"},
            "readability": {"label": "Fluency", "score": 30, "max": 30, "status": "pass"},
        },
        "action_required": "",
    }
    generator.writing_policy = {}
    generator.intent_graph = {}

    result = generator.run_step_9()

    assert result["status"] == "success"
    summary_path = tmp_path / "output" / "readiness_summary.md"
    assert summary_path.exists()
    assert "READY_FOR_LISTING" in summary_path.read_text(encoding="utf-8")


def test_run_step_9_loads_risk_report_from_disk(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "run_config.json"
    config_path.write_text(
        json.dumps(
            {
                "target_country": "US",
                "brand_name": "TOSBARRFT",
                "product_code": "SMOKE",
                "input_files": {},
                "llm": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main.AmazonListingGenerator, "_initialize_runtime", lambda self: None)
    monkeypatch.setattr(app_main.report_generator, "generate_report", lambda **kwargs: "# Full Report")
    monkeypatch.setattr(app_main.report_generator, "generate_action_items", lambda **kwargs: [])

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "risk_report.json").write_text(json.dumps({"review_queue": []}), encoding="utf-8")

    generator = app_main.AmazonListingGenerator(str(config_path), str(output_dir))
    generator.preprocessed_data = SimpleNamespace(
        processed_at="2026-04-15",
        language="English",
        run_config=SimpleNamespace(target_country="US", product_code="SMOKE"),
    )
    generator.generated_copy = {
        "title": "Test title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "search_terms": ["body camera"],
        "metadata": {"generation_status": "live_success"},
    }
    generator.scoring_results = {
        "listing_status": "READY_FOR_LISTING",
        "dimensions": {
            "traffic": {"label": "A10", "score": 100, "max": 100, "status": "pass"},
            "content": {"label": "COSMO", "score": 100, "max": 100, "status": "pass"},
            "conversion": {"label": "Rufus", "score": 100, "max": 100, "status": "pass"},
            "readability": {"label": "Fluency", "score": 30, "max": 30, "status": "pass"},
        },
        "action_required": "",
    }
    generator.writing_policy = {}
    generator.intent_graph = {}
    generator.risk_report = None

    result = generator.run_step_9()

    assert result["status"] == "success"
    assert generator.risk_report == {"review_queue": []}
