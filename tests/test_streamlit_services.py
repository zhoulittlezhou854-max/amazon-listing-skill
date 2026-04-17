import json
from pathlib import Path

from app.services import run_service, workspace_service


class _Upload:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self):
        return self._content


def test_initialize_workspace_creates_config_and_inputs(tmp_path: Path):
    result = workspace_service.initialize_workspace(
        product_code="T70",
        site="FR",
        brand_name="TOSBARRFT",
        files={
            "attribute_table": _Upload("attr.txt", b"video_resolution: 4K"),
            "keyword_table": _Upload("kw.csv", b"keyword,search_volume\nbody camera,1200\n"),
            "aba_merged": _Upload("aba.csv", b"keyword,search_volume\nbody camera,1200\n"),
            "review_table": _Upload("review.csv", b"field_name,content_text\nFeature_Praise,good\n"),
        },
        manual_notes="premium commuter product",
        workspace_root=str(tmp_path),
    )
    run_config = json.loads(Path(result["run_config_path"]).read_text(encoding="utf-8"))
    assert run_config["target_country"] == "FR"
    assert Path(run_config["input_files"]["attribute_table"]).exists()
    assert run_config["llm"]["provider"] == "deepseek"
    assert run_config["llm"]["model"] == "deepseek-chat"


def test_initialize_workspace_warns_when_custom_llm_differs_from_official_config(tmp_path: Path, monkeypatch):
    official_config = tmp_path / "config" / "run_configs"
    official_config.mkdir(parents=True, exist_ok=True)
    (official_config / "H91lite_US.json").write_text(
        json.dumps(
            {
                "llm": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key_env": "DEEPSEEK_API_KEY",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = workspace_service.initialize_workspace(
        product_code="H91lite",
        site="US",
        brand_name="TOSBARRFT",
        files={},
        workspace_root=str(tmp_path / "workspace"),
        llm_config={
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "api_key_env": "CRS_OAI_KEY",
        },
    )

    run_config = json.loads(Path(result["run_config_path"]).read_text(encoding="utf-8"))
    assert "does not match the official run config" in result["llm_alignment_warning"]
    assert "does not match the official run config" in run_config["llm_alignment_warning"]


def test_run_workspace_workflow_returns_failure_payload_when_runner_raises(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace" / "T70_FR"
    workspace.mkdir(parents=True)

    def _boom(config_path, output_dir, steps=None):
        raise RuntimeError("runner failed")

    monkeypatch.setattr(run_service, "run_generator_workflow", _boom)
    result = run_service.run_workspace_workflow("config.json", str(workspace), steps=[0])
    assert result["status"] == "RUN_FAILED"
    assert "runner failed" in result["error"]


def test_run_workspace_workflow_dual_version_returns_dual_report(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace" / "H91LITE_US"
    workspace.mkdir(parents=True)
    run_config = workspace / "run_config.json"
    run_config.write_text(
        json.dumps({"product_code": "H91lite", "target_country": "US"}),
        encoding="utf-8",
    )

    captured = []

    def _fake_run(
        config_path,
        output_dir,
        steps=None,
        blueprint_model_override=None,
        title_model_override=None,
        bullet_model_override=None,
    ):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        model = "deepseek-reasoner" if blueprint_model_override else "deepseek-chat"
        captured.append(
            {
                "blueprint": blueprint_model_override,
                "title": title_model_override,
                "bullets": bullet_model_override,
            }
        )
        (out / "generated_copy.json").write_text(
            json.dumps(
                {
                    "title": "Demo",
                    "bullets": ["B1", "B2", "B3", "B4", "B5"],
                    "description": "Desc",
                    "search_terms": ["t1"],
                    "metadata": {"generation_status": "live_success"},
                }
            ),
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            json.dumps(
                {
                    "listing_status": "READY_FOR_LISTING",
                    "dimensions": {
                        "traffic": {"score": 100},
                        "content": {"score": 100},
                        "conversion": {"score": 90 if not blueprint_model_override else 100},
                        "readability": {"score": 30},
                    },
                }
            ),
            encoding="utf-8",
        )
        (out / "risk_report.json").write_text(json.dumps({}), encoding="utf-8")
        if blueprint_model_override:
            (out / "bullet_blueprint.json").write_text(
                json.dumps({"llm_model": model}),
                encoding="utf-8",
            )
        return {
            "summary": {"workflow_status": "success"},
            "generated_copy": {},
            "risk_report": {},
            "scoring_results": {},
            "writing_policy": {},
            "preprocessed_data": None,
        }

    monkeypatch.setattr(run_service, "run_generator_workflow", _fake_run)
    monkeypatch.setattr(run_service, "snapshot_run_outputs", lambda *_args, **_kwargs: {})

    result = run_service.run_workspace_workflow(
        str(run_config),
        str(workspace),
        steps=[0, 5, 6, 7, 8, 9],
        dual_version=True,
    )

    assert result["status"] == "success"
    assert "Listing Dual Version Report" in result["dual_report_text"]
    assert "version_a" in result["dual_version"]["version_a_dir"]
    assert "version_b" in result["dual_version"]["version_b_dir"]
    assert captured[0] == {"blueprint": None, "title": None, "bullets": None}
    assert captured[1] == {
        "blueprint": "deepseek-reasoner",
        "title": "deepseek-reasoner",
        "bullets": "deepseek-reasoner",
    }


def test_run_workspace_workflow_dual_version_surfaces_version_b_failure_status(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace" / "H91LITE_US"
    workspace.mkdir(parents=True)
    run_config = workspace / "run_config.json"
    run_config.write_text(
        json.dumps({"product_code": "H91lite", "target_country": "US"}),
        encoding="utf-8",
    )

    def _fake_run(
        config_path,
        output_dir,
        steps=None,
        blueprint_model_override=None,
        title_model_override=None,
        bullet_model_override=None,
    ):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        if blueprint_model_override:
            (out / "execution_summary.json").write_text(
                json.dumps(
                    {
                        "workflow_status": "failed",
                        "results": {
                            "step_5": {
                                "status": "error",
                                "error": "experimental_version_b_blueprint_failed: timeout",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            return {
                "summary": {"workflow_status": "failed", "results": {"step_5": {"status": "error"}}},
                "generated_copy": {},
                "risk_report": {},
                "scoring_results": {},
                "writing_policy": {},
                "preprocessed_data": None,
            }
        (out / "generated_copy.json").write_text(
            json.dumps(
                {
                    "title": "Demo",
                    "bullets": ["B1", "B2", "B3", "B4", "B5"],
                    "description": "Desc",
                    "search_terms": ["t1"],
                    "metadata": {"generation_status": "live_success"},
                }
            ),
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            json.dumps(
                {
                    "listing_status": "READY_FOR_LISTING",
                    "dimensions": {
                        "traffic": {"score": 100},
                        "content": {"score": 100},
                        "conversion": {"score": 90},
                        "readability": {"score": 30},
                    },
                }
            ),
            encoding="utf-8",
        )
        return {
            "summary": {"workflow_status": "success"},
            "generated_copy": {},
            "risk_report": {},
            "scoring_results": {},
            "writing_policy": {},
            "preprocessed_data": None,
        }

    monkeypatch.setattr(run_service, "run_generator_workflow", _fake_run)
    monkeypatch.setattr(run_service, "snapshot_run_outputs", lambda *_args, **_kwargs: {})

    result = run_service.run_workspace_workflow(
        str(run_config),
        str(workspace),
        steps=[0, 5, 6, 7, 8, 9],
        dual_version=True,
    )

    assert result["dual_version"]["version_b"]["generation_status"] == "FAILED_AT_BLUEPRINT"
    assert "experimental_version_b_blueprint_failed: timeout" in result["dual_report_text"]


def test_attach_intent_weight_snapshot_updates_run_config(tmp_path: Path):
    workspace = workspace_service.initialize_workspace(
        product_code="T70",
        site="DE",
        brand_name="TOSBARRFT",
        files={},
        workspace_root=str(tmp_path),
    )
    snapshot_path = tmp_path / "intent_weights" / "latest.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text("{}", encoding="utf-8")

    workspace_service.attach_intent_weight_snapshot(workspace["run_config_path"], str(snapshot_path))

    run_config = json.loads(Path(workspace["run_config_path"]).read_text(encoding="utf-8"))
    assert run_config["intent_weight_snapshot_path"] == str(snapshot_path.resolve())


def test_run_workspace_workflow_returns_intent_weight_summary(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace" / "T70_DE"
    workspace.mkdir(parents=True)
    (workspace / "listing_report.md").write_text("# Report", encoding="utf-8")

    def _fake_run(config_path, output_dir, steps=None):
        output = Path(output_dir)
        (output / "listing_report.md").write_text("# Report", encoding="utf-8")
        return {
            "summary": {"workflow_status": "success"},
            "generated_copy": {
                "metadata": {},
                "evidence_bundle": {
                    "claim_support_matrix": [
                        {"claim": "150 minute runtime", "support_status": "supported"},
                        {"claim": "stormproof use", "support_status": "unsupported"},
                    ],
                    "rufus_readiness": {
                        "score": 0.5,
                        "supported_claim_count": 1,
                        "total_claim_count": 2,
                    },
                },
                "compute_tier_map": {
                    "title": {"tier_used": "native", "rerun_recommended": False, "rerun_priority": "normal"},
                    "bullet_1": {"tier_used": "rule_based", "rerun_recommended": True, "rerun_priority": "high"},
                },
            },
            "risk_report": {},
            "scoring_results": {},
            "writing_policy": {
                "intent_weight_summary": {
                    "updated_keyword_count": 2,
                    "top_promoted_keywords": ["helmet camera", "bike camera"],
                    "top_external_themes": ["commuter vlog setup"],
                    "channel_count": 1,
                }
            },
            "intent_graph": {},
        }

    monkeypatch.setattr(run_service, "run_generator_workflow", _fake_run)
    monkeypatch.setattr(run_service, "snapshot_run_outputs", lambda *_args, **_kwargs: {})

    result = run_service.run_workspace_workflow("config.json", str(workspace), steps=[0])

    assert result["status"] == "success"
    assert result["evidence_summary"]["unsupported_claim_count"] == 1
    assert result["compute_tier_summary"]["fallback_field_count"] == 1
    assert result["intent_weight_summary"]["updated_keyword_count"] == 2
    assert result["intent_weight_summary"]["top_external_themes"] == ["commuter vlog setup"]
    assert "prelaunch_checklist" in result
    assert "thirty_day_iteration_panel" in result


def test_list_workspace_runs_returns_single_and_dual_payloads(tmp_path: Path):
    workspace = tmp_path / "workspace" / "H91LITE_US"
    single_run = workspace / "runs" / "20260416_090000"
    dual_run = workspace / "runs" / "20260416_100000"
    single_run.mkdir(parents=True)
    (dual_run / "version_a").mkdir(parents=True)
    (dual_run / "version_b").mkdir(parents=True)

    (single_run / "generated_copy.json").write_text(
        json.dumps({"title": "Single Title", "bullets": ["B1"], "description": "Desc", "search_terms": ["kw"], "metadata": {"generation_status": "live_success"}}),
        encoding="utf-8",
    )
    (single_run / "risk_report.json").write_text(
        json.dumps({"listing_status": {"status": "READY_FOR_LISTING"}}),
        encoding="utf-8",
    )
    (single_run / "scoring_results.json").write_text(
        json.dumps({"dimensions": {"traffic": {"score": 100}, "content": {"score": 90}, "conversion": {"score": 88}, "readability": {"score": 30}}}),
        encoding="utf-8",
    )
    (single_run / "listing_report.md").write_text("# Single Report", encoding="utf-8")
    (single_run / "readiness_summary.md").write_text("# Single Summary", encoding="utf-8")

    for path, title in [
        (dual_run / "version_a", "Version A Title"),
        (dual_run / "version_b", "Version B Title"),
    ]:
        (path / "generated_copy.json").write_text(
            json.dumps({"title": title, "bullets": ["B1"], "description": "Desc", "search_terms": ["kw"], "metadata": {"generation_status": "live_success"}}),
            encoding="utf-8",
        )
        (path / "risk_report.json").write_text(
            json.dumps({"listing_status": {"status": "READY_FOR_LISTING"}}),
            encoding="utf-8",
        )
        (path / "scoring_results.json").write_text(
            json.dumps({"dimensions": {"traffic": {"score": 100}, "content": {"score": 100}, "conversion": {"score": 100}, "readability": {"score": 30}}}),
            encoding="utf-8",
        )
        (path / "listing_report.md").write_text(f"# {title} Report", encoding="utf-8")
        (path / "readiness_summary.md").write_text(f"# {title} Summary", encoding="utf-8")

    (dual_run / "dual_version_report.md").write_text("# Dual Version Report", encoding="utf-8")

    runs = workspace_service.list_workspace_runs(str(workspace))

    assert len(runs) == 2
    assert runs[0]["is_dual_version"] is True
    assert runs[0]["version_a"]["generated_copy"]["title"] == "Version A Title"
    assert runs[0]["version_b"]["generated_copy"]["title"] == "Version B Title"
    assert "Dual Version Report" in runs[0]["dual_report_text"]
    assert runs[1]["is_dual_version"] is False
    assert runs[1]["generated_copy"]["title"] == "Single Title"
    assert "Single Summary" in runs[1]["readiness_summary_text"]
