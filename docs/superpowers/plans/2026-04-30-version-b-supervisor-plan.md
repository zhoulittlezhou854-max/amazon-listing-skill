# Version B Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add supervised dual-version execution so `version_a` remains the primary reliable output while `version_b` can fail or time out without blocking final verdict/report generation.

**Architecture:** Dual-version runs launch isolated worker subprocesses for `version_a` and `version_b`; a supervisor monitors `worker_status.json`, deadline, heartbeat, process termination, and output availability. If `version_b` fails or times out, the run becomes `partial_success`, `hybrid/generated_copy.json` is not produced, `hybrid/unavailable.json` explains why, and final readiness is computed from `version_a` only.

**Tech Stack:** Python stdlib (`subprocess`, `json`, `datetime`, `pathlib`, `signal`), existing `run_generator_workflow`, existing `run_pipeline.py`, Streamlit service/UI tests, pytest.

---

## Confirmed Product Contract

- `version_a` is primary and must be protected.
- `version_b` is experimental and must not block final reporting.
- Default deadlines: `version_a=1200s`, `version_b=1800s`.
- If A succeeds and B fails/times out: `run_status=partial_success`.
- `partial_success` does not block `LISTING_READY.md` if A passes launch gate.
- Worker status must include heartbeat, current step/stage/field, reference status, output paths, and termination details.
- Timeout handling: mark timed_out, terminate, wait 30s, kill if still alive.
- B failed/timed_out: do not write `hybrid/generated_copy.json`; write `hybrid/unavailable.json`.
- UI change scope: minimal worker status display only; no full status-contract UI refactor.
- Live validation checks supervisor behavior; it does not require `LISTING_READY.md`.

## File Structure

- Create `modules/run_worker.py`: worker status manifest helpers plus CLI entrypoint that runs one version workflow and writes terminal state.
- Create `modules/run_supervisor.py`: worker spec builder, subprocess launcher/monitor, timeout termination, summary writer.
- Modify `main.py`: emit step/field callbacks enough for worker heartbeat; reuse existing `status_callback` if available.
- Modify `run_pipeline.py`: dual-version path uses supervisor; finalization handles B unavailable and writes `hybrid/unavailable.json`.
- Modify `app/services/run_service.py`: dual-version service path uses supervisor; returns `supervisor_summary` to UI.
- Modify `app/streamlit_app.py`: render a minimal worker status panel.
- Update `modules/INDEX.md`, `tests/INDEX.md` for new modules/tests.
- Create/modify tests:
  - `tests/test_run_worker.py`
  - `tests/test_run_supervisor.py`
  - `tests/integration/test_run_pipeline_wrapper.py`
  - `tests/test_streamlit_services.py`
  - `tests/test_streamlit_app.py`

---

### Task 1: Worker Status Contract

**Files:**
- Create: `modules/run_worker.py`
- Test: `tests/test_run_worker.py`
- Modify: `modules/INDEX.md`, `tests/INDEX.md`

- [ ] **Step 1: Write failing tests for worker status lifecycle**

Add tests that expect a manifest with role, deadline, heartbeat, current step, output paths, reference status, and terminal states.

