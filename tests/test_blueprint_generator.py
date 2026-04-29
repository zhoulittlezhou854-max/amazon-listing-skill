import json
from types import SimpleNamespace

import pytest

from modules import blueprint_generator
from modules import intent_translator
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


def test_blueprint_l2_keywords_use_qualified_bullet_metadata():
    tiered_keywords = {
        "l2": ["legacy l2 fallback"],
        "_metadata": {
            "body camera": {
                "keyword": "body camera",
                "quality_status": "qualified",
                "routing_role": "title",
                "traffic_tier": "L1",
                "search_volume": 20000,
            },
            "travel camera": {
                "keyword": "travel camera",
                "quality_status": "qualified",
                "routing_role": "bullet",
                "traffic_tier": "L2",
                "blue_ocean_score": 0.8,
            },
            "thumb camera": {
                "keyword": "thumb camera",
                "quality_status": "qualified",
                "routing_role": "bullet",
                "traffic_tier": "L3",
            },
            "blocked camera": {
                "keyword": "blocked camera",
                "quality_status": "rejected",
                "routing_role": "bullet",
            },
        },
    }

    assert blueprint_generator._derive_blueprint_l2_keywords(tiered_keywords) == [
        "travel camera",
        "thumb camera",
    ]


def test_blueprint_l2_keywords_fallback_to_legacy_l2_when_no_bullet_metadata():
    tiered_keywords = {
        "l2": ["legacy l2 fallback"],
        "_metadata": {
            "body camera": {
                "keyword": "body camera",
                "quality_status": "qualified",
                "routing_role": "title",
            },
        },
    }

    assert blueprint_generator._derive_blueprint_l2_keywords(tiered_keywords) == ["legacy l2 fallback"]


class TestCallBlueprintLlm:
    def test_uses_v3_primary_model(self, monkeypatch):
        calls = []

        def _fake_stream(client, messages, model, timeout):
            calls.append({"model": model, "timeout": timeout, "messages": messages})
            return '{"bullets":[]}'

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)
        result = blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, [])

        assert result == '{"bullets":[]}'
        assert calls[0]["model"] == "deepseek-v4-flash"

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
        assert calls == ["deepseek-v4-flash", "deepseek-v4-pro"]

    def test_override_model_skips_v3_primary_model(self, monkeypatch):
        calls = []

        def _fake_stream(client, messages, model, timeout):
            calls.append({"model": model, "timeout": timeout})
            return '{"bullets":[]}'

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)

        result = blueprint_generator._call_blueprint_llm(
            object(),
            [{"role": "system", "content": "x"}],
            180,
            None,
            [],
            override_model="deepseek-v4-pro",
        )

        assert result == '{"bullets":[]}'
        assert calls == [{"model": "deepseek-v4-pro", "timeout": 180}]

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

        assert blueprint_generator._stream_llm_response(_Client(), [], "deepseek-v4-flash", 30) == "Hello world"

    def test_both_fail_raises_last_exception(self, monkeypatch):
        def _fake_stream(client, messages, model, timeout):
            raise RuntimeError(f"{model} failed")

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)

        with pytest.raises(RuntimeError, match="deepseek-v4-pro failed"):
            blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, [])

    def test_audit_log_records_retry_on_v3_failure(self, monkeypatch):
        audit_log = []

        def _fake_stream(client, messages, model, timeout):
            if model == "deepseek-v4-flash":
                raise Exception("v3 timeout")
            return '{"bullets":[]}'

        monkeypatch.setattr(blueprint_generator, "_stream_llm_response", _fake_stream)
        blueprint_generator._call_blueprint_llm(object(), [{"role": "system", "content": "x"}], 30, None, audit_log)

        assert audit_log[0]["action"] == "llm_retry"
        assert audit_log[0]["model"] == "deepseek-v4-flash"
        assert "v3 timeout" in audit_log[0]["error"]


