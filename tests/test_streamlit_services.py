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


def test_run_workspace_workflow_returns_failure_payload_when_runner_raises(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace" / "T70_FR"
    workspace.mkdir(parents=True)

    def _boom(config_path, output_dir, steps=None):
        raise RuntimeError("runner failed")

    monkeypatch.setattr(run_service, "run_generator_workflow", _boom)
    result = run_service.run_workspace_workflow("config.json", str(workspace), steps=[0])
    assert result["status"] == "RUN_FAILED"
    assert "runner failed" in result["error"]


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