```python
from pathlib import Path

from modules import run_worker


def test_create_worker_status_manifest_records_deadline_and_reference_status(tmp_path: Path):
    status = run_worker.create_worker_status_manifest(
        output_dir=tmp_path,
        worker_name="version_b",
        role="experimental",
        deadline_seconds=1800,
    )

    assert status["worker_name"] == "version_b"
    assert status["role"] == "experimental"
    assert status["state"] == "pending"
    assert status["reference_status"] == "not_available"
    assert status["used_for_final_verdict"] is False
    assert status["deadline_seconds"] == 1800
    assert status["deadline_at"]
    assert (tmp_path / run_worker.WORKER_STATUS_FILE).exists()


def test_update_worker_status_records_heartbeat_step_stage_and_field(tmp_path: Path):
    run_worker.create_worker_status_manifest(
        output_dir=tmp_path,
        worker_name="version_a",
        role="primary",
        deadline_seconds=1200,
    )

    updated = run_worker.update_worker_status(
        tmp_path,
        state="running",
        current_step=6,
        current_stage="copy_generation",
        current_field="description",
    )

    assert updated["state"] == "running"
    assert updated["heartbeat_at"]
    assert updated["current_step"] == 6
    assert updated["current_stage"] == "copy_generation"
    assert updated["current_field"] == "description"


def test_mark_worker_terminal_state_sets_reference_for_timeout(tmp_path: Path):
    run_worker.create_worker_status_manifest(
        output_dir=tmp_path,
        worker_name="version_b",
        role="experimental",
        deadline_seconds=1800,
    )

    final = run_worker.mark_worker_terminal_state(
        tmp_path,
        state="timed_out",
        error="deadline_exceeded",
        termination={"terminate_sent": True, "kill_sent": True},
    )

    assert final["state"] == "timed_out"
    assert final["reference_status"] == "not_available"
    assert final["reference_reason"] == "version_b timed out after 1800 seconds"
    assert final["termination"]["kill_sent"] is True
```

- [ ] **Step 2: Run red test**

Run: `./.venv/bin/pytest tests/test_run_worker.py -q`
Expected: FAIL because `modules.run_worker` does not exist.

- [ ] **Step 3: Implement minimal worker status helpers**

Implement:

```python
WORKER_STATUS_FILE = "worker_status.json"

def create_worker_status_manifest(output_dir, worker_name, role, deadline_seconds): ...
def read_worker_status(output_dir): ...
def update_worker_status(output_dir, **updates): ...
def mark_worker_terminal_state(output_dir, state, error="", termination=None): ...
```

Rules:
- `version_a` role `primary` defaults `reference_status=primary_result` and `used_for_final_verdict=True` when success.
- `version_b` role `experimental` defaults `reference_status=not_available` until success is proven.
- terminal `failed` => `reference_status=failed`.
- terminal `timed_out` => `reference_status=not_available`.

- [ ] **Step 4: Run green test**

Run: `./.venv/bin/pytest tests/test_run_worker.py -q`
Expected: PASS.

- [ ] **Step 5: Update indexes**

Add `run_worker.py` and `test_run_worker.py` rows to `modules/INDEX.md` and `tests/INDEX.md`.

---

### Task 2: Worker CLI Entrypoint

**Files:**
- Modify: `modules/run_worker.py`
- Test: `tests/test_run_worker.py`

- [ ] **Step 1: Write failing test for CLI job wrapper**

```python
from pathlib import Path

from modules import run_worker


def test_run_worker_job_marks_success_and_writes_output_paths(tmp_path: Path, monkeypatch):
    def _fake_run_generator_workflow(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "generated_copy.json").write_text("{}", encoding="utf-8")
        (output_dir / "risk_report.json").write_text("{}", encoding="utf-8")
        (output_dir / "scoring_results.json").write_text("{}", encoding="utf-8")
        (output_dir / "execution_summary.json").write_text("{}", encoding="utf-8")
        return {"summary": {"workflow_status": "success"}}

    monkeypatch.setattr(run_worker, "run_generator_workflow", _fake_run_generator_workflow)

    result = run_worker.run_worker_job(
        worker_name="version_a",
        role="primary",
        config_path="config/run_configs/H91lite_US.json",
        output_dir=tmp_path,
        steps=[0, 6, 8],
        deadline_seconds=1200,
    )

    status = run_worker.read_worker_status(tmp_path)
    assert result["state"] == "success"
    assert status["state"] == "success"
    assert status["generated_copy_path"].endswith("generated_copy.json")
    assert status["reference_status"] == "primary_result"
```

- [ ] **Step 2: Run red test**

Run: `./.venv/bin/pytest tests/test_run_worker.py::test_run_worker_job_marks_success_and_writes_output_paths -q`
Expected: FAIL because `run_worker_job` is missing.

- [ ] **Step 3: Implement `run_worker_job` and CLI parser**

