from pathlib import Path
import json

import run_pipeline


def test_resolve_run_paths_maps_product_market_and_run_id(tmp_path: Path):
    config_path, output_dir = run_pipeline.resolve_run_paths(
        "H91lite",
        "us",
        "r6",
        workspace_root=tmp_path,
    )

    assert config_path == tmp_path / "config" / "run_configs" / "H91lite_US.json"
    assert output_dir == tmp_path / "output" / "runs" / "H91lite_US_r6"


def test_main_fresh_clears_existing_output_before_running(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r7"
    output_dir.mkdir(parents=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")
    stale_file = output_dir / "stale.txt"
    stale_file.write_text("old artifacts", encoding="utf-8")

    monkeypatch.setattr(
        run_pipeline,
        "resolve_run_paths",
        lambda product, market, run_id: (config_path, output_dir),
    )

    captured = {}

    def _fake_workflow(config_arg: str, output_arg: str, steps=None):
        captured["config"] = config_arg
        captured["output"] = output_arg
        captured["steps"] = steps
        out = Path(output_arg)
        out.mkdir(parents=True, exist_ok=True)
        (out / "generated_copy.json").write_text(
            '{"metadata": {"generation_status": "live_success"}}',
            encoding="utf-8",
        )
        return {"summary": {"results": {"step_6": {"metadata": {"generation_status": "unknown"}}}}}

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r7", "--fresh"],
    )

    run_pipeline.main()

    stdout = capsys.readouterr().out
    assert "Generation status: live_success" in stdout
    assert captured["config"] == str(config_path)
    assert captured["output"] == str(output_dir)
    assert not stale_file.exists()


def test_main_dual_version_writes_versioned_outputs_and_report(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r15_dual"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        run_pipeline,
        "resolve_run_paths",
        lambda product, market, run_id: (config_path, output_dir),
    )

    calls = []

    def _fake_workflow(
        config_arg: str,
        output_arg: str,
        steps=None,
        blueprint_model_override=None,
        title_model_override=None,
        bullet_model_override=None,
    ):
        calls.append(
            {
                "output": output_arg,
                "override": blueprint_model_override,
                "title_override": title_model_override,
                "bullet_override": bullet_model_override,
            }
        )
        out = Path(output_arg)
        out.mkdir(parents=True, exist_ok=True)
        model = "deepseek-reasoner" if blueprint_model_override else "deepseek-chat"
        (out / "generated_copy.json").write_text(
            '{"title":"Demo","bullets":["B1","B2","B3","B4","B5"],'
            '"description":"Desc","search_terms":["k1","k2"],'
            '"metadata":{"generation_status":"live_success"}}',
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{'
            '"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text(
            f'{{"llm_model":"{model}"}}',
            encoding="utf-8",
        )
        return {"summary": {"results": {"step_6": {"metadata": {"generation_status": "live_success"}}}}}

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r15_dual", "--dual-version"],
    )

    run_pipeline.main()

    stdout = capsys.readouterr().out
    assert "Version A generation status: live_success" in stdout
    assert "Version B generation status: live_success" in stdout
    assert calls[0]["override"] is None
    assert calls[1]["override"] == "deepseek-reasoner"
    assert calls[1]["title_override"] == "deepseek-reasoner"
    assert calls[1]["bullet_override"] == "deepseek-reasoner"
    assert (output_dir / "version_a" / "generated_copy.json").exists()
    assert (output_dir / "version_b" / "generated_copy.json").exists()
    dual_report = (output_dir / "all_report_compare.md").read_text(encoding="utf-8")
    assert "Listing All Report Compare" in dual_report
    assert "Version A：V3 全链路" in dual_report
    assert "Version B：R1 Title + Bullets + V3 Remaining Fields" in dual_report


def test_main_dual_version_reports_explicit_version_b_failure(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r15_dual_fail"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        run_pipeline,
        "resolve_run_paths",
        lambda product, market, run_id: (config_path, output_dir),
    )

    def _fake_workflow(
        config_arg: str,
        output_arg: str,
        steps=None,
        blueprint_model_override=None,
        title_model_override=None,
        bullet_model_override=None,
    ):
        out = Path(output_arg)
        out.mkdir(parents=True, exist_ok=True)
        if blueprint_model_override:
            (out / "execution_summary.json").write_text(
                '{"workflow_status":"failed","results":{"step_5":{"status":"error","error":"experimental_version_b_blueprint_failed: timeout"}}}',
                encoding="utf-8",
            )
            return {"summary": {"workflow_status": "failed", "results": {"step_5": {"status": "error"}}}}
        (out / "generated_copy.json").write_text(
            '{"title":"Demo","bullets":["B1","B2","B3","B4","B5"],'
            '"description":"Desc","search_terms":["k1","k2"],'
            '"metadata":{"generation_status":"live_success"}}',
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{'
            '"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-chat"}', encoding="utf-8")
        return {"summary": {"results": {"step_6": {"metadata": {"generation_status": "live_success"}}}}}

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r15_dual_fail", "--dual-version"],
    )

    run_pipeline.main()

    stdout = capsys.readouterr().out
    assert "Version B generation status: FAILED_AT_BLUEPRINT" in stdout
    dual_report = (output_dir / "all_report_compare.md").read_text(encoding="utf-8")
    assert "Generation Status: FAILED_AT_BLUEPRINT" in dual_report
    assert "experimental_version_b_blueprint_failed: timeout" in dual_report


def test_main_dual_version_writes_final_verdict_and_listing_ready(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r28_hybrid_stabilize"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        run_pipeline,
        "resolve_run_paths",
        lambda product, market, run_id: (config_path, output_dir),
    )

    def _fake_workflow(
        config_arg: str,
        output_arg: str,
        steps=None,
        blueprint_model_override=None,
        title_model_override=None,
        bullet_model_override=None,
    ):
        out = Path(output_arg)
        out.mkdir(parents=True, exist_ok=True)
        title = "Version B title" if blueprint_model_override else "Version A title"
        bullets = ["B1", "B2", "B3", "B4", "B5"] if blueprint_model_override else ["A1", "A2", "A3", "A4", "A5"]
        (out / "generated_copy.json").write_text(
            json.dumps(
                {
                    "title": title,
                    "bullets": bullets,
                    "description": "Desc",
                    "search_terms": ["k1", "k2"],
                    "metadata": {"generation_status": "live_success"},
                }
            ),
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-chat"}', encoding="utf-8")
        if not blueprint_model_override:
            (out / "preprocessed_data.json").write_text('{"preprocessed_data":{"processed_at":"2026-04-20"}}', encoding="utf-8")
            (out / "writing_policy.json").write_text("{}", encoding="utf-8")
        return {"summary": {"results": {"step_6": {"metadata": {"generation_status": "live_success"}}}}}

    def _fake_finalize_hybrid_outputs(**kwargs):
        hybrid_copy = kwargs["hybrid_copy"]
        hybrid_copy.setdefault("metadata", {})["launch_decision"] = {
            "passed": False,
            "recommended_output": "version_a",
            "scores": {"A10": 70, "COSMO": 92, "Rufus": 100, "Fluency": 30},
            "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
            "reasons": ["a10_below_threshold"],
        }
        return {
            "generated_copy": hybrid_copy,
            "risk_report": {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
            "scoring_results": {
                "listing_status": "NOT_READY_FOR_LISTING",
                "dimensions": {
                    "traffic": {"score": 70},
                    "content": {"score": 92},
                    "conversion": {"score": 100},
                    "readability": {"score": 30},
                },
            },
        }

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(run_pipeline.hybrid_composer, "finalize_hybrid_outputs", _fake_finalize_hybrid_outputs)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r28_hybrid_stabilize", "--dual-version"],
    )

    run_pipeline.main()

    verdict_path = output_dir / "final_readiness_verdict.json"
    ready_path = output_dir / "LISTING_READY.md"
    assert verdict_path.exists()
    assert ready_path.exists()

    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["recommended_output"] == "version_a"
    assert verdict["launch_gate"]["scores"] == {"A10": 70, "COSMO": 92, "Rufus": 100, "Fluency": 30}
    assert verdict["artifact_paths"]["recommended_generated_copy"].endswith("version_a/generated_copy.json")

    ready_text = ready_path.read_text(encoding="utf-8")
    assert "## Amazon Backend Paste Blocks" in ready_text
    assert "### Title" in ready_text
    assert "### Bullet 1" in ready_text
    assert "### Search Terms" in ready_text
    assert "Version A title" in ready_text
    assert "A1" in ready_text
    dual_report = (output_dir / "all_report_compare.md").read_text(encoding="utf-8")
    assert "## Hybrid Launch Decision" in dual_report
    assert "Recommended Output: `version_a`" in dual_report
