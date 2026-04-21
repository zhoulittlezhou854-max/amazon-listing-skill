from pathlib import Path

from tools import streamlit_launcher


def test_build_streamlit_command_uses_repo_venv_and_app_paths(tmp_path: Path):
    command = streamlit_launcher.build_streamlit_command(tmp_path, "127.0.0.1", 8501)

    assert command[0] == str(tmp_path / ".venv" / "bin" / "streamlit")
    assert command[1:3] == ["run", str(tmp_path / "app" / "streamlit_app.py")]
    assert "--server.address" in command
    assert "127.0.0.1" in command
    assert "8501" in command


def test_read_pid_returns_none_for_invalid_content(tmp_path: Path):
    pid_path = tmp_path / "streamlit_console.pid"
    pid_path.write_text("not-a-pid", encoding="utf-8")

    assert streamlit_launcher.read_pid(pid_path) is None


def test_runtime_state_cleans_up_stale_pid_file(tmp_path: Path):
    pid_path = streamlit_launcher.pid_file(tmp_path)
    pid_path.write_text("999999", encoding="utf-8")

    state = streamlit_launcher.runtime_state(tmp_path, "127.0.0.1", 8501)

    assert state["running"] is False
    assert state["pid"] is None
    assert not pid_path.exists()
