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


def test_run_single_version_enforces_deadline_and_persists_failure(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "version_b"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_workflow(*_args, **_kwargs):
        raise run_pipeline.VersionRunTimeout("version_deadline_exceeded:1")

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)

    result = run_pipeline._run_single_version(
        config_path=config_path,
        output_dir=output_dir,
        steps=None,
        blueprint_model_override="deepseek-v4-pro",
        title_model_override="deepseek-v4-pro",
        bullet_model_override="deepseek-v4-pro",
        deadline_seconds=1,
    )

    summary = json.loads((output_dir / "execution_summary.json").read_text(encoding="utf-8"))
    assert result["generation_status"] == "FAILED"
    assert summary["workflow_status"] == "failed"
    assert "version_deadline_exceeded" in summary["error"]


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
        model = "deepseek-v4-pro" if blueprint_model_override else "deepseek-v4-flash"
        (out / "generated_copy.json").write_text(
            '{"title":"Demo","bullets":["B1","B2","B3","B4","B5"],'
            '"description":"Desc","search_terms":["k1","k2"],'
            '"metadata":{"generation_status":"live_success"},"keyword_reconciliation":{"status":"complete"}}',
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
    assert calls[1]["override"] == "deepseek-v4-pro"
    assert calls[1]["title_override"] == "deepseek-v4-pro"
    assert calls[1]["bullet_override"] == "deepseek-v4-pro"
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
            '"metadata":{"generation_status":"live_success"},"keyword_reconciliation":{"status":"complete"}}',
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{'
            '"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-v4-flash"}', encoding="utf-8")
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


def test_main_dual_version_writes_partial_outputs_when_version_b_raises_timeout(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r15_dual_timeout"
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
            raise TimeoutError("version_b_deadline_exceeded")
        (out / "generated_copy.json").write_text(
            '{"title":"Version A Title","bullets":["A1","A2","A3","A4","A5"],'
            '"description":"Desc","search_terms":["k1","k2"],'
            '"metadata":{"generation_status":"live_success"},"keyword_reconciliation":{"status":"complete"}}',
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{'
            '"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "risk_report.json").write_text(
            '{"listing_status":{"status":"READY_FOR_LISTING","blocking_reasons":[]}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-v4-flash"}', encoding="utf-8")
        return {"summary": {"workflow_status": "success", "results": {"step_6": {"metadata": {"generation_status": "live_success"}}}}}

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r15_dual_timeout", "--dual-version"],
    )

    run_pipeline.main()

    stdout = capsys.readouterr().out
    verdict = json.loads((output_dir / "final_readiness_verdict.json").read_text(encoding="utf-8"))
    version_b_summary = json.loads((output_dir / "version_b" / "execution_summary.json").read_text(encoding="utf-8"))

    assert "Version B generation status: FAILED" in stdout
    assert version_b_summary["workflow_status"] == "failed"
    assert "version_b_deadline_exceeded" in version_b_summary["error"]
    assert verdict["recommended_output"] == "version_a"
    assert (output_dir / "LISTING_READY.md").exists()


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
                    "keyword_reconciliation": {"status": "complete"},
                }
            ),
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-v4-flash"}', encoding="utf-8")
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
    review_path = output_dir / "LISTING_REVIEW_REQUIRED.md"
    assert verdict_path.exists()
    assert not ready_path.exists()
    assert review_path.exists()

    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["recommended_output"] == "version_a"
    assert verdict["candidate_listing_status"] == "UNKNOWN"
    assert verdict["operational_listing_status"] == "NOT_READY_FOR_LISTING"
    assert verdict["listing_status"] == "NOT_READY_FOR_LISTING"
    assert verdict["launch_gate"]["scores"] == {"A10": 100, "COSMO": 100, "Rufus": 90, "Fluency": 30}
    assert verdict["artifact_paths"]["recommended_generated_copy"].endswith("version_a/generated_copy.json")

    review_text = review_path.read_text(encoding="utf-8")
    assert "Listing Review Required" in review_text
    assert "Passed: `False`" in review_text
    assert "Amazon Backend Paste Blocks" not in review_text
    assert "Version A title" in review_text
    dual_report = (output_dir / "all_report_compare.md").read_text(encoding="utf-8")
    assert "## Hybrid Launch Decision" in dual_report
    assert "Recommended Output: `version_a`" in dual_report