Support arguments:

```bash
python -m modules.run_worker \
  --worker-name version_b \
  --role experimental \
  --config-path config/run_configs/H91lite_US.json \
  --output-dir output/runs/.../version_b \
  --deadline-seconds 1800 \
  --steps 0,1,2,3,4,5,6,7,8,9 \
  --blueprint-model-override deepseek-v4-pro \
  --title-model-override deepseek-v4-pro \
  --bullet-model-override deepseek-v4-pro
```

Implementation points:
- Create manifest before running.
- Pass a `status_callback` into `run_generator_workflow` that updates heartbeat/current step/stage/field.
- Mark success only when workflow status is success and expected output files exist.
- Mark failed on exception and store error string.

- [ ] **Step 4: Run worker tests**

Run: `./.venv/bin/pytest tests/test_run_worker.py -q`
Expected: PASS.

---

### Task 3: Supervisor Monitoring and Timeout Termination

**Files:**
- Create: `modules/run_supervisor.py`
- Test: `tests/test_run_supervisor.py`
- Modify: `modules/INDEX.md`, `tests/INDEX.md`

- [ ] **Step 1: Write failing tests for worker specs and timeout summary**

```python
from pathlib import Path
from types import SimpleNamespace

from modules import run_supervisor, run_worker


def test_build_worker_spec_sets_version_deadlines(tmp_path: Path):
    spec_a = run_supervisor.build_worker_spec(
        worker_name="version_a",
        run_config_path="config/run_configs/H91lite_US.json",
        output_dir=tmp_path / "version_a",
    )
    spec_b = run_supervisor.build_worker_spec(
        worker_name="version_b",
        run_config_path="config/run_configs/H91lite_US.json",
        output_dir=tmp_path / "version_b",
        blueprint_model_override="deepseek-v4-pro",
        title_model_override="deepseek-v4-pro",
        bullet_model_override="deepseek-v4-pro",
    )

    assert spec_a["deadline_seconds"] == 1200
    assert spec_a["role"] == "primary"
    assert spec_b["deadline_seconds"] == 1800
    assert spec_b["role"] == "experimental"
    assert "modules.run_worker" in " ".join(spec_b["command"])


def test_supervise_workers_marks_b_timeout_partial_success(tmp_path: Path, monkeypatch):
    version_a = tmp_path / "version_a"
    version_b = tmp_path / "version_b"
    run_worker.create_worker_status_manifest(version_a, "version_a", "primary", 1200)
    run_worker.mark_worker_terminal_state(version_a, state="success")
    run_worker.create_worker_status_manifest(version_b, "version_b", "experimental", 1800)

    class _Proc:
        def __init__(self, name):
            self.name = name
            self.returncode = None
            self.terminated = False
            self.killed = False
        def poll(self):
            return self.returncode
        def terminate(self):
            self.terminated = True
        def kill(self):
            self.killed = True
            self.returncode = -9
        def wait(self, timeout=None):
            raise TimeoutError("still running")

    procs = {"version_a": _Proc("version_a"), "version_b": _Proc("version_b")}
    procs["version_a"].returncode = 0

    specs = [
        {"worker_name": "version_a", "output_dir": str(version_a), "deadline_ts": 9999999999, "process": procs["version_a"]},
        {"worker_name": "version_b", "output_dir": str(version_b), "deadline_ts": 0, "process": procs["version_b"]},
    ]

    summary = run_supervisor.supervise_workers(
        worker_specs=specs,
        poll_interval_seconds=0,
        terminate_grace_seconds=0,
        kill_grace_seconds=0,
    )

    assert summary["state"] == "partial_success"
    assert summary["workers"]["version_b"]["state"] == "timed_out"
    assert summary["workers"]["version_b"]["reference_status"] == "not_available"
    assert summary["workers"]["version_b"]["termination"]["kill_sent"] is True
```

- [ ] **Step 2: Run red test**

Run: `./.venv/bin/pytest tests/test_run_supervisor.py -q`
Expected: FAIL because `modules.run_supervisor` does not exist.

