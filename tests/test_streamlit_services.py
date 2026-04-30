import json
from pathlib import Path
from types import SimpleNamespace

from app.services import run_service, workspace_service
from modules import run_worker


class _Upload:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self):
        return self._content


class _CompletedInlineWorker:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode

    def poll(self):
        return self.returncode


def _arg_after(command: list[str], flag: str) -> str | None:
    if flag not in command:
        return None
    index = command.index(flag)
    if index + 1 >= len(command):
        return None
    return command[index + 1]


def _install_inline_service_workers(monkeypatch):
    def _launch_worker_inline(spec: dict):
        command = list(spec.get("command") or [])
        output_dir = Path(spec["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        run_worker.create_worker_status_manifest(
            output_dir=output_dir,
            worker_name=str(spec.get("worker_name") or ""),
            role=str(spec.get("role") or ""),
            deadline_seconds=int(spec.get("deadline_seconds") or 0),
        )
        try:
            raw_steps = _arg_after(command, "--steps")
            steps = [int(chunk.strip()) for chunk in raw_steps.split(",") if chunk.strip()] if raw_steps else None
            result = run_service.run_generator_workflow(
                str(_arg_after(command, "--config-path") or ""),
                str(output_dir),
                steps=steps,
                blueprint_model_override=_arg_after(command, "--blueprint-model-override"),
                title_model_override=_arg_after(command, "--title-model-override"),
                bullet_model_override=_arg_after(command, "--bullet-model-override"),
            )
            summary = result.get("summary") or {}
            workflow_status = summary.get("workflow_status") or "success"
            if workflow_status == "success" and (output_dir / "generated_copy.json").exists():
                run_worker.mark_worker_terminal_state(output_dir, state="success")
                spec["process"] = _CompletedInlineWorker(0)
            else:
                run_worker.mark_worker_terminal_state(
                    output_dir,
                    state="failed",
                    error=str(summary.get("error") or workflow_status),
                )
                spec["process"] = _CompletedInlineWorker(1)
        except TimeoutError as exc:
            run_service._persist_failure_summary(
                output_dir,
                run_config_path=str(_arg_after(command, "--config-path") or ""),
                steps=steps,
                error=str(exc),
                logs="",
            )
            run_worker.mark_worker_terminal_state(output_dir, state="timed_out", error=str(exc))
            spec["process"] = _CompletedInlineWorker(124)
        return spec["process"]

    monkeypatch.setattr(run_service.run_supervisor, "launch_worker", _launch_worker_inline)


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
    execution_summary = json.loads(Path(result["run_dir"]).joinpath("execution_summary.json").read_text(encoding="utf-8"))
    assert execution_summary["workflow_status"] == "failed"
    assert execution_summary["error"] == "runner failed"
    assert execution_summary["results"]["service_wrapper"]["status"] == "error"


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
        else:
            (out / "preprocessed_data.json").write_text(
                json.dumps({"preprocessed_data": {"processed_at": "2026-04-21"}}),
                encoding="utf-8",
            )
            (out / "writing_policy.json").write_text("{}", encoding="utf-8")
        return {
            "summary": {"workflow_status": "success"},
            "generated_copy": {},
            "risk_report": {},
            "scoring_results": {},
            "writing_policy": {},
            "preprocessed_data": None,
        }

    def _fake_finalize_hybrid_outputs(**kwargs):
        hybrid_output = Path(kwargs["output_dir"])
        hybrid_output.mkdir(parents=True, exist_ok=True)
        generated_copy = {
            "title": "Hybrid Title",
            "bullets": ["H1", "H2", "H3", "H4", "H5"],
            "description": "Hybrid Desc",
            "search_terms": ["hk1"],
            "metadata": {
                "hybrid_generation_status": "reaudited",
                "visible_copy_mode": "hybrid_postselect",
                "launch_decision": {
                    "passed": False,
                    "recommended_output": "version_a",
                    "scores": {"A10": 70, "COSMO": 92, "Rufus": 100, "Fluency": 30},
                    "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
                    "reasons": ["a10_below_threshold"],
                },
            },
        }
        scoring_results = {
            "listing_status": "NOT_READY_FOR_LISTING",
            "dimensions": {
                "traffic": {"score": 70},
                "content": {"score": 92},
                "conversion": {"score": 100},
                "readability": {"score": 30},
            },
        }
        risk_report = {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}}
        (hybrid_output / "generated_copy.json").write_text(json.dumps(generated_copy), encoding="utf-8")
        (hybrid_output / "scoring_results.json").write_text(json.dumps(scoring_results), encoding="utf-8")
        (hybrid_output / "risk_report.json").write_text(json.dumps(risk_report), encoding="utf-8")
        return {
            "generated_copy": generated_copy,
            "risk_report": risk_report,
            "scoring_results": scoring_results,
        }

    monkeypatch.setattr(run_service, "run_generator_workflow", _fake_run)
    _install_inline_service_workers(monkeypatch)
    monkeypatch.setattr(run_service, "snapshot_run_outputs", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        run_service,
        "hybrid_composer",
        SimpleNamespace(
            compose_hybrid_listing=lambda **kwargs: {
                "title": "Hybrid Title",
                "bullets": ["H1", "H2", "H3", "H4", "H5"],
                "description": "Hybrid Desc",
                "search_terms": ["hk1"],
                "metadata": {"hybrid_sources": {"title": "version_a"}, "visible_copy_mode": "hybrid_postselect"},
            },
            finalize_hybrid_outputs=lambda **kwargs: _fake_finalize_hybrid_outputs(**kwargs),
        ),
        raising=False,
    )

    result = run_service.run_workspace_workflow(
        str(run_config),
        str(workspace),
        steps=[0, 5, 6, 7, 8, 9],
        dual_version=True,
    )

    assert result["status"] == "success"
    assert "Listing All Report Compare" in result["dual_report_text"]
    assert "version_a" in result["dual_version"]["version_a_dir"]
    assert "version_b" in result["dual_version"]["version_b_dir"]
    assert "Hybrid Launch Decision" in result["dual_report_text"]
    run_dir = Path(result["run_dir"])
    assert (run_dir / "hybrid" / "generated_copy.json").exists()
    assert (run_dir / "final_readiness_verdict.json").exists()
    assert not (run_dir / "LISTING_READY.md").exists()
    assert (run_dir / "LISTING_REVIEW_REQUIRED.md").exists()
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
    _install_inline_service_workers(monkeypatch)
    monkeypatch.setattr(run_service, "snapshot_run_outputs", lambda *_args, **_kwargs: {})

    result = run_service.run_workspace_workflow(
        str(run_config),
        str(workspace),
        steps=[0, 5, 6, 7, 8, 9],
        dual_version=True,
    )

    assert result["dual_version"]["version_b"]["generation_status"] == "FAILED_AT_BLUEPRINT"
    assert "experimental_version_b_blueprint_failed: timeout" in result["dual_report_text"]