def test_main_dual_version_recommends_hybrid_for_review_when_scores_pass_but_risk_blocks(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r40_review"
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
        is_b = bool(blueprint_model_override)
        (out / "generated_copy.json").write_text(
            json.dumps(
                {
                    "title": "Version B Title" if is_b else "Version A Title",
                    "bullets": ["B1", "B2", "B3", "B4", "B5"] if is_b else ["A1", "A2", "A3", "A4", "A5"],
                    "description": "Desc",
                    "search_terms": ["k1", "k2"],
                    "metadata": {"generation_status": "live_success"},
                    "keyword_reconciliation": {"status": "complete"},
                    "decision_trace": {"keyword_assignments": [], "bullet_trace": []},
                }
            ),
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            '{"listing_status":"READY_FOR_LISTING","dimensions":{"traffic":{"score":100},"content":{"score":100},"conversion":{"score":90},"readability":{"score":30}}}',
            encoding="utf-8",
        )
        (out / "risk_report.json").write_text(
            '{"listing_status":{"status":"READY_FOR_LISTING","blocking_reasons":[]}}',
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-v4-pro"}', encoding="utf-8")
        if not is_b:
            (out / "preprocessed_data.json").write_text('{"preprocessed_data":{"processed_at":"2026-04-20"}}', encoding="utf-8")
            (out / "writing_policy.json").write_text("{}", encoding="utf-8")
        return {"summary": {"results": {"step_6": {"metadata": {"generation_status": "live_success"}}}}}

    def _fake_finalize_hybrid_outputs(**kwargs):
        hybrid_copy = kwargs["hybrid_copy"]
        hybrid_copy.setdefault("metadata", {})["launch_decision"] = {
            "passed": False,
            "recommended_output": "hybrid",
            "scores": {"A10": 80, "COSMO": 92, "Rufus": 100, "Fluency": 28},
            "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
            "reasons": ["listing_not_ready"],
        }
        return {
            "generated_copy": hybrid_copy,
            "risk_report": {"listing_status": {"status": "NOT_READY_FOR_LISTING", "blocking_reasons": ["Repeated word root more than twice: record"]}},
            "scoring_results": {
                "listing_status": "READY_FOR_LISTING",
                "dimensions": {
                    "traffic": {"score": 80},
                    "content": {"score": 92},
                    "conversion": {"score": 100},
                    "readability": {"score": 28},
                },
            },
        }

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(run_pipeline.hybrid_composer, "finalize_hybrid_outputs", _fake_finalize_hybrid_outputs)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r40_review", "--dual-version"],
    )

    run_pipeline.main()

    verdict = json.loads((output_dir / "final_readiness_verdict.json").read_text(encoding="utf-8"))
    assert verdict["recommended_output"] == "version_a"
    assert verdict["listing_status"] == "READY_FOR_LISTING"
    assert verdict["artifact_paths"]["recommended_generated_copy"].endswith("version_a/generated_copy.json")
    assert (output_dir / "LISTING_READY.md").exists()
    assert not (output_dir / "LISTING_REVIEW_REQUIRED.md").exists()
    ready_text = (output_dir / "LISTING_READY.md").read_text(encoding="utf-8")
    assert "Output: `version_a`" in ready_text
    assert "Amazon Backend Paste Blocks" in ready_text


def test_main_dual_version_keeps_version_b_only_output_review_required(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config" / "run_configs" / "H91lite_US.json"
    output_dir = tmp_path / "output" / "runs" / "H91lite_US_r_partial"
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
        if not blueprint_model_override:
            (out / "execution_summary.json").write_text(
                json.dumps({"workflow_status": "failed", "results": {}}),
                encoding="utf-8",
            )
            return {"summary": {"workflow_status": "failed", "results": {}}}
        (out / "generated_copy.json").write_text(
            json.dumps(
                {
                    "title": "Version B Title",
                    "bullets": ["B1", "B2", "B3", "B4", "B5"],
                    "description": "Version B Desc",
                    "search_terms": ["k1", "k2"],
                    "metadata": {"generation_status": "live_success"},
                    "keyword_reconciliation": {"status": "complete"},
                }
            ),
            encoding="utf-8",
        )
        (out / "scoring_results.json").write_text(
            json.dumps(
                {
                    "listing_status": "READY_FOR_LISTING",
                    "dimensions": {
                        "traffic": {"score": 90},
                        "content": {"score": 92},
                        "conversion": {"score": 100},
                        "readability": {"score": 30},
                    },
                }
            ),
            encoding="utf-8",
        )
        (out / "risk_report.json").write_text(
            json.dumps({"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}}),
            encoding="utf-8",
        )
        (out / "bullet_blueprint.json").write_text('{"llm_model":"deepseek-v4-pro"}', encoding="utf-8")
        return {"summary": {"results": {"step_6": {"metadata": {"generation_status": "live_success"}}}}}

    monkeypatch.setattr(run_pipeline, "run_generator_workflow", _fake_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--product", "H91lite", "--market", "US", "--run-id", "r_partial", "--dual-version"],
    )

    run_pipeline.main()

    verdict = json.loads((output_dir / "final_readiness_verdict.json").read_text(encoding="utf-8"))
    review_text = (output_dir / "LISTING_REVIEW_REQUIRED.md").read_text(encoding="utf-8")

    assert verdict["recommended_output"] == "version_b"
    assert verdict["artifact_paths"]["recommended_generated_copy"].endswith("version_b/generated_copy.json")
    assert verdict["operational_listing_status"] == "NOT_READY_FOR_LISTING"
    assert verdict["candidate_verdict"]["operational_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["launch_gate"]["passed"] is False
    assert not (output_dir / "LISTING_READY.md").exists()
    assert "Version B Title" in review_text
    assert "Output: `version_b`" in review_text


def test_final_verdict_replaces_blocked_launch_recommendation_with_ready_candidate(tmp_path: Path):
    version_a = {
        "generated_copy": {
            "title": "Version A Title",
            "bullets": ["A1", "A2", "A3", "A4", "A5"],
            "description": "Version A Desc",
            "search_terms": ["a1"],
            "generation_status": "live_success",
            "keyword_reconciliation": {"status": "complete"},
        },
        "risk_report": {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
        "scoring_results": {
            "dimensions": {
                "traffic": {"score": 100},
                "content": {"score": 100},
                "conversion": {"score": 100},
                "readability": {"score": 30},
            }
        },
    }
    version_b = {
        "generated_copy": {
            "title": "Version B Title",
            "bullets": ["B1", "B2", "B3", "B4", "B5"],
            "description": "Version B Desc",
            "search_terms": ["b1"],
            "generation_status": "live_success",
            "keyword_reconciliation": {"status": "complete"},
        },
        "risk_report": {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
        "scoring_results": {
            "dimensions": {
                "traffic": {"score": 100},
                "content": {"score": 100},
                "conversion": {"score": 100},
                "readability": {"score": 30},
            }
        },
    }
    hybrid_bundle = {
        "generated_copy": {
            "title": "Hybrid Title",
            "bullets": ["H1", "H2", "H3", "H4", "H5"],
            "description": "Hybrid Desc",
            "search_terms": ["h1"],
            "metadata": {
                "launch_decision": {
                    "passed": True,
                    "recommended_output": "version_b",
                    "scores": {"A10": 100, "COSMO": 100, "Rufus": 100, "Fluency": 30},
                    "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
                }
            },
        },
        "risk_report": {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
        "scoring_results": {
            "dimensions": {
                "traffic": {"score": 100},
                "content": {"score": 100},
                "conversion": {"score": 100},
                "readability": {"score": 30},
            }
        },
    }

    verdict = run_pipeline._build_final_readiness_verdict(
        run_id="r_contract",
        output_dir=tmp_path,
        version_a=version_a,
        version_b=version_b,
        hybrid_bundle=hybrid_bundle,
        hybrid_copy={},
    )

    assert verdict["recommended_output"] == "version_a"
    assert verdict["artifact_paths"]["recommended_generated_copy"].endswith("version_a/generated_copy.json")
    assert verdict["operational_listing_status"] == "READY_FOR_LISTING"
    assert verdict["launch_gate"]["passed"] is True


def test_final_verdict_recomputes_launch_gate_for_ready_version_a_when_hybrid_decision_failed(tmp_path: Path):
    version_a = {
        "generated_copy": {
            "title": "Version A Title",
            "bullets": ["A1", "A2", "A3", "A4", "A5"],
            "description": "Version A Desc",
            "search_terms": ["a1"],
            "generation_status": "live_success",
            "keyword_reconciliation": {"status": "complete"},
        },
        "risk_report": {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
        "scoring_results": {
            "listing_status": "READY_FOR_LISTING",
            "dimensions": {
                "traffic": {"score": 100},
                "content": {"score": 100},
                "conversion": {"score": 92},
                "readability": {"score": 28},
            },
        },
    }
    hybrid_bundle = {
        "generated_copy": {
            "title": "Hybrid Title",
            "bullets": ["H1", "H2", "H3", "H4", "H5"],
            "description": "Hybrid Desc",
            "search_terms": ["h1"],
            "metadata": {
                "launch_decision": {
                    "passed": False,
                    "recommended_output": "version_a",
                    "scores": {"A10": 100, "COSMO": 100, "Rufus": 92, "Fluency": 28},
                    "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
                    "reasons": ["listing_not_ready"],
                }
            },
            "keyword_reconciliation": {"status": "complete"},
        },
        "risk_report": {"listing_status": {"status": "NOT_READY_FOR_LISTING", "blocking_reasons": ["Repeated word root more than twice: record"]}},
        "scoring_results": {
            "listing_status": "READY_FOR_LISTING",
            "dimensions": {
                "traffic": {"score": 100},
                "content": {"score": 100},
                "conversion": {"score": 92},
                "readability": {"score": 28},
            },
        },
    }

    verdict = run_pipeline._build_final_readiness_verdict(
        run_id="r_recompute_version_a",
        output_dir=tmp_path,
        version_a=version_a,
        version_b={},
        hybrid_bundle=hybrid_bundle,
        hybrid_copy={},
    )

    assert verdict["recommended_output"] == "version_a"
    assert verdict["launch_gate"]["passed"] is True
    assert verdict["operational_listing_status"] == "READY_FOR_LISTING"
    assert verdict["listing_status"] == "READY_FOR_LISTING"
    assert verdict["reasons"] == []


def test_review_required_report_includes_field_provenance_and_fact_readiness(tmp_path: Path):
    hybrid_dir = tmp_path / "hybrid"
    hybrid_dir.mkdir()
    (hybrid_dir / "generated_copy.json").write_text(
        json.dumps(
            {
                "title": "Hybrid Title",
                "bullets": ["B1", "B2", "B3", "B4", "B5"],
                "description": "",
                "search_terms": ["k1"],
                "metadata": {
                    "field_provenance": {
                        "description": {
                            "provenance_tier": "safe_fallback",
                            "eligibility": "review_only",
                            "blocking_reasons": ["fallback_not_launch_eligible"],
                        },
                        "bullet_5": {
                            "provenance_tier": "native_live",
                            "eligibility": "blocked",
                            "blocking_reasons": ["slot_contract_failed:multiple_primary_promises"],
                        },
                    },
                    "canonical_fact_readiness": {
                        "required_fact_status": {
                            "video_resolution": "present",
                            "waterproof_supported": "known_blocked",
                        },
                        "blocking_missing": ["battery_life"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    verdict = {
        "recommended_output": "hybrid",
        "candidate_listing_status": "READY_FOR_LISTING",
        "operational_listing_status": "NOT_READY_FOR_LISTING",
        "launch_gate": {"passed": False, "scores": {}},
        "reasons": ["field_safe_fallback_not_launch_eligible:description"],
        "artifact_paths": {"hybrid_generated_copy": str(hybrid_dir / "generated_copy.json")},
    }

    path = run_pipeline._write_listing_review_required(tmp_path, verdict)

    text = path.read_text(encoding="utf-8")
    assert "## Field Provenance" in text
    assert "description: safe_fallback -> review_only" in text
    assert "bullet_5: native_live -> blocked" in text
    assert "## Canonical Fact Readiness" in text
    assert "battery_life: missing" in text
    assert "waterproof_supported: known_blocked" in text
