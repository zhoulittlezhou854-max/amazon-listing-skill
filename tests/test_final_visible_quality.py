from modules.final_visible_quality import repair_final_visible_copy, validate_final_visible_copy


def _base_copy(**overrides):
    artifact = {
        "title": "TOSBARRFT vlogging camera Action Camera with 150 minutes",
        "bullets": [
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — Use this POV camera for sports training.",
            "COMPLETE KIT, ZERO WAIT — Open the box and start recording your commute immediately. Inside you get the body camera, magnetic clip, back clip, USB cable, and 32GB SD card. The built-in battery delivers 150 minutes of continuous recording. Supports micro SD up to 256GB.",
        ],
        "description": "Use it for travel. Ask support about best-use scenarios.",
        "search_terms": ["wearable camera", "thumb camera"],
        "bullet_packets": [
            {
                "slot": "B1",
                "required_keywords": ["action camera"],
                "capability_mapping": ["long battery"],
                "scene_mapping": ["travel_documentation"],
            },
            {
                "slot": "B2",
                "required_keywords": ["body camera"],
                "capability_mapping": ["lightweight design"],
                "scene_mapping": ["commuting_capture"],
            },
            {
                "slot": "B3",
                "required_keywords": ["body cam"],
                "capability_mapping": ["easy operation"],
                "scene_mapping": ["commuting_capture"],
            },
            {
                "slot": "B4",
                "required_keywords": ["pov camera", "action camera"],
                "capability_mapping": ["high definition"],
                "scene_mapping": ["sports_training"],
            },
            {
                "slot": "B5",
                "required_keywords": ["wearable camera", "thumb camera"],
                "capability_mapping": ["long battery"],
                "scene_mapping": ["commuting_capture"],
            },
        ],
        "metadata": {"generation_status": "live_success"},
    }
    artifact.update(overrides)
    return artifact


def test_final_visible_quality_blocks_b5_multiple_primary_promises():
    report = validate_final_visible_copy(
        _base_copy(),
        candidate_id="version_a",
        source_type="stable",
    )

    assert report["operational_status"] == "NOT_READY_FOR_LISTING"
    assert "slot_contract_failed:B5:multiple_primary_promises" in report["paste_ready_blockers"]
    assert any(
        issue["code"] == "slot_contract_failed:multiple_primary_promises"
        for issue in report["slot_issues"]["B5"]
    )


def test_final_visible_quality_blocks_keyword_append_artifact():
    artifact = _base_copy(
        bullets=[
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — The lens rotates for stable training clips Includes pov.",
            "READY KIT — Open the box with wearable camera and thumb camera, magnetic clip, back clip, USB cable, and 32GB SD card included. Add microSD storage up to 256GB for commute recording.",
        ]
    )

    report = validate_final_visible_copy(
        artifact,
        candidate_id="version_a",
        source_type="stable",
    )

    assert "fluency_artifact:bullet_b4:keyword_append_fragment" in report["paste_ready_blockers"]


def test_final_visible_quality_blocks_description_forbidden_surface():
    report = validate_final_visible_copy(
        _base_copy(description="Use it for travel recording. Ask support about best-use scenarios."),
        candidate_id="version_a",
        source_type="stable",
    )

    assert "forbidden_surface:description:best" in report["paste_ready_blockers"]
    assert report["field_issues"]["description"][0]["repairable"] is True


def test_final_visible_quality_report_uses_candidate_shaped_schema():
    report = validate_final_visible_copy(
        _base_copy(),
        candidate_id="version_a",
        source_type="stable",
    )

    assert report["schema_version"] == "final_visible_quality_v1"
    assert report["candidate_id"] == "version_a"
    assert report["source_type"] == "stable"
    assert set(report) >= {
        "field_issues",
        "slot_issues",
        "paste_ready_blockers",
        "review_only_warnings",
        "operational_status",
        "repair_log",
    }


def test_repair_final_visible_copy_rewrites_b5_without_battery_runtime():
    artifact = _base_copy()

    repaired, report = repair_final_visible_copy(
        artifact,
        candidate_id="version_a",
        source_type="stable",
    )

    b5 = repaired["bullets"][4].lower()
    assert "wearable camera" in b5
    assert "thumb camera" in b5
    assert "150 minutes" not in b5
    assert "battery" not in b5
    assert "runtime" not in b5
    assert "per charge" not in b5
    assert "32gb" in b5
    assert "256gb" in b5
    assert report["status"] == "repaired"
    assert report["operational_status"] == "READY_FOR_LISTING"
    assert report["paste_ready_blockers"] == []
    assert repaired["final_visible_quality"] == report
    assert repaired["metadata"]["final_visible_quality"] == report


def test_repair_final_visible_copy_rewrites_keyword_append_fragment():
    artifact = _base_copy(
        bullets=[
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — The lens rotates for stable training clips Includes pov.",
            "READY KIT — Open the box with wearable camera and thumb camera, magnetic clip, back clip, USB cable, and 32GB SD card included. Add microSD storage up to 256GB for commute recording.",
        ]
    )

    repaired, report = repair_final_visible_copy(
        artifact,
        candidate_id="version_a",
        source_type="stable",
    )

    assert "Includes pov" not in repaired["bullets"][3]
    assert "POV camera" in repaired["bullets"][3] or "pov camera" in repaired["bullets"][3].lower()
    assert "keyword_append_fragment" not in str(report)


def test_repair_final_visible_copy_removes_description_best_sentence_safely():
    artifact = _base_copy(
        description="Capture commute clips. Ask support about best-use scenarios. Keep setup simple."
    )

    repaired, report = repair_final_visible_copy(
        artifact,
        candidate_id="version_a",
        source_type="stable",
    )

    assert "best" not in repaired["description"].lower()
    assert "use-case" in repaired["description"].lower() or "setup" in repaired["description"].lower()
    assert "forbidden_surface:description:best" not in report["paste_ready_blockers"]


def test_final_visible_quality_keeps_backend_search_terms_as_warning_not_blocker():
    artifact = _base_copy(
        bullets=[
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — Use this POV camera and action camera setup for sports training.",
            "READY KIT — Open the box with wearable camera and thumb camera, magnetic clip, back clip, USB cable, and 32GB SD card included. Add microSD storage up to 256GB for commute recording.",
        ],
        description="Capture commute clips with simple setup.",
        search_terms=["wearable camera"],
    )

    report = validate_final_visible_copy(artifact, candidate_id="version_a", source_type="stable")

    assert "backend_search_terms_underused" in report["review_only_warnings"]
    assert "backend_search_terms_underused" not in report["paste_ready_blockers"]