def test_generate_blueprint_r1_uses_reasoner_override(monkeypatch):
    class _Client:
        def __init__(self):
            self.active_model = "deepseek-v4-pro"
            self._meta = {"configured_model": "deepseek-v4-pro"}

        @property
        def response_metadata(self):
            return dict(self._meta)

        def _record_response_meta(self, **kwargs):
            self._meta = {"configured_model": kwargs.get("configured_model", "deepseek-v4-pro")}

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
                    assert kwargs["model"] == "deepseek-v4-pro"
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

    assert blueprint["llm_model"] == "deepseek-v4-pro"
    assert blueprint["bullets"][0]["theme"] == "Runtime"


def test_generate_blueprint_r1_uses_extended_timeout_budget(monkeypatch):
    captured = {}

    class _Client:
        active_model = "deepseek-v4-pro"

        @property
        def response_metadata(self):
            return {"configured_model": "deepseek-v4-pro"}

        def _record_response_meta(self, **kwargs):
            captured["configured_model"] = kwargs.get("configured_model")

    monkeypatch.setattr(blueprint_generator, "get_llm_client", lambda: _Client())
    monkeypatch.setattr(blueprint_generator, "_resolve_blueprint_stream_client", lambda llm: object())

    def _fake_call(stream_client, messages, timeout, fallback_model, audit_log, override_model=None):
        captured["timeout"] = timeout
        captured["override_model"] = override_model
        return (
            '{"bullets": ['
            '{"bullet_index": 1, "theme": "Runtime", "assigned_l2_keywords": [], "mandatory_elements": [], '
            '"scenes": [], "capabilities": [], "accessories": [], "persona": "commuter", '
            '"pain_point": "battery anxiety", "buying_trigger": "all-day use", "proof_angle": "150 minutes", '
            '"priority": "P0", "slot_directive": "numeric proof"}'
            ']}'
        )

    monkeypatch.setattr(blueprint_generator, "_call_blueprint_llm", _fake_call)

    blueprint = blueprint_generator.generate_blueprint_r1(
        preprocessed_data=_preprocessed(),
        writing_policy={},
        intent_graph={},
    )

    assert blueprint["llm_model"] == "deepseek-v4-pro"
    assert captured["timeout"] == 180
    assert captured["override_model"] == "deepseek-v4-pro"


def test_generate_blueprint_r1_attaches_debug_context_on_failure(monkeypatch):
    class _Client:
        def __init__(self):
            self.active_model = "deepseek-v4-flash"
            self._meta = {"configured_model": "deepseek-v4-pro", "error": "timed_out"}

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
    assert debug_context.get("llm_response_meta", {}).get("configured_model") == "deepseek-v4-pro"


def test_resolve_blueprint_stream_client_uses_openai_compatible_runtime(monkeypatch):
    captured = {}

    class _FakeOpenAI:
        def __init__(self, *, api_key, base_url):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setattr(blueprint_generator, "OpenAI", _FakeOpenAI)

    llm = SimpleNamespace(
        _client=None,
        _deepseek_key=None,
        _deepseek_base=None,
        _openai_compatible={
            "api_key": "gateway-key",
            "base_url": "https://api.gptclubapi.xyz/openai",
        },
    )

    stream_client = blueprint_generator._resolve_blueprint_stream_client(llm)

    assert isinstance(stream_client, _FakeOpenAI)
    assert captured == {
        "api_key": "gateway-key",
        "base_url": "https://api.gptclubapi.xyz/openai",
    }


