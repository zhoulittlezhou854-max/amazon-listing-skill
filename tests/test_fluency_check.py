from types import SimpleNamespace

from modules import copy_generation as cg
from modules import fluency_check as fc
from modules import writing_policy as wp


class _CaptureBulletClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate_bullet(self, system_prompt, payload, temperature=0.15):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "payload": payload,
                "temperature": temperature,
            }
        )
        return self.response


def _write_competitor_csv(tmp_path, rows):
    path = tmp_path / "competitors.csv"
    header = "ASIN_Role,ASIN,Data_Type,Field_Name,Content_Text\n"
    body = "".join(
        f'{row["ASIN_Role"]},{row.get("ASIN", "")},{row["Data_Type"]},{row["Field_Name"]},"{row["Content_Text"]}"\n'
        for row in rows
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def test_benchmark_extraction_filters_low_quality_bullets(tmp_path):
    path = _write_competitor_csv(
        tmp_path,
        [
            {
                "ASIN_Role": "Competitor_Exact",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_1",
                "Content_Text": (
                    "Capture Every Detail — Record crisp 4K footage at 30fps with a 154 degree lens, "
                    "so fast rides, pet walks, and commute moments stay sharp from the first clip."
                ),
            },
            {
                "ASIN_Role": "Competitor_Exact",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_2",
                "Content_Text": "Portable design for daily use without any measurable spec.",
            },
            {
                "ASIN_Role": "Competitor_Exact",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_3",
                "Content_Text": (
                    "Best Camera Ever — Guaranteed amazing quality with perfect results every time for every rider."
                ),
            },
        ],
    )
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(review_table=str(path)),
        target_country="US",
        raw_human_insights="",
    )

    bullets = wp._extract_benchmark_bullets(preprocessed)

    assert len(bullets) == 1
    assert bullets[0].startswith("Capture Every Detail")


def test_benchmark_extraction_deduplicates_similar_bullets(tmp_path):
    duplicate = (
        "Capture Every Detail — Record crisp 4K footage at 30fps with a 154 degree lens, "
        "so commute clips stay sharp and ready to share after every ride."
    )
    path = _write_competitor_csv(
        tmp_path,
        [
            {
                "ASIN_Role": "Competitor_Exact",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_1",
                "Content_Text": duplicate,
            },
            {
                "ASIN_Role": "Competitor_Similar",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_1",
                "Content_Text": duplicate + " Extra tail for a second source.",
            },
        ],
    )
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(review_table=str(path)),
        target_country="US",
        raw_human_insights="",
    )

    bullets = wp._extract_benchmark_bullets(preprocessed)

    assert len(bullets) == 1


def test_benchmark_fallback_returns_default_when_no_competitor_data():
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(review_table="missing.csv"),
        target_country="US",
        raw_human_insights="",
    )

    bullets = wp._extract_benchmark_bullets(preprocessed)

    assert len(bullets) >= 3
    assert bullets[0].startswith("Capture Every Detail")


def test_benchmark_path_reads_input_files_review_table(tmp_path):
    path = _write_competitor_csv(
        tmp_path,
        [
            {
                "ASIN_Role": "Competitor_Exact",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_1",
                "Content_Text": "Capture crisp 4K footage at 30fps with a compact build that keeps commute clips sharp.",
            }
        ],
    )
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(input_files={"review_table": str(path)}),
        ingestion_audit={},
    )

    paths = wp._benchmark_candidate_paths(preprocessed)

    assert paths == [path]


def test_benchmark_path_falls_back_to_multi_dimension_table(tmp_path):
    path = _write_competitor_csv(
        tmp_path,
        [
            {
                "ASIN_Role": "Competitor_Exact",
                "Data_Type": "Listing_Content",
                "Field_Name": "Bullet_1",
                "Content_Text": "Record 1080P clips at 30fps with a 154 degree view that keeps rides covered.",
            }
        ],
    )
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(input_files={"multi_dimension_table": str(path)}),
        ingestion_audit={},
    )

    paths = wp._benchmark_candidate_paths(preprocessed)

    assert paths == [path]


def test_numeric_pattern_matches_1080p():
    assert bool(wp._BENCHMARK_NUMERIC_PATTERN.search("1080P HD video"))


def test_numeric_pattern_matches_154_degree():
    assert bool(wp._BENCHMARK_NUMERIC_PATTERN.search("154° wide angle"))


def test_numeric_pattern_matches_4k():
    assert bool(wp._BENCHMARK_NUMERIC_PATTERN.search("4K UHD recording"))


def test_action_opener_accepts_header_noun_with_verb_in_body():
    assert wp._bullet_has_action_opener("Long Battery Life — Records up to 150 minutes")


def test_perfect_not_hard_blocked_for_top_bsr():
    assert wp._is_high_quality_bullet(
        "Perfect for travel, records 4K at 30fps with a 150-minute battery, compact clip mount, and all-day comfort that keeps daily commute clips rolling from the first errand to the last stop.",
        bsr_rank=200,
    )


