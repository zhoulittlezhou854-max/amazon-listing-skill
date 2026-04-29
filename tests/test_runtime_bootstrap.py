from pathlib import Path

from tools import runtime_bootstrap as rb


def _make_venv(tmp_path: Path) -> Path:
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")
    return python_path


def test_should_reexec_when_system_python_and_local_venv_present(tmp_path):
    _make_venv(tmp_path)

    assert rb.should_reexec_to_project_venv(
        tmp_path,
        environ={},
        executable="/usr/bin/python3",
        prefix="/usr",
        base_prefix="/usr",
    ) is True


def test_should_not_reexec_when_already_in_venv(tmp_path):
    python_path = _make_venv(tmp_path)

    assert rb.should_reexec_to_project_venv(
        tmp_path,
        environ={},
        executable=str(python_path),
        prefix=str(tmp_path / ".venv"),
        base_prefix="/usr",
    ) is False


def test_should_not_reexec_when_skip_flag_is_set(tmp_path):
    _make_venv(tmp_path)

    assert rb.should_reexec_to_project_venv(
        tmp_path,
        environ={"AMAZON_LISTING_SKIP_VENV_BOOTSTRAP": "1"},
        executable="/usr/bin/python3",
        prefix="/usr",
        base_prefix="/usr",
    ) is False


def test_ensure_project_venv_execs_with_marker(tmp_path, monkeypatch):
    python_path = _make_venv(tmp_path)
    monkeypatch.setattr(rb.sys, "argv", ["run_pipeline.py", "--product", "H91lite"])
    monkeypatch.setattr(rb.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(rb.sys, "prefix", "/usr")
    monkeypatch.setattr(rb.sys, "base_prefix", "/usr")
    monkeypatch.delenv("AMAZON_LISTING_VENV_BOOTSTRAPPED", raising=False)
    monkeypatch.delenv("AMAZON_LISTING_SKIP_VENV_BOOTSTRAP", raising=False)

    captured = {}

    def _fake_execve(executable, argv, env):
        captured["executable"] = executable
        captured["argv"] = argv
        captured["env"] = env
        raise SystemExit(0)

    monkeypatch.setattr(rb.os, "execve", _fake_execve)

    try:
        rb.ensure_project_venv(tmp_path)
    except SystemExit:
        pass

    assert captured["executable"] == str(python_path)
    assert captured["argv"][0] == str(python_path)
    assert captured["argv"][1:] == ["run_pipeline.py", "--product", "H91lite"]
    assert captured["env"]["AMAZON_LISTING_VENV_BOOTSTRAPPED"] == "1"


def test_main_module_does_not_reexec_project_venv_at_import_time():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    before_main_guard = source.split('if __name__ == "__main__":', 1)[0]

    assert "ensure_project_venv(Path(__file__).resolve().parent)" not in before_main_guard