- [ ] **Step 3: Implement supervisor**

Implement:

```python
DEFAULT_VERSION_A_DEADLINE_SECONDS = 1200
DEFAULT_VERSION_B_DEADLINE_SECONDS = 1800
SUPERVISOR_SUMMARY_FILE = "supervisor_summary.json"

def build_worker_spec(...): ...
def launch_worker(spec): ...
def supervise_workers(worker_specs, poll_interval_seconds=5, terminate_grace_seconds=30, kill_grace_seconds=10): ...
def write_supervisor_summary(run_dir, summary): ...
```

Summary rules:
- A success + B success => `success`.
- A success + B failed/timed_out => `partial_success`.
- A failed/timed_out => `failed`.
- `available_outputs` includes versions with `generated_copy.json`.
- `blocking_components` includes `version_a` if A failed/timed_out.

- [ ] **Step 4: Run supervisor tests**

Run: `./.venv/bin/pytest tests/test_run_supervisor.py -q`
Expected: PASS.

---

### Task 4: Dual-Version Pipeline Integration

**Files:**
- Modify: `run_pipeline.py`
- Test: `tests/integration/test_run_pipeline_wrapper.py`

- [ ] **Step 1: Write failing integration tests for partial success and hybrid unavailable**

Test with monkeypatched supervisor outputs:

```python
def test_dual_version_b_timeout_writes_hybrid_unavailable_and_final_verdict(tmp_path, monkeypatch):
    # Arrange version_a output as success, version_b worker status as timed_out.
    # Monkeypatch run_supervisor.supervise_workers to return partial_success.
    # Act: run dual-version wrapper.
    # Assert: final_readiness_verdict.json exists, hybrid/unavailable.json exists,
    # hybrid/generated_copy.json does not exist, LISTING_READY or LISTING_REVIEW_REQUIRED exists.
```

Expected artifacts:

```json
{
  "status": "unavailable",
  "reason": "version_b_timed_out",
  "source": "supervisor_summary"
}
```

- [ ] **Step 2: Run red test**

Run: `./.venv/bin/pytest tests/integration/test_run_pipeline_wrapper.py -q`
Expected: FAIL because pipeline still expects both versions to complete for hybrid.

- [ ] **Step 3: Integrate supervisor into `--dual-version` path**

Implementation points:
- Build two worker specs.
- Launch/supervise workers.
- Load existing bundles from version directories.
- If A unavailable: write failed summary and do not produce fake final verdict.
- If A available and B unavailable: write `hybrid/unavailable.json`, build final verdict from A only, run status `partial_success`.
- If A and B available: compose hybrid as today.
- Include `supervisor_summary` in final result and compare report inputs.

- [ ] **Step 4: Run integration tests**

Run: `./.venv/bin/pytest tests/integration/test_run_pipeline_wrapper.py -q`
Expected: PASS.

---

### Task 5: Service Layer Integration

**Files:**
- Modify: `app/services/run_service.py`
- Test: `tests/test_streamlit_services.py`

- [ ] **Step 1: Write failing service tests**

Add tests for:

```python
def test_run_workspace_workflow_dual_version_b_timeout_returns_partial_success(tmp_path, monkeypatch):
    # Fake supervisor returns version_a success and version_b timed_out.
    # Assert result["status"] == "partial_success".
    # Assert result["supervisor_summary"]["workers"]["version_b"]["reference_status"] == "not_available".
    # Assert LISTING_READY or LISTING_REVIEW_REQUIRED still exists based on A verdict.
    # Assert hybrid/unavailable.json exists and hybrid/generated_copy.json missing.
```

- [ ] **Step 2: Run red test**

Run: `./.venv/bin/pytest tests/test_streamlit_services.py -q`
Expected: FAIL because service does not use supervisor output.

- [ ] **Step 3: Implement service support**

Implementation points:
- Import `modules.run_supervisor`.
- Dual-version path uses worker specs and supervisor.
- Load bundles from version output dirs.
- Return `supervisor_summary` at top level and under `dual_version`.
- Preserve existing single-version service path.

