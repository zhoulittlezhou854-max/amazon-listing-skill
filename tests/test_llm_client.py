import json

import pytest

from modules import llm_client


def test_extract_openai_compatible_text_reads_nonstandard_content_root():
    payload = {
        "id": "resp_123",
        "model": "gpt-5.4",
        "status": "completed",
        "output": [],
        "content": [
            {
                "type": "output_text",
                "text": "READY",
            }
        ],
    }

    text, state = llm_client._extract_openai_compatible_text(payload)

    assert text == "READY"
    assert state == "completed"


def test_extract_openai_compatible_text_reads_chat_style_choices():
    payload = {
        "id": "chatcmpl_123",
        "model": "gpt-5.4",
        "choices": [
            {
                "message": {
                    "content": "Bonjour",
                }
            }
        ],
    }

    text, state = llm_client._extract_openai_compatible_text(payload)

    assert text == "Bonjour"
    assert state == "completed"


def test_extract_openai_compatible_text_marks_empty_output_array():
    payload = {
        "id": "resp_456",
        "model": "gpt-5.4",
        "status": "completed",
        "output": [],
    }

    text, state = llm_client._extract_openai_compatible_text(payload)

    assert text == ""
    assert state == "empty_output_array"


def test_extract_openai_compatible_text_marks_no_message_in_output():
    payload = {
        "id": "resp_789",
        "model": "gpt-5.4",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "tool_call", "name": "shell"},
        ],
    }

    text, state = llm_client._extract_openai_compatible_text(payload)

    assert text == ""
    assert state == "no_message_in_output"


def test_deepseek_config_becomes_primary_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "DEEPSEEK_API_KEY",
            "request_timeout_seconds": 45,
            "force_live_llm": False,
        }
    )

    client = llm_client.LLMClient()

    assert client.provider_label == "deepseek"
    assert client.base_url == "https://api.deepseek.com/v1"
    assert client.active_model == "deepseek-chat"