def test_generate_blueprint_r1_falls_back_to_non_streaming_llm_when_stream_route_is_unavailable(monkeypatch):
    class _Client:
        def __init__(self):
            self.active_model = "deepseek-v4-pro"
            self._openai_compatible = {
                "api_key": "gateway-key",
                "base_url": "https://api.gptclubapi.xyz/openai",
            }
            self._meta = {"configured_model": "deepseek-v4-pro"}

        @property
        def response_metadata(self):
            return dict(self._meta)

        def _record_response_meta(self, **kwargs):
            self._meta = {
                "configured_model": kwargs.get("configured_model", "deepseek-v4-pro"),
                "error": kwargs.get("error", ""),
            }

        def generate_text(self, system_prompt, payload, temperature=0.0, override_model=None):
            assert override_model == "deepseek-v4-pro"
            assert payload.get("_disable_fallback") is True
            return (
                '{"bullets": ['
                '{"bullet_index": 1, "theme": "Runtime", "assigned_l2_keywords": [], "mandatory_elements": [],'
                '"scenes": [], "capabilities": [], "accessories": [], "persona": "commuter",'
                '"pain_point": "battery anxiety", "buying_trigger": "all-day use", "proof_angle": "150 minutes",'
                '"priority": "P0", "slot_directive": "numeric proof"},'
                '{"bullet_index": 2, "theme": "Mount", "assigned_l2_keywords": [], "mandatory_elements": [],'
                '"scenes": [], "capabilities": [], "accessories": [], "persona": "rider",'
                '"pain_point": "unstable clip", "buying_trigger": "hands-free capture", "proof_angle": "clip included",'
                '"priority": "P1", "slot_directive": "mounting proof"},'
                '{"bullet_index": 3, "theme": "Portability", "assigned_l2_keywords": [], "mandatory_elements": [],'
                '"scenes": [], "capabilities": [], "accessories": [], "persona": "traveler",'
                '"pain_point": "bulky gear", "buying_trigger": "grab-and-go", "proof_angle": "compact body",'
                '"priority": "P1", "slot_directive": "portable proof"},'
                '{"bullet_index": 4, "theme": "Usage guidance", "assigned_l2_keywords": [], "mandatory_elements": [],'
                '"scenes": [], "capabilities": [], "accessories": [], "persona": "new user",'
                '"pain_point": "wrong fit", "buying_trigger": "clear boundaries", "proof_angle": "best-use guidance",'
                '"priority": "P1", "slot_directive": "guidance"},'
                '{"bullet_index": 5, "theme": "Package", "assigned_l2_keywords": [], "mandatory_elements": [],'
                '"scenes": [], "capabilities": [], "accessories": [], "persona": "gift buyer",'
                '"pain_point": "missing accessories", "buying_trigger": "ready to use", "proof_angle": "bundle value",'
                '"priority": "P2", "slot_directive": "package trust"}'
                ']}'
            )

    monkeypatch.setattr(blueprint_generator, "get_llm_client", lambda: _Client())
    monkeypatch.setattr(
        blueprint_generator,
        "_call_blueprint_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Error code: 404 - route /openai/chat/completions not found")
        ),
    )

    blueprint = blueprint_generator.generate_blueprint_r1(
        preprocessed_data=_preprocessed(),
        writing_policy={},
        intent_graph={},
    )

    assert blueprint["llm_model"] == "deepseek-v4-pro"
    assert len(blueprint["bullets"]) == 5
    assert blueprint["bullets"][0]["theme"] == "Runtime"


def test_false_live_streaming_not_in_enriched_policy_intent_graph():
    policy = {
        "scene_priority": ["commuting_capture"],
        "product_profile": {"target_audience_role": "commuter", "category_type": "action_camera"},
    }

    enriched = intent_translator.enrich_policy_with_intent_graph(
        policy,
        {"live_streaming_supported": False, "wifi_connection": "2.4GHz"},
    )

    capabilities = [str(item.get("capability") or "").lower() for item in enriched.get("intent_graph") or []]
    assert "live streaming" not in capabilities
    assert "live_streaming_supported" in (enriched.get("suppressed_capabilities") or [])


