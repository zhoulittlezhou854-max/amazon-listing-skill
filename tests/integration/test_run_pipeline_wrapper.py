from pathlib import Path

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
    dual_report = (output_dir / "dual_version_report.md").read_text(encoding="utf-8")
    assert "Listing Dual Version Report" in dual_report
    assert "Version A：V3 全链路" in dual_report
    assert "Version B：R1 Title + Bullets + V3 Remaining Fields" in dual_report
