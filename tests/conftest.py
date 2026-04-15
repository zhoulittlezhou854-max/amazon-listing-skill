from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolate_llm_runtime(monkeypatch):
    llm_env_vars = [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_WIRE_API",
        "OPENAI_COMPAT_API_KEY",
        "OPENAI_COMPAT_BASE_URL",
        "OPENAI_COMPAT_MODEL",
        "OPENAI_COMPAT_VERIFY_SSL",
        "OPENAI_COMPAT_DISABLE_CODEX_FALLBACK",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_BASE",
        "DEEPSEEK_MODEL",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "CODEX_LLM_MODEL",
    ]
    for var in llm_env_vars:
        monkeypatch.delenv(var, raising=False)

    try:
        from modules import llm_client
    except Exception:
        yield
        return

    monkeypatch.setattr(llm_client, "RUNTIME_LLM_CONFIG", {}, raising=False)
    monkeypatch.setattr(llm_client, "RUNTIME_FORCE_LIVE", False, raising=False)
    monkeypatch.setattr(llm_client, "_LLM_CLIENT_SINGLETON", None, raising=False)
    yield
