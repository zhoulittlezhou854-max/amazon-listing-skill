#!/usr/bin/env python3
"""Helpers for re-executing entrypoints inside the project virtualenv."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

_BOOTSTRAP_MARKER = "AMAZON_LISTING_VENV_BOOTSTRAPPED"
_SKIP_BOOTSTRAP = "AMAZON_LISTING_SKIP_VENV_BOOTSTRAP"


def _project_venv_python(project_root: Path) -> Path:
    return project_root / ".venv" / "bin" / "python"


def _running_in_virtualenv(*, executable: str | None = None, prefix: str | None = None, base_prefix: str | None = None) -> bool:
    exe = Path(executable or sys.executable).resolve()
    if ".venv" in exe.parts:
        return True
    return str(prefix or sys.prefix) != str(base_prefix or getattr(sys, "base_prefix", sys.prefix))


def should_reexec_to_project_venv(
    project_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
    executable: str | None = None,
    prefix: str | None = None,
    base_prefix: str | None = None,
) -> bool:
    env = environ or os.environ
    if env.get(_SKIP_BOOTSTRAP) == "1":
        return False
    if env.get(_BOOTSTRAP_MARKER) == "1":
        return False
    if _running_in_virtualenv(executable=executable, prefix=prefix, base_prefix=base_prefix):
        return False
    return _project_venv_python(project_root).exists()


def ensure_project_venv(project_root: Path, argv: Sequence[str] | None = None) -> None:
    if not should_reexec_to_project_venv(project_root):
        return
    venv_python = _project_venv_python(project_root)
    env = os.environ.copy()
    env[_BOOTSTRAP_MARKER] = "1"
    command = [str(venv_python), *(list(argv) if argv is not None else sys.argv)]
    print(f"[runtime] Re-executing with {venv_python}", file=sys.stderr)
    os.execve(str(venv_python), command, env)