def test_blueprint_scrubs_false_live_streaming_from_entry_fields():
    blueprint = {
        "bullets": [
            {
                "bullet_index": 3,
                "theme": "Live Streaming POV Capture",
                "assigned_l2_keywords": ["thumb camera"],
                "mandatory_elements": ["WiFi 2.4GHz for app control and live stream", "1080P clarity"],
                "scenes": ["vlog_content_creation"],
                "capabilities": ["live streaming", "easy operation"],
                "accessories": [],
                "persona": "creator",
                "pain_point": "missed moments",
                "buying_trigger": "fast sharing",
                "proof_angle": "live streaming proof via WiFi app",
                "priority": "P1",
                "slot_directive": "Highlight live streaming and WiFi sharing.",
            }
        ]
    }

    scrubbed = blueprint_generator._scrub_suppressed_blueprint_content(
        blueprint,
        suppressed_capabilities={"live_streaming_supported"},
    )
    entry = scrubbed["bullets"][0]

    assert "live stream" not in entry["theme"].lower()
    assert not any("live stream" in item.lower() for item in entry["mandatory_elements"])
    assert not any("live stream" in item.lower() for item in entry["capabilities"])
    assert "live stream" not in entry["proof_angle"].lower()
    assert "live stream" not in entry["slot_directive"].lower()


def test_true_live_streaming_still_enters_blueprint():
    blueprint = {
        "bullets": [
            {
                "bullet_index": 3,
                "theme": "Live Streaming POV Capture",
                "assigned_l2_keywords": [],
                "mandatory_elements": ["WiFi 2.4GHz for app control and live stream"],
                "scenes": [],
                "capabilities": ["live streaming"],
                "accessories": [],
                "persona": "creator",
                "pain_point": "",
                "buying_trigger": "",
                "proof_angle": "live streaming proof",
                "priority": "P1",
                "slot_directive": "Highlight live streaming.",
            }
        ]
    }

    scrubbed = blueprint_generator._scrub_suppressed_blueprint_content(
        blueprint,
        suppressed_capabilities=set(),
    )

    entry = scrubbed["bullets"][0]
    assert "live streaming" in entry["theme"].lower()
    assert any("live stream" in item.lower() for item in entry["mandatory_elements"])


def test_waterproof_false_scrubs_underwater_terms():
    blueprint = {
        "bullets": [
            {
                "bullet_index": 4,
                "theme": "Underwater Waterproof Adventure",
                "assigned_l2_keywords": [],
                "mandatory_elements": ["waterproof case for underwater capture", "1080P footage"],
                "scenes": [],
                "capabilities": ["waterproof"],
                "accessories": [],
                "persona": "traveler",
                "pain_point": "",
                "buying_trigger": "",
                "proof_angle": "waterproof proof",
                "priority": "P1",
                "slot_directive": "Position as waterproof for underwater use.",
            }
        ]
    }

    scrubbed = blueprint_generator._scrub_suppressed_blueprint_content(
        blueprint,
        suppressed_capabilities={"waterproof_supported"},
    )
    entry = scrubbed["bullets"][0]
    assert "waterproof" not in entry["theme"].lower()
    assert "underwater" not in entry["theme"].lower()
    assert not any(any(token in item.lower() for token in ("waterproof", "underwater")) for item in entry["mandatory_elements"])


def test_stabilization_false_scrubs_without_leaving_no_image_fragment():
    blueprint = {
        "bullets": [
            {
                "bullet_index": 2,
                "theme": "Professional Evidence Capture",
                "assigned_l2_keywords": ["body camera with audio"],
                "mandatory_elements": [
                    "1080P HD video with audio recording (AAC format)",
                    "explicit note: NO image stabilization",
                    "best for stable professional scenes",
                ],
                "scenes": ["commuting_capture"],
                "capabilities": ["lightweight design"],
                "accessories": [],
                "persona": "Security Guard / Service Professional",
                "pain_point": "",
                "buying_trigger": "",
                "proof_angle": "No image stabilization, best for stable professional scenes.",
                "priority": "P1",
                "slot_directive": "Must include the limitation (no stabilization) framed as a condition for best use.",
            }
        ]
    }

    scrubbed = blueprint_generator._scrub_suppressed_blueprint_content(
        blueprint,
        suppressed_capabilities={"stabilization_supported"},
    )
    entry = scrubbed["bullets"][0]

    assert not any("no image" in item.lower() for item in entry["mandatory_elements"])
    assert "no image" not in entry["proof_angle"].lower()
    assert "no image" not in entry["slot_directive"].lower()
    assert "stable professional scenes" in entry["proof_angle"].lower()


