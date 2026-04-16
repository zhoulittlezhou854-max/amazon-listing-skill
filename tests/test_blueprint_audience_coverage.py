from types import SimpleNamespace

import modules.blueprint_generator as bg


def _fake_preprocessed():
    return SimpleNamespace(
        language='English',
        raw_human_insights='',
        attribute_data=SimpleNamespace(data={}),
        canonical_core_selling_points=['long battery life', 'magnetic clip', '1080p video'],
        feedback_context={},
    )


def test_audience_allocation_plan_covers_multiple_groups():
    plan = bg._build_audience_allocation_plan(
        preprocessed_data=_fake_preprocessed(),
        writing_policy={'scene_priority': ['commuting_capture', 'daily_vlogging']},
    )

    groups = {entry['group'] for entry in plan}
    assert len(plan) == 5
    assert len(groups) >= 2
    assert {'professional', 'daily', 'kit'}.issubset(groups)


def test_audience_allocation_prompt_marks_must_follow_structure():
    plan = bg._build_audience_allocation_plan(
        preprocessed_data=_fake_preprocessed(),
        writing_policy={'scene_priority': ['commuting_capture']},
    )

    prompt = bg._build_audience_allocation_prompt(plan)

    assert 'Audience Allocation Plan' in prompt
    assert 'MUST follow this structure' in prompt
    assert '- B1 [' in prompt
    assert 'At least 2 different audience groups must be represented' in prompt
