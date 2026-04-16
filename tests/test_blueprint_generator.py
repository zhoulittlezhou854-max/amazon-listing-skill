from types import SimpleNamespace

from modules import blueprint_generator


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


def test_generate_blueprint_r1_uses_reasoner_override(monkeypatch):
    class _Client:
        def __init__(self):
            self.response_metadata = {"configured_model": "deepseek-reasoner"}

        def generate_text(self, system_prompt, payload, temperature=0.35, override_model=None):
            assert override_model == "deepseek-reasoner"
            return (
                '{"bullets": ['
                '{"bullet_index": 1, "theme": "Runtime", "assigned_l2_keywords": [], "mandatory_elements": [],'
                '"scenes": [], "capabilities": [], "accessories": [], "persona": "commuter",'
                '"pain_point": "battery anxiety", "buying_trigger": "all-day use", "proof_angle": "150 minutes",'
                '"priority": "P0", "slot_directive": "numeric proof"}'
                ']}'
            )

    monkeypatch.setattr(blueprint_generator, "get_llm_client", lambda: _Client())

    blueprint = blueprint_generator.generate_blueprint_r1(
        preprocessed_data=_preprocessed(),
        writing_policy={},
        intent_graph={},
    )

    assert blueprint["llm_model"] == "deepseek-reasoner"
    assert blueprint["bullets"][0]["theme"] == "Runtime"