def test_run_workspace_workflow_dual_version_marks_b_timeout_partial_success(tmp_path: Path, monkeypatch):
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
            raise TimeoutError("version_b_deadline_exceeded")
        (out / "generated_copy.json").write_text(
            json.dumps(
                {
                    "title": "Version A Title",
                    "bullets": ["A1", "A2", "A3", "A4", "A5"],
                    "description": "Desc",
                    "search_terms": ["t1"],
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
                        "traffic": {"score": 100},
                        "content": {"score": 100},
                        "conversion": {"score": 90},
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
        return {"summary": {"workflow_status": "success"}}

    monkeypatch.setattr(run_service, "run_generator_workflow", _fake_run)
    _install_inline_service_workers(monkeypatch)
    monkeypatch.setattr(run_service, "snapshot_run_outputs", lambda *_args, **_kwargs: {})

    result = run_service.run_workspace_workflow(
        str(run_config),
        str(workspace),
        steps=[0, 5, 6, 7, 8, 9],
        dual_version=True,
    )

    run_dir = Path(result["run_dir"])
    assert result["status"] == "partial_success"
    assert result["supervisor_summary"]["state"] == "partial_success"
    assert result["supervisor_summary"]["workers"]["version_b"]["state"] == "timed_out"
    assert result["dual_version"]["version_b"]["reference_status"] == "not_available"
    assert (run_dir / "hybrid" / "unavailable.json").exists()
    assert not (run_dir / "hybrid" / "generated_copy.json").exists()


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
    (dual_run / "hybrid").mkdir(parents=True)

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
        (dual_run / "hybrid", "Hybrid Title"),
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

    (dual_run / "all_report_compare.md").write_text("# All Report Compare", encoding="utf-8")
    (dual_run / "final_readiness_verdict.json").write_text(
        json.dumps(
            {
                "recommended_output": "hybrid",
                "listing_status": "READY_FOR_LISTING",
                "launch_gate": {"scores": {"A10": 90, "COSMO": 92, "Rufus": 100, "Fluency": 30}},
                "artifact_paths": {
                    "recommended_generated_copy": str((dual_run / "hybrid" / "generated_copy.json").resolve()),
                },
            }
        ),
        encoding="utf-8",
    )
    (dual_run / "LISTING_READY.md").write_text("# Listing Ready", encoding="utf-8")

    runs = workspace_service.list_workspace_runs(str(workspace))

    assert len(runs) == 2
    assert runs[0]["is_dual_version"] is True
    assert runs[0]["version_a"]["generated_copy"]["title"] == "Version A Title"
    assert runs[0]["version_b"]["generated_copy"]["title"] == "Version B Title"
    assert runs[0]["hybrid"]["generated_copy"]["title"] == "Hybrid Title"
    assert runs[0]["recommended_output"] == "hybrid"
    assert runs[0]["listing_status"] == "READY_FOR_LISTING"
    assert runs[0]["scores"] == {"A10": 90, "COSMO": 92, "Rufus": 100, "Fluency": 30}
    assert "Listing Ready" in runs[0]["listing_ready_text"]
    assert "All Report Compare" in runs[0]["dual_report_text"]
    assert runs[1]["is_dual_version"] is False
    assert runs[1]["generated_copy"]["title"] == "Single Title"
    assert "Single Summary" in runs[1]["readiness_summary_text"]


def test_snapshot_run_outputs_dual_version_captures_verdict_and_reports(tmp_path: Path):
    workspace = tmp_path / "workspace" / "H91LITE_US"
    run_dir = workspace / "runs" / "20260421_120000"
    (run_dir / "version_a").mkdir(parents=True)
    (run_dir / "hybrid").mkdir(parents=True)
    (run_dir / "all_report_compare.md").write_text("# All Report Compare", encoding="utf-8")
    (run_dir / "final_readiness_verdict.json").write_text('{"recommended_output":"hybrid"}', encoding="utf-8")
    (run_dir / "LISTING_READY.md").write_text("# Ready", encoding="utf-8")
    (run_dir / "hybrid" / "listing_report.md").write_text("# Hybrid Report", encoding="utf-8")
    (run_dir / "version_a" / "generated_copy.json").write_text("{}", encoding="utf-8")

    captured = workspace_service.snapshot_run_outputs(str(workspace), str(run_dir))

    assert "all_report_compare.md" in captured
    assert "final_readiness_verdict.json" in captured
    assert "LISTING_READY.md" in captured
    assert "hybrid_listing_report.md" in captured
    assert Path(captured["all_report_compare.md"]).exists()


def test_list_product_code_options_filters_by_site_and_deduplicates(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    entries = [
        ("H91", "US", "2026-04-16T11:38:49+00:00"),
        ("H91lit", "US", "2026-04-16T07:25:02+00:00"),
        ("H91", "US", "2026-04-15T07:25:02+00:00"),
        ("T70", "DE", "2026-04-17T07:25:02+00:00"),
    ]
    for index, (product_code, site, created_at) in enumerate(entries):
        workspace = workspace_root / f"workspace_{index}"
        workspace.mkdir(parents=True)
        (workspace / "product_config.json").write_text(
            json.dumps(
                {
                    "product_code": product_code,
                    "site": site,
                    "workspace_dir": str(workspace.resolve()),
                    "run_config_path": str((workspace / "run_config.json").resolve()),
                    "created_at": created_at,
                }
            ),
            encoding="utf-8",
        )

    assert workspace_service.list_product_code_options("US", workspace_root=str(workspace_root)) == ["H91", "H91lit"]
    assert workspace_service.list_product_code_options("DE", workspace_root=str(workspace_root)) == ["T70"]


def test_list_product_code_options_returns_empty_without_history(tmp_path: Path):
    assert workspace_service.list_product_code_options("US", workspace_root=str(tmp_path / "workspace")) == []