def test_perfect_soft_blocked_for_low_bsr():
    assert not wp._is_high_quality_bullet(
        "Perfect for travel, records 4K at 30fps with a 150-minute battery, compact clip mount, and all-day comfort that keeps daily commute clips rolling from the first errand to the last stop.",
        bsr_rank=1000,
    )


def test_length_280_accepted():
    bullet = (
        "Capture every commute in 1080P at 30fps with a 154 degree view, magnetic clip, stable body mount, "
        "and lightweight housing that keeps rides comfortable while the 150-minute battery records errands, "
        "delivery shifts, travel notes, and quick family moments without missing the action."
    )
    assert len(bullet) <= wp._BENCHMARK_MAX_LENGTH
    assert wp._is_high_quality_bullet(bullet, bsr_rank=200)


def test_repair_prompt_includes_benchmark_when_available(monkeypatch):
    client = _CaptureBulletClient('{"text":"BODY CAMERA CLARITY — Capture 4K travel clips at 35g for up to 150 minutes.","capability_mapping":["easy operation"]}')
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    cg._repair_bullet_candidate_with_llm(
        "BODY CAMERA WITH — Capture travel clips with body camera with audio.",
        {"fluency_header_trailing_preposition": "with", "missing_numeric": "150 minutes"},
        {
            "target_language": "English",
            "mandatory_keywords": ["body camera with audio"],
            "localized_scene_anchors": ["travel"],
            "localized_capability_anchors": ["easy operation"],
            "numeric_proof": "150 minutes",
            "slot": "B5",
            "benchmark_bullets": [
                "Capture Every Detail — Record crisp 4K footage at 30fps with a 154 degree lens so every commute stays sharp.",
                "All-Day Power, Featherlight Build — At just 35g with a 150-minute battery, clip it on and keep moving.",
            ],
        },
    )

    prompt = client.calls[0]["system_prompt"]
    assert "Reference examples" in prompt
    assert "Capture Every Detail" in prompt


def test_repair_prompt_skips_benchmark_block_when_empty(monkeypatch):
    client = _CaptureBulletClient('{"text":"BODY CAMERA CLARITY — Capture travel clips for up to 150 minutes.","capability_mapping":["easy operation"]}')
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    cg._repair_bullet_candidate_with_llm(
        "BODY CAMERA WITH — Capture travel clips with body camera with audio.",
        {"fluency_header_trailing_preposition": "with"},
        {
            "target_language": "English",
            "mandatory_keywords": ["body camera with audio"],
            "localized_scene_anchors": ["travel"],
            "localized_capability_anchors": ["easy operation"],
            "slot": "B5",
            "benchmark_bullets": [],
        },
    )

    prompt = client.calls[0]["system_prompt"]
    assert "Reference examples" not in prompt


def test_repair_with_benchmark_fixes_preposition_header(monkeypatch):
    client = _CaptureBulletClient('{"text":"BODY CAMERA CLARITY — Capture travel moments with body camera with audio and 150 minutes runtime.","capability_mapping":["easy operation"]}')
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    repaired = cg._repair_bullet_candidate_with_llm(
        "BODY CAMERA WITH — Document travel using a body camera with audio, easy operation, 150 minutes so every clip feels ready to share.",
        {"fluency_header_trailing_preposition": "with", "missing_numeric": "150 minutes"},
        {
            "target_language": "English",
            "mandatory_keywords": ["body camera with audio"],
            "localized_scene_anchors": ["travel"],
            "localized_capability_anchors": ["easy operation"],
            "numeric_proof": "150 minutes",
            "slot": "B5",
            "benchmark_bullets": [
                "All-Day Power, Featherlight Build — At just 35g with a 150-minute battery, clip it on and keep moving.",
            ],
        },
    )

    assert repaired.startswith("BODY CAMERA CLARITY")
    assert "WITH —" not in repaired


def test_repair_preserves_all_numeric_specs_after_benchmark_repair(monkeypatch):
    client = _CaptureBulletClient('{"text":"TRAVEL READY DETAIL — Record 4K clips with a 35g camera for up to 150 minutes on every ride.","capability_mapping":["easy operation"]}')
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    repaired = cg._repair_bullet_candidate_with_llm(
        "TRAVEL CAMERA WITH — Record travel clips with a tiny camera.",
        {"fluency_header_trailing_preposition": "with", "missing_numeric": "150 minutes"},
        {
            "target_language": "English",
            "mandatory_keywords": ["travel camera"],
            "localized_scene_anchors": ["ride"],
            "localized_capability_anchors": ["easy operation"],
            "numeric_proof": "150 minutes",
            "slot": "B4",
            "benchmark_bullets": [
                "Capture Every Detail — Record crisp 4K footage at 30fps with a 154 degree lens so every commute stays sharp.",
            ],
        },
    )

    assert "4K" in repaired
    assert "35g" in repaired
    assert "150 minutes" in repaired