- [ ] **Step 4: Run service tests**

Run: `./.venv/bin/pytest tests/test_streamlit_services.py -q`
Expected: PASS.

---

### Task 6: Minimal UI Worker Status Panel

**Files:**
- Modify: `app/streamlit_app.py`
- Test: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write failing pure-function UI tests**

Add pure helper tests, not browser tests:

```python
def test_build_worker_status_rows_surfaces_b_reference_status():
    result = {
        "status": "partial_success",
        "supervisor_summary": {
            "state": "partial_success",
            "workers": {
                "version_a": {"state": "success", "role": "primary", "used_for_final_verdict": True},
                "version_b": {
                    "state": "timed_out",
                    "role": "experimental",
                    "reference_status": "not_available",
                    "reference_reason": "version_b timed out after 1800 seconds",
                    "current_step": 6,
                    "current_stage": "copy_generation",
                    "current_field": "visible_copy_batch",
                },
            },
            "hybrid_status": "unavailable",
            "hybrid_unavailable_reason": "version_b_timed_out",
        },
    }

    rows = build_worker_status_rows(result)

    assert any(row["版本"] == "version_b" and row["参考价值"] == "不可用" for row in rows)
    assert any("visible_copy_batch" in row["当前位置"] for row in rows if row["版本"] == "version_b")
```

- [ ] **Step 2: Run red test**

Run: `./.venv/bin/pytest tests/test_streamlit_app.py -q`
Expected: FAIL because `build_worker_status_rows` is missing.

- [ ] **Step 3: Implement helper and minimal render block**

Implement:

```python
def build_worker_status_rows(result: dict) -> list[dict]: ...
def _translate_worker_state(state: str) -> str: ...
def _translate_reference_status(status: str) -> str: ...
```

Render in the result display area only if `supervisor_summary` exists.

- [ ] **Step 4: Run UI tests**

Run: `./.venv/bin/pytest tests/test_streamlit_app.py -q`
Expected: PASS.

---

### Task 7: Final Verification and Live Smoke

**Files:**
- Potentially update `docs/superpowers/plans/INDEX.md` status only if needed.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
./.venv/bin/pytest \
  tests/test_run_worker.py \
  tests/test_run_supervisor.py \
  tests/integration/test_run_pipeline_wrapper.py \
  tests/test_streamlit_services.py \
  tests/test_streamlit_app.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `./.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 3: Run H91lite live supervisor validation**

Run:

```bash
RUN_ID="r48_version_b_supervisor_live_$(date +%Y%m%d_%H%M%S)"
./.venv/bin/python run_pipeline.py --product H91lite --market US --run-id "$RUN_ID" --dual-version --fresh
```

Expected:
- `final_readiness_verdict.json` exists.
- `supervisor_summary.json` exists.
- `version_a/worker_status.json` exists and is terminal.
- `version_b/worker_status.json` exists and is terminal.
- If B failed/timed_out, `hybrid/unavailable.json` exists and `hybrid/generated_copy.json` does not.
- If B succeeded, normal hybrid artifacts may exist.
- `LISTING_READY.md` or `LISTING_REVIEW_REQUIRED.md` exists according to launch gate.

- [ ] **Step 4: Summarize remaining listing quality issues**

Report whether live output was `LISTING_READY` or `LISTING_REVIEW_REQUIRED`. Do not claim listing quality is fixed unless launch gate passes.

---

## Self-Review Checklist

- Spec coverage: Tasks cover worker status, subprocess supervisor, deadlines, partial_success, timeout termination, hybrid unavailable, service return, minimal UI, tests, and live smoke.
- Placeholder scan: No TBD/TODO placeholders; each task has concrete commands and expected artifacts.
- Type consistency: `worker_status.json`, `supervisor_summary.json`, `reference_status`, `current_step`, `current_stage`, `current_field`, and `hybrid/unavailable.json` names are consistent across tasks.
