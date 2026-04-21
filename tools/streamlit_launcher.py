#!/usr/bin/env python3
"""Manage the local Streamlit console as a background process."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8501
STARTUP_WAIT_SECONDS = 2.0
SHUTDOWN_WAIT_SECONDS = 3.0


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def debug_dir(root: Path) -> Path:
    path = root / "output" / "debug"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_file(root: Path) -> Path:
    return debug_dir(root) / "streamlit_console.pid"


def log_file(root: Path) -> Path:
    return debug_dir(root) / "streamlit_console.log"


def streamlit_app_path(root: Path) -> Path:
    return root / "app" / "streamlit_app.py"


def streamlit_binary(root: Path) -> Path:
    return root / ".venv" / "bin" / "streamlit"


def build_streamlit_command(root: Path, host: str, port: int) -> list[str]:
    return [
        str(streamlit_binary(root)),
        "run",
        str(streamlit_app_path(root)),
        "--server.headless",
        "true",
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
    ]


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    try:
        return int(content)
    except ValueError:
        return None


def is_process_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cleanup_stale_pid(root: Path) -> None:
    path = pid_file(root)
    pid = read_pid(path)
    if pid is not None and not is_process_alive(pid):
        path.unlink(missing_ok=True)


def runtime_state(root: Path, host: str, port: int) -> dict[str, object]:
    cleanup_stale_pid(root)
    pid = read_pid(pid_file(root))
    return {
        "running": is_process_alive(pid),
        "pid": pid,
        "url": f"http://{host}:{port}",
        "pid_file": str(pid_file(root)),
        "log_file": str(log_file(root)),
    }


def print_state(state: dict[str, object]) -> None:
    status = "running" if state["running"] else "stopped"
    print(f"Streamlit console is {status}.")
    print(f"URL: {state['url']}")
    print(f"PID: {state['pid'] or '-'}")
    print(f"PID file: {state['pid_file']}")
    print(f"Log file: {state['log_file']}")


def start_server(root: Path, host: str, port: int) -> int:
    state = runtime_state(root, host, port)
    if state["running"]:
        print("Streamlit console is already running.")
        print_state(state)
        return 0

    binary = streamlit_binary(root)
    app_path = streamlit_app_path(root)
    if not binary.exists():
        print(f"Missing Streamlit binary: {binary}", file=sys.stderr)
        return 1
    if not app_path.exists():
        print(f"Missing Streamlit app: {app_path}", file=sys.stderr)
        return 1

    with log_file(root).open("ab") as log_handle:
        process = subprocess.Popen(
            build_streamlit_command(root, host, port),
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    time.sleep(STARTUP_WAIT_SECONDS)
    if process.poll() is not None:
        print("Streamlit console failed to stay running.", file=sys.stderr)
        tail = log_file(root).read_text(encoding="utf-8", errors="replace")[-4000:]
        if tail.strip():
            print("--- recent log ---", file=sys.stderr)
            print(tail, file=sys.stderr)
        return 1

    pid_file(root).write_text(str(process.pid), encoding="utf-8")
    print("Streamlit console started.")
    print_state(runtime_state(root, host, port))
    return 0


def stop_server(root: Path) -> int:
    cleanup_stale_pid(root)
    path = pid_file(root)
    pid = read_pid(path)
    if pid is None or not is_process_alive(pid):
        path.unlink(missing_ok=True)
        print("Streamlit console is already stopped.")
        return 0

    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + SHUTDOWN_WAIT_SECONDS
    while time.time() < deadline:
        if not is_process_alive(pid):
            path.unlink(missing_ok=True)
            print("Streamlit console stopped.")
            return 0
        time.sleep(0.1)

    os.kill(pid, signal.SIGKILL)
    path.unlink(missing_ok=True)
    print("Streamlit console was force-stopped.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the local Streamlit console.")
    parser.add_argument("command", choices=["start", "stop", "restart", "status"])
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Streamlit bind host, default {DEFAULT_HOST}.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Streamlit port, default {DEFAULT_PORT}.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    if args.command == "start":
        return start_server(root, args.host, args.port)
    if args.command == "stop":
        return stop_server(root)
    if args.command == "restart":
        stop_server(root)
        return start_server(root, args.host, args.port)

    print_state(runtime_state(root, args.host, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