def test_call_llm_uses_deepseek_as_primary_before_optional_fallback(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "DEEPSEEK_API_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    calls = []

    def _fake_deepseek(system_prompt, payload, temperature, *, timeout_seconds):
        calls.append("deepseek")
        return "READY"

    monkeypatch.setattr(client, "_call_deepseek", _fake_deepseek)

    text = client._call_llm("Reply with exactly READY.", {"probe": "deepseek_primary"}, 0.0)

    assert text == "READY"
    assert calls == ["deepseek"]


def test_openai_compatible_responses_falls_back_to_chat_when_packet_is_empty_for_supported_provider(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://compat.example.com/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = None

    calls = []

    def _fake_post(url, body, headers, timeout=60, verify_ssl=True):
        calls.append(url)
        if url.endswith("/responses"):
            return {
                "id": "resp_123",
                "model": "gpt-5.4",
                "status": "completed",
                "output": [],
            }, {}
        return {
            "id": "chatcmpl_123",
            "model": "gpt-5.4",
            "choices": [
                {
                    "message": {
                        "content": "Recovered through chat fallback",
                    }
                }
            ],
        }, {}

    monkeypatch.setattr(llm_client, "_http_post_json", _fake_post)

    text = client.generate_text("Reply with exactly READY.", {"probe": "fallback"}, temperature=0.0)

    assert text == "Recovered through chat fallback"
    assert calls[0].endswith("/responses")
    assert calls[1].endswith("/chat/completions")
    assert client.response_metadata["wire_api"] == "chat/completions"


def test_openai_compatible_gptclub_skips_chat_fallback_and_uses_codex_exec(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {"codex_bin": "/usr/local/bin/codex"}

    calls = []

    def _fake_post(url, body, headers, timeout=60, verify_ssl=True):
        calls.append(url)
        return {
            "id": "resp_123",
            "model": "gpt-5.4",
            "status": "completed",
            "output": [],
        }, {}

    monkeypatch.setattr(llm_client, "_http_post_json", _fake_post)
    monkeypatch.setattr(
        client,
        "_call_codex_exec",
        lambda system_prompt, payload, temperature, *, timeout_seconds: "Recovered through codex exec",
    )

    text = client.generate_text("Reply with exactly READY.", {"probe": "fallback"}, temperature=0.0)

    assert text == "Recovered through codex exec"
    assert calls == ["https://api.gptclubapi.xyz/openai/responses"]
    assert client.response_metadata["wire_api"] == "codex_exec"


def test_openai_compatible_gptclub_uses_http_fallback_before_codex(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
            "http_fallback_provider": {
                "base_url": "https://api.gptclubapi.xyz/v1",
                "api_key_env": "CRS_OAI_KEY",
                "model": "gpt-4o",
                "timeout_seconds": 30,
            },
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {"codex_bin": "/usr/local/bin/codex"}

    calls = []

    def _fake_post(url, body, headers, timeout=60, verify_ssl=True):
        calls.append(url)
        return {
            "id": "resp_123",
            "model": "gpt-5.4",
            "status": "completed",
            "output": [],
        }, {}

    monkeypatch.setattr(llm_client, "_http_post_json", _fake_post)
    monkeypatch.setattr(client, "_call_http_fallback", lambda *args, **kwargs: "Recovered through http fallback")
    monkeypatch.setattr(
        client,
        "_call_codex_exec",
        lambda system_prompt, payload, temperature, *, timeout_seconds: pytest.fail("codex should not run"),
    )

    text = client.generate_text("Reply with exactly READY.", {"probe": "fallback"}, temperature=0.0)

    assert text == "Recovered through http fallback"
    assert calls == ["https://api.gptclubapi.xyz/openai/responses"]


def test_http_fallback_uses_request_timeout_budget_when_larger_than_provider_default(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
            "http_fallback_provider": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key_env": "CRS_OAI_KEY",
                "model": "deepseek-chat",
                "timeout_seconds": 30,
            },
        }
    )
    client = llm_client.LLMClient()
    seen = {}

    class _FakeHeaders(dict):
        def get_content_charset(self):
            return "utf-8"

    class _FakeResponse:
        headers = _FakeHeaders()

        def read(self):
            return json.dumps(
                {
                    "id": "chatcmpl_123",
                    "model": "deepseek-chat",
                    "choices": [{"message": {"content": "Recovered through http fallback"}}],
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0, context=None):
        seen["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", _fake_urlopen)

    text = client._call_http_fallback(
        "Reply with exactly READY.",
        {"probe": "fallback", "_request_timeout_seconds": 180},
        0.0,
    )

    assert text == "Recovered through http fallback"
    assert seen["timeout"] == 180


def test_healthcheck_tolerates_reachable_gateway_with_missing_output_text(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": True,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = None

    def _fake_post(url, body, headers, timeout=60, verify_ssl=True):
        if url.endswith("/responses"):
            return {
                "id": "resp_456",
                "model": "gpt-5.4",
                "status": "completed",
                "output": [],
            }, {"x-request-id": "req_123"}
        raise RuntimeError("HTTPError 404: route not found")

    monkeypatch.setattr(llm_client, "_http_post_json", _fake_post)

    healthcheck = client.healthcheck()

    assert healthcheck["ok"] is False
    assert healthcheck["degraded_ok"] is True
    assert healthcheck["error"] == "empty_output_array"


def test_openai_compatible_uses_isolated_codex_home_when_sessions_dir_unavailable(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-test-home")
    monkeypatch.setattr(llm_client.shutil, "which", lambda name: "/usr/local/bin/codex" if name == "codex" else None)
    monkeypatch.setattr(llm_client, "_codex_sessions_accessible", lambda: False)

    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )

    client = llm_client.LLMClient()

    assert client._codex_exec_fallback is not None
    assert client._codex_exec_fallback["codex_home"] == "/tmp/codex-test-home"


def test_generate_text_raises_retryable_missing_output_error(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = None

    def _fake_call(system_prompt, payload, temperature):
        client._last_response_meta = {
            "error": "missing_output_text",
            "response_state": "missing_output_text",
        }
        return None

    monkeypatch.setattr(client, "_call_llm", _fake_call)

    with pytest.raises(llm_client.LLMClientUnavailable) as excinfo:
        client.generate_text("Reply with exactly READY.", {"probe": "retryable"}, temperature=0.0)

    assert excinfo.value.error_code == "missing_output_text"
    assert excinfo.value.retryable is True
    assert "missing_output_text" in str(excinfo.value)


def test_generate_text_marks_empty_output_array_non_retryable(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = None

    def _fake_call(system_prompt, payload, temperature):
        client._last_response_meta = {
            "error": "empty_output_array",
            "response_state": "empty_output_array",
        }
        return None

    monkeypatch.setattr(client, "_call_llm", _fake_call)

    with pytest.raises(llm_client.LLMClientUnavailable) as excinfo:
        client.generate_text("Reply with exactly READY.", {"probe": "non_retryable"}, temperature=0.0)

    assert excinfo.value.error_code == "empty_output_array"
    assert excinfo.value.retryable is False


def test_call_http_fallback_uses_chat_completions_and_records_metadata(monkeypatch):
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
            "http_fallback_provider": {
                "base_url": "https://api.gptclubapi.xyz/v1",
                "api_key": "fallback-key",
                "model": "gpt-4o",
                "timeout_seconds": 30,
            },
        }
    )
    client = llm_client.LLMClient()
    captured = {}

    class _FakeHeaders(dict):
        def get_content_charset(self):
            return "utf-8"

    class _FakeResponse:
        def __init__(self):
            self.headers = _FakeHeaders({"x-request-id": "req_fallback"})

        def read(self):
            return b'{\"id\":\"chatcmpl_123\",\"model\":\"gpt-4o\",\"choices\":[{\"message\":{\"content\":\"HTTP fallback READY\"}}]}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout, context=None):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["timeout"] = timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", _fake_urlopen)

    text = client._call_http_fallback("System prompt", {"probe": "http"}, 0.15)

    assert text == "HTTP fallback READY"
    assert captured["url"] == "https://api.gptclubapi.xyz/v1/chat/completions"
    assert captured["timeout"] == 30
    assert captured["body"]["model"] == "gpt-4o"
    assert client.response_metadata["wire_api"] == "chat/completions"
    assert client.response_metadata["provider"] == "http_fallback"


def test_call_llm_prefers_http_fallback_before_codex_exec(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
            "http_fallback_provider": {
                "base_url": "https://api.gptclubapi.xyz/v1",
                "api_key_env": "CRS_OAI_KEY",
                "model": "gpt-4o",
                "timeout_seconds": 30,
            },
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {"codex_bin": "/usr/local/bin/codex"}
    calls = []

    def _fake_openai(system_prompt, payload, temperature, *, timeout_seconds):
        calls.append("openai")
        return None

    def _fake_http(system_prompt, payload, temperature, *, timeout_seconds=None):
        calls.append("http")
        return "Recovered through http fallback"

    monkeypatch.setattr(client, "_call_openai_compatible", _fake_openai)
    monkeypatch.setattr(client, "_call_http_fallback", _fake_http)
    monkeypatch.setattr(
        client,
        "_call_codex_exec",
        lambda system_prompt, payload, temperature, *, timeout_seconds: pytest.fail("codex should not run"),
    )

    text = client._call_llm("Reply with exactly READY.", {"probe": "order"}, 0.0)

    assert text == "Recovered through http fallback"
    assert calls == ["openai", "http"]


def test_probe_http_fallback_returns_false_when_provider_unreachable(monkeypatch):
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
            "http_fallback_provider": {
                "base_url": "https://api.gptclubapi.xyz/v1",
                "api_key": "fallback-key",
                "model": "gpt-4o",
                "timeout_seconds": 5,
            },
        }
    )
    client = llm_client.LLMClient()
    monkeypatch.setattr(client, "_call_http_fallback", lambda *args, **kwargs: None)

    assert client.probe_http_fallback() is False


def test_call_llm_uses_openai_compatible_before_codex_exec(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {"codex_bin": "/usr/local/bin/codex"}
    calls = []

    def _fake_openai(system_prompt, payload, temperature, *, timeout_seconds):
        calls.append("openai")
        return None

    def _fake_codex(system_prompt, payload, temperature, *, timeout_seconds):
        calls.append("codex")
        return "Recovered through codex exec"

    monkeypatch.setattr(client, "_call_openai_compatible", _fake_openai)
    monkeypatch.setattr(client, "_call_codex_exec", _fake_codex)

    text = client._call_llm("Reply with exactly READY.", {"probe": "order"}, 0.0)

    assert text == "Recovered through codex exec"
    assert calls == ["openai", "codex"]


def test_openai_compatible_empty_packet_falls_back_to_codex_exec(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {"codex_bin": "/usr/local/bin/codex"}

    def _fake_post(url, body, headers, timeout=60, verify_ssl=True):
        return {
            "id": "resp_123",
            "model": "gpt-5.4",
            "status": "completed",
            "output": [],
        }, {}

    monkeypatch.setattr(llm_client, "_http_post_json", _fake_post)
    monkeypatch.setattr(client, "_call_openai_compatible_chat_fallback", lambda **kwargs: None)
    monkeypatch.setattr(
        client,
        "_call_codex_exec",
        lambda system_prompt, payload, temperature, *, timeout_seconds: "Recovered through codex exec",
    )

    text = client._call_openai_compatible(
        "Reply with exactly READY.",
        {"probe": "fallback"},
        0.0,
        timeout_seconds=30,
    )

    assert text == "Recovered through codex exec"
    assert client.response_metadata["wire_api"] == "codex_exec"


def test_codex_exec_timeout_budget_adds_process_overhead():
    assert llm_client._codex_exec_timeout_budget(75) == 120
    assert llm_client._codex_exec_timeout_budget(90) == 135


def test_codex_exec_passes_prompt_as_cli_argument(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {
        "codex_bin": "/usr/local/bin/codex",
        "model": "gpt-5.4",
        "sandbox": "workspace-write",
        "reasoning_effort": "low",
        "workdir": "/tmp",
        "codex_home": "/tmp/codex-home-test",
    }
    captured = {}

    def _fake_run(command, *, env, capture_output, text, timeout, cwd):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        captured["timeout"] = timeout
        out_file = command[command.index("-o") + 1]
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write("READY")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(llm_client.subprocess, "run", _fake_run)
    monkeypatch.setattr(llm_client.os, "makedirs", lambda path, exist_ok=True: None)

    text = client._call_codex_exec("Reply with exactly READY.", {"probe": "codex_arg"}, 0.0, timeout_seconds=30)

    assert text == "READY"
    assert "--json" not in captured["command"]
    assert "-o" in captured["command"]
    assert captured["command"][-1].startswith("You are a text-generation backend.")


def test_codex_exec_omits_model_override_without_explicit_codex_model(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {
        "codex_bin": "/usr/local/bin/codex",
        "model": "",
        "sandbox": "workspace-write",
        "reasoning_effort": "low",
        "workdir": "/tmp",
        "codex_home": "/tmp/codex-home-test",
    }
    captured = {}

    def _fake_run(command, *, env, capture_output, text, timeout, cwd):
        captured["command"] = command
        out_file = command[command.index("-o") + 1]
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write("READY")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(llm_client.subprocess, "run", _fake_run)
    monkeypatch.setattr(llm_client.os, "makedirs", lambda path, exist_ok=True: None)

    text = client._call_codex_exec("Reply with exactly READY.", {"probe": "codex_arg"}, 0.0, timeout_seconds=30)

    assert text == "READY"
    assert "-m" not in captured["command"]


def test_codex_exec_omits_reasoning_override_without_explicit_setting(monkeypatch):
    monkeypatch.setenv("CRS_OAI_KEY", "test-key")
    llm_client.configure_llm_runtime(
        {
            "provider": "openai_compatible",
            "model": "gpt-5.4",
            "base_url": "https://api.gptclubapi.xyz/openai",
            "wire_api": "responses",
            "api_key_env": "CRS_OAI_KEY",
            "force_live_llm": False,
        }
    )
    client = llm_client.LLMClient()
    client._codex_exec_fallback = {
        "codex_bin": "/usr/local/bin/codex",
        "model": "",
        "sandbox": "workspace-write",
        "reasoning_effort": "",
        "workdir": "/tmp",
        "codex_home": "/tmp/codex-home-test",
        "model_provider": "crs",
    }
    captured = {}

    def _fake_run(command, *, env, capture_output, text, timeout, cwd):
        captured["command"] = command
        out_file = command[command.index("-o") + 1]
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write("READY")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(llm_client.subprocess, "run", _fake_run)
    monkeypatch.setattr(llm_client.os, "makedirs", lambda path, exist_ok=True: None)

    text = client._call_codex_exec("Reply with exactly READY.", {"probe": "codex_arg"}, 0.0, timeout_seconds=30)

    assert text == "READY"
    assert not any("model_reasoning_effort" in str(part) for part in captured["command"])
    assert not any("model_provider" in str(part) for part in captured["command"])