def test_stabilization_false_scrubs_does_not_include_image_stabilization_fragment():
    blueprint = {
        "bullets": [
            {
                "bullet_index": 4,
                "theme": "Best-Use Guidance",
                "assigned_l2_keywords": ["body camera"],
                "mandatory_elements": [
                    "does not include image stabilization",
                    "use on steady surfaces for clearest video",
                ],
                "scenes": ["travel_documentation"],
                "capabilities": [],
                "accessories": [],
                "persona": "first-time buyer",
                "pain_point": "",
                "buying_trigger": "",
                "proof_angle": "This body camera does not include image stabilization, so use on steady surfaces for clearest video.",
                "priority": "P1",
                "slot_directive": "Frame the limitation warmly: does not include image stabilization, so guide steady use.",
            }
        ]
    }

    scrubbed = blueprint_generator._scrub_suppressed_blueprint_content(
        blueprint,
        suppressed_capabilities={"stabilization_supported"},
    )
    entry = scrubbed["bullets"][0]

    assert not any("does not include image" in item.lower() for item in entry["mandatory_elements"])
    assert "does not include image" not in entry["proof_angle"].lower()
    assert "does not include image" not in entry["slot_directive"].lower()
    assert "steady surfaces" in entry["proof_angle"].lower()


def test_dedupe_negative_constraint_blueprint_content_keeps_single_slot():
    blueprint = {
        "bullets": [
            {
                "bullet_index": 2,
                "theme": "Professional Evidence Capture",
                "assigned_l2_keywords": ["body camera with audio"],
                "mandatory_elements": ["explicit note: NO image stabilization", "loop recording"],
                "scenes": ["commuting_capture"],
                "capabilities": ["lightweight design"],
                "accessories": [],
                "persona": "Security Guard / Service Professional",
                "pain_point": "",
                "buying_trigger": "",
                "proof_angle": "No image stabilization for stable professional scenes.",
                "priority": "P1",
                "slot_directive": "Must include the limitation (no stabilization) framed as a condition for best use.",
            },
            {
                "bullet_index": 4,
                "theme": "Best-Use Guidance for Optimal Video Quality",
                "assigned_l2_keywords": [],
                "mandatory_elements": [
                    "Clear statement: Machine has no image stabilization.",
                    "Warning: Not suitable for high-vibration environments (e.g., on a motorcycle).",
                ],
                "scenes": [],
                "capabilities": [],
                "accessories": [],
                "persona": "Informed Buyer / First-Time User",
                "pain_point": "",
                "buying_trigger": "",
                "proof_angle": "Transparent best-use guidance about no stabilization.",
                "priority": "P1",
                "slot_directive": "Express the critical limitation from raw_human_insights as warm, positive guidance.",
            },
        ]
    }

    deduped = blueprint_generator._dedupe_negative_constraint_blueprint_content(
        blueprint,
        suppressed_capabilities={"stabilization_supported"},
    )

    bullet_2 = deduped["bullets"][0]
    bullet_4 = deduped["bullets"][1]
    bullet_2_text = json.dumps(bullet_2, ensure_ascii=False).lower()
    bullet_4_text = json.dumps(bullet_4, ensure_ascii=False).lower()

    assert "stabilization" not in bullet_2_text
    assert "stabilization" in bullet_4_text
