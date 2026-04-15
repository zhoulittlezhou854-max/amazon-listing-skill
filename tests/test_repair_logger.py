import json
from pathlib import Path

from modules import repair_logger as rl


def test_repair_log_written_after_successful_repair(tmp_path):
    artifact_dir = tmp_path / "step6_artifacts"

    entry = rl.record_repair(
        artifact_dir=str(artifact_dir),
        field="bullet_b2",
        rule_id="header_body_rupture",
        severity="high",
        original="BODY CAMERA WITH — It weighs 35g.",
        repaired="LIGHTWEIGHT DESIGN — At just 35g, it clips on comfortably.",
        repair_success=True,
        attempts=1,
        benchmark_used=True,
    )

    log_path = artifact_dir.parent / "repair_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["field"] == "bullet_b2"
    assert payload["repair_success"] is True
    assert payload["benchmark_used"] is True
    assert entry["rule_id"] == "header_body_rupture"


def test_repair_log_written_after_warned_repair(tmp_path):
    artifact_dir = tmp_path / "step6_artifacts"

    rl.record_repair(
        artifact_dir=str(artifact_dir),
        field="title",
        rule_id="title_missing_keyword",
        severity="medium",
        original="Mini camera, 1080p",
        repaired="Mini camera, 1080p",
        repair_success=False,
        attempts=2,
        benchmark_used=False,
    )

    summary = json.loads((artifact_dir.parent / "repair_summary.json").read_text(encoding="utf-8"))
    assert summary["total_repairs_attempted"] == 1
    assert summary["total_repairs_warned"] == 1
    assert summary["by_rule"]["title_missing_keyword"]["attempted"] == 1
    assert summary["by_rule"]["title_missing_keyword"]["warned"] == 1


def test_false_positive_detected_when_edit_distance_minimal():
    assert rl._is_false_positive_candidate(
        "LONG BATTERY — Records 150 minutes for daily rides.",
        "LONG BATTERY — Records 150 minutes for daily ride.",
        "dash_tail_without_predicate",
        fluency_score_before=2,
        fluency_score_after=2,
    )


def test_false_positive_not_detected_on_substantial_change():
    assert not rl._is_false_positive_candidate(
        "BODY CAMERA WITH — It weighs 35g perfect for travel.",
        "LIGHTWEIGHT DESIGN — At just 35g, it stays comfortable through every commute.",
        "header_body_rupture",
        fluency_score_before=0,
        fluency_score_after=3,
    )


def test_repair_summary_counts_by_rule(tmp_path):
    artifact_dir = tmp_path / "step6_artifacts"

    rl.record_repair(
        artifact_dir=str(artifact_dir),
        field="bullet_b2",
        rule_id="header_body_rupture",
        severity="high",
        original="A",
        repaired="B",
        repair_success=True,
    )
    rl.record_repair(
        artifact_dir=str(artifact_dir),
        field="bullet_b5",
        rule_id="header_body_rupture",
        severity="high",
        original="C",
        repaired="D",
        repair_success=False,
    )

    summary = json.loads((artifact_dir.parent / "repair_summary.json").read_text(encoding="utf-8"))
    assert summary["by_rule"]["header_body_rupture"] == {
        "attempted": 2,
        "succeeded": 1,
        "warned": 1,
    }


def test_repair_summary_includes_false_positive_candidates(tmp_path, monkeypatch):
    artifact_dir = tmp_path / "step6_artifacts"
    learnings_dir = tmp_path / ".learnings"
    monkeypatch.setattr(rl, "LEARNINGS_DIR", learnings_dir)

    rl.record_repair(
        artifact_dir=str(artifact_dir),
        field="bullet_b5",
        rule_id="dash_tail_without_predicate",
        severity="medium",
        original="BODY CAMERA — stable audio clip",
        repaired="BODY CAMERA — stable audio clips",
        repair_success=False,
    )

    summary = json.loads((artifact_dir.parent / "repair_summary.json").read_text(encoding="utf-8"))
    assert summary["false_positive_candidates"]
    learnings_path = learnings_dir / "false_positive_candidates.jsonl"
    assert learnings_path.exists()
    learnings = learnings_path.read_text(encoding="utf-8")
    assert "dash_tail_without_predicate" in learnings
