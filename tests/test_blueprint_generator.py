from types import SimpleNamespace

import pytest

from modules import blueprint_generator
from modules.llm_client import LLMClientUnavailable


def _preprocessed():
    return SimpleNamespace(
        language="English",
        real_vocab=None,
        canonical_core_selling_points=["1080P HD", "150 minutes runtime"],
        core_selling_points=["1080P HD", "150 minutes runtime"],
        attribute_data=SimpleNamespace(data={"weight": "35g"}),
        raw_human_insights="commuter POV use",
        feedback_context={},
    )


class TestCallBlueprintLlm:
    def test_uses_v3_primary_model(self, monkeypatch):
        calls = []

        def _fake_stream(client, messages, model, timeout):
            calls.append({"model": model, "timeout": timeout, "messages": messages})
            return '{"bullets":[]}'

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)
        result = blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, [])

        assert result == '{"bullets":[]}'
        assert calls[0]["model"] == "deepseek-chat"

    def test_falls_back_to_r1_when_v3_fails(self, monkeypatch):
        calls = []

        def _fake_stream(client, messages, model, timeout):
            calls.append(model)
            if len(calls) == 1:
                raise Exception("v3 timeout")
            return '{"bullets":[]}'

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)
        result = blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, [])

        assert result == '{"bullets":[]}'
        assert calls == ["deepseek-chat", "deepseek-reasoner"]

    def test_streaming_response_joined_correctly(self):
        class _Delta:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, content):
                self.delta = _Delta(content)

        class _Chunk:
            def __init__(self, content):
                self.choices = [_Choice(content)]

        class _Completions:
            def create(self, **kwargs):
                assert kwargs["stream"] is True
                return [_Chunk("Hello"), _Chunk(" world")]

        class _Chat:
            def __init__(self):
                self.completions = _Completions()

        class _Client:
            def __init__(self):
                self.chat = _Chat()

        assert blueprint_generator._stream_llm_response(_Client(), [], "deepseek-chat", 30) == "Hello world"

    def test_both_fail_raises_last_exception(self, monkeypatch):
        def _fake_stream(client, messages, model, timeout):
            raise RuntimeError(f"{model} failed")

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)

        with pytest.raises(RuntimeError, match="deepseek-reasoner failed"):
            blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, [])

    def test_audit_log_records_retry_on_v3_failure(self, monkeypatch):
        audit_log = []

        def _fake_stream(client, messages, model, timeout):
            if model == "deepseek-chat":
                raise Exception("v3 timeout")
            return '{"bullets":[]}'

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)
        blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, audit_log)

        assert audit_log[0]["action"] == "llm_retry"
        assert audit_log[0]["model"] == "deepseek-chat"
        assert "v3 timeout" in audit_log[0]["error"]


def test_generate_blueprint_r1_uses_reasoner_override(monkeypatch):
    class _Client:
        def __init__(self):
            self.active_model = "deepseek-chat"
            self._meta = {"configured_model": "deepseek-chat"}

        @property
        def response_metadata(self):
            return dict(self._meta)

        def _record_response_meta(self, **kwargs):
            self._meta = {"configured_model": kwargs.get("configured_model", "deepseek-chat")}

        @property
        def _client(self):
            class _Delta:
                def __init__(self, content):
                    self.content = content

            class _Choice:
                def __init__(self, content):
                    self.delta = _Delta(content)

            class _Chunk:
                def __init__(self, content):
                    self.choices = [_Choice(content)]

            class _Completions:
                def create(self, **kwargs):
                    assert kwargs["model"] == "deepseek-chat"
                    return [
                        _Chunk(
                            '{"bullets": ['
                            '{"bullet_index": 1, "theme": "Runtime", "assigned_l2_keywords": [], "mandatory_elements": [],'
                            '"scenes": [], "capabilities": [], "accessories": [], "persona": "commuter",'
                            '"pain_point": "battery anxiety", "buying_trigger": "all-day use", "proof_angle": "150 minutes",'
                            '"priority": "P0", "slot_directive": "numeric proof"}'
                            ']}'
                        )
                    ]

            class _Chat:
                def __init__(self):
                    self.completions = _Completions()

            return SimpleNamespace(chat=_Chat())

    monkeypatch.setattr(blueprint_generator, "get_llm_client", lambda: _Client())

    blueprint = blueprint_generator.generate_blueprint_r1(
        preprocessed_data=_preprocessed(),
        writing_policy={},
        intent_graph={},
    )

    assert blueprint["llm_model"] == "deepseek-chat"
    assert blueprint["bullets"][0]["theme"] == "Runtime"


def test_generate_blueprint_r1_attaches_debug_context_on_failure(monkeypatch):
    class _Client:
        def __init__(self):
            self.active_model = "deepseek-chat"
            self._meta = {"configured_model": "deepseek-reasoner", "error": "timed_out"}

        @property
        def response_metadata(self):
            return dict(self._meta)

        def _record_response_meta(self, **kwargs):
            self._meta = {
                "configured_model": kwargs.get("configured_model", ""),
                "error": kwargs.get("error", ""),
            }

        @property
        def _client(self):
            class _Completions:
                def create(self, **kwargs):
                    raise LLMClientUnavailable("r1 blueprint timeout", error_code="timed_out", retryable=True)

            class _Chat:
                def __init__(self):
                    self.completions = _Completions()

            return SimpleNamespace(chat=_Chat())

    monkeypatch.setattr(blueprint_generator, "get_llm_client", lambda: _Client())

    with pytest.raises(RuntimeError, match="Bullet blueprint generation failed") as exc_info:
        blueprint_generator.generate_blueprint_r1(
            preprocessed_data=_preprocessed(),
            writing_policy={},
            intent_graph={},
        )

    debug_context = getattr(exc_info.value, "debug_context", {}) or {}
    assert debug_context.get("field") == "bullet_blueprint"
    assert debug_context.get("request_payload", {}).get("field") == "bullet_blueprint"
    assert "system_prompt" in debug_context
    assert debug_context.get("llm_response_meta", {}).get("configured_model") == "deepseek-reasoner"