def test_header_body_rupture_detected_when_body_starts_with_it():
    bullet = "LIGHTWEIGHT DESIGN — It weighs only 35g perfect for commute."

    issues = fc.check_fluency("bullet_b2", bullet)

    assert any(issue.rule_id == "header_body_rupture" for issue in issues)


def test_header_body_rupture_detected_when_body_starts_with_this():
    bullet = "LONG BATTERY — This camera records up to 150 minutes non-stop."

    issues = fc.check_fluency("bullet_b5", bullet)

    assert any(issue.rule_id == "header_body_rupture" for issue in issues)


def test_header_body_rupture_not_triggered_on_clean_bullet():
    bullet = (
        "Capture Every Detail — 4K UHD at 30fps records crisp footage even in fast-motion scenes."
    )

    issues = fc.check_fluency("bullet_b1", bullet)

    assert not any(issue.rule_id == "header_body_rupture" for issue in issues)


def test_required_specs_extracted_correctly():
    assert fc._extract_specs("Records 4K at 30fps, weighs 35g") == "4K, 30fps, 35g"


def test_dash_tail_without_predicate_skips_when_tail_has_comma_clause():
    issues = fc.check_fluency(
        "bullet_b5",
        "BODY CAMERA WITH AUDIO — featuring easy operation, 150 minutes of recording for commute capture",
    )
    assert not any(issue.rule_id == "dash_tail_without_predicate" for issue in issues)


def test_dash_tail_without_predicate_skips_when_tail_is_long_predicate_like_body():
    issues = fc.check_fluency(
        "bullet_b5",
        "BODY CAMERA WITH AUDIO — clear audio for city commute, stable clip use, and all-day travel journaling support",
    )
    assert not any(issue.rule_id == "dash_tail_without_predicate" for issue in issues)


def test_rupture_repair_preserves_all_numeric_specs(monkeypatch):
    client = _CaptureBulletClient(
        '{"text":"LIGHTWEIGHT DESIGN — At just 35g, it stays comfortable through a full 150 minutes of commuting capture.","capability_mapping":["lightweight design"]}'
    )
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    repaired = cg._repair_bullet_candidate_with_llm(
        "LIGHTWEIGHT DESIGN — It weighs only 35g and records for 150 minutes during commute.",
        {"fluency_header_body_rupture": True},
        {
            "target_language": "English",
            "mandatory_keywords": ["travel camera"],
            "localized_scene_anchors": ["commute"],
            "localized_capability_anchors": ["lightweight design"],
            "numeric_proof": "150 minutes",
            "slot": "B2",
            "benchmark_bullets": [
                "All-Day Power, Featherlight Build — At just 35g with a 150-minute battery, clip it to your chest or helmet and forget it's there until the ride is done."
            ],
        },
    )

    assert "35g" in repaired
    assert "150 minutes" in repaired


def test_rupture_repair_produces_flowing_header_body(monkeypatch):
    client = _CaptureBulletClient(
        '{"text":"LONG BATTERY — With up to 150 minutes of runtime, it keeps body camera recording ready for your full commute.","capability_mapping":["long battery"]}'
    )
    monkeypatch.setattr(cg, "get_llm_client", lambda: client)

    repaired = cg._repair_bullet_candidate_with_llm(
        "LONG BATTERY — This camera records up to 150 minutes non-stop.",
        {"fluency_header_body_rupture": True},
        {
            "target_language": "English",
            "mandatory_keywords": ["body camera with audio"],
            "localized_scene_anchors": ["commute"],
            "localized_capability_anchors": ["long battery"],
            "numeric_proof": "150 minutes",
            "slot": "B5",
            "benchmark_bullets": [
                "All-Day Power, Featherlight Build — At just 35g with a 150-minute battery, clip it to your chest or helmet and forget it's there until the ride is done."
            ],
        },
    )

    issues = fc.check_fluency("bullet_b5", repaired)

    assert not any(issue.rule_id == "header_body_rupture" for issue in issues)


def test_fluency_flags_keyword_append_fragment():
    issues = fc.check_fluency("bullet_b4", "SMOOTH MOTION SETUP — The lens rotates for stable clips Includes pov.")

    assert any(issue.rule_id == "keyword_append_fragment" for issue in issues)


def test_fluency_flags_orphan_the_artifact():
    issues = fc.check_fluency("bullet_b1", "RECORDING POWER — Document your entire travel documentation The.")

    assert any(issue.rule_id == "orphan_the_artifact" for issue in issues)


def test_fluency_flags_capitalized_join_artifact():
    issues = fc.check_fluency(
        "bullet_b2",
        "LIGHTWEIGHT — Clips to your vest for extended-session wear Capture crisp 1080P footage.",
    )

    assert any(issue.rule_id == "capitalized_join_artifact" for issue in issues)
