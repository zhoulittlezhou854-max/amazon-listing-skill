from modules.keyword_reconciliation import reconcile_keyword_assignments


def test_final_title_and_bullets_are_scanned_for_authoritative_coverage():
    candidate = {
        "title": "Vlogging Camera Mini Camera for Travel Days",
        "bullets": [
            "Travel camera grip keeps everyday trips simple.",
            "Body camera with audio records clear voice notes.",
            "Thumb camera design clips discreetly to a backpack.",
            "Extra bullet should not affect the required L2 slot count.",
            "Final included bullet stays within the scanned range.",
            "Travel camera beyond the first five bullets is ignored.",
        ],
        "description": "A pocket-size recorder for family walks.",
        "search_terms": ["thumb camera", "backup phrase"],
    }
    metadata = {
        "vlogging camera": {"tier": "l1", "source": "keyword_table"},
        "mini camera": {"tier": "L1", "protocol_source": "keyword_protocol"},
        "travel camera": {"tier": "L2", "source": "keyword_table"},
        "body camera with audio": {"tier": "L2", "source": "keyword_table"},
        "thumb camera": {"tier": "L2", "source": "keyword_table"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    assert result["status"] == "complete"
    assert result["warnings"] == []
    assert result["coverage"] == {
        "l1_title_hits": 2,
        "l2_bullet_slots": 3,
        "l3_backend_terms": 0,
    }
    fields_by_keyword = {}
    protocol_sources = {}
    for row in result["assignments"]:
        fields_by_keyword.setdefault(row["keyword"], set()).add(row["field"])
        protocol_sources[row["keyword"]] = row["protocol_source"]

    assert fields_by_keyword["vlogging camera"] == {"title"}
    assert protocol_sources["mini camera"] == "keyword_protocol"
    assert "bullet_1" in fields_by_keyword["travel camera"]
    assert "bullet_3" in fields_by_keyword["thumb camera"]


def test_search_terms_do_not_downgrade_authoritative_l2_metadata():
    candidate = {
        "title": "Pocket video kit",
        "bullet_1": "Use this travel camera on weekend routes.",
        "search_terms": "travel camera travelcam pocket recorder",
    }
    metadata = {
        "travel camera": {"tier": "L2", "source": "keyword_table"},
        "pocket recorder": {"tier": "L3", "source": "backend_plan"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    by_keyword_and_field = {
        (row["keyword"], row["field"]): row for row in result["assignments"]
    }
    assert by_keyword_and_field[("travel camera", "bullet_1")]["tier"] == "L2"
    assert by_keyword_and_field[("travel camera", "search_terms")]["tier"] == "L2"
    assert (
        by_keyword_and_field[("travel camera", "search_terms")]["protocol_source"]
        == "keyword_table"
    )
    assert result["coverage"]["l2_bullet_slots"] == 1
    assert result["coverage"]["l3_backend_terms"] == 1


def test_assignment_rows_include_current_consumer_assigned_fields():
    candidate = {
        "title": "Mini Camera",
        "bullets": ["Travel camera for weekend routes."],
        "search_terms": "pocket recorder",
    }
    metadata = {
        "travel camera": {"tier": "L2", "source": "keyword_table"},
        "pocket recorder": {"tier": "L3", "source": "backend_plan"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    travel_row = next(row for row in result["assignments"] if row["keyword"] == "travel camera")
    backend_row = next(row for row in result["assignments"] if row["keyword"] == "pocket recorder")
    assert travel_row["field"] == "bullet_1"
    assert travel_row["assigned_fields"] == ["bullet_1"]
    assert travel_row["traffic_tier"] == "L2"
    assert backend_row["assigned_fields"] == ["search_terms"]


def test_search_terms_list_entries_are_matched_independently_not_joined():
    candidate = {
        "title": "Pocket video kit",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "search_terms": ["travel", "camera", "pocket recorder"],
    }
    metadata = {
        "travel camera": {"tier": "L3", "source": "backend_plan"},
        "pocket recorder": {"tier": "L3", "source": "backend_plan"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    search_term_keywords = {
        row["keyword"] for row in result["assignments"] if row["field"] == "search_terms"
    }
    assert "travel camera" not in search_term_keywords
    assert "pocket recorder" in search_term_keywords
    assert result["coverage"]["l3_backend_terms"] == 1


def test_tier_can_come_from_traffic_tier_or_level_metadata():
    candidate = {
        "title": "Mini Camera",
        "bullets": ["Travel camera for weekend routes."],
        "search_terms": "pocket recorder",
    }
    metadata = {
        "travel camera": {"traffic_tier": "l2", "source": "keyword_table"},
        "pocket recorder": {"level": "L3", "source": "backend_plan"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    by_keyword = {row["keyword"]: row for row in result["assignments"]}
    assert by_keyword["travel camera"]["tier"] == "L2"
    assert by_keyword["travel camera"]["traffic_tier"] == "L2"
    assert by_keyword["pocket recorder"]["tier"] == "L3"
    assert result["coverage"]["l2_bullet_slots"] == 1
    assert result["coverage"]["l3_backend_terms"] == 1


def test_reconciliation_accepts_simple_plural_phrase_variant():
    candidate = {
        "title": "Action Cameras for Travel",
        "bullets": ["Compact body cameras clip on quickly."],
        "search_terms": "pocket recorder",
    }
    metadata = {
        "action camera": {"tier": "L1", "source": "keyword_table"},
        "body camera": {"tier": "L2", "source": "keyword_table"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    by_keyword = {row["keyword"]: row for row in result["assignments"]}
    assert by_keyword["action camera"]["field"] == "title"
    assert by_keyword["body camera"]["field"] == "bullet_1"
    assert result["coverage"]["l1_title_hits"] == 1
    assert result["coverage"]["l2_bullet_slots"] == 1


def test_reconciliation_accepts_y_to_ies_plural_phrase_variant():
    candidate = {
        "title": "Long Batteries for Travel Cameras",
        "bullets": ["Accessory kits keep the mount organized."],
        "search_terms": "",
    }
    metadata = {
        "battery": {"tier": "L1", "source": "keyword_table"},
        "accessory": {"tier": "L2", "source": "keyword_table"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    by_keyword = {row["keyword"]: row for row in result["assignments"]}
    assert by_keyword["battery"]["field"] == "title"
    assert by_keyword["accessory"]["field"] == "bullet_1"
    assert result["coverage"]["l1_title_hits"] == 1
    assert result["coverage"]["l2_bullet_slots"] == 1


def test_reconciliation_accepts_plural_head_noun_before_qualifier():
    candidate = {
        "title": "Mini Camera",
        "bullets": ["Use body cameras with audio for work shifts."],
        "search_terms": "",
    }
    metadata = {
        "body camera with audio": {"tier": "L2", "source": "keyword_table"},
    }

    result = reconcile_keyword_assignments(candidate, metadata)

    [row] = result["assignments"]
    assert row["keyword"] == "body camera with audio"
    assert row["field"] == "bullet_1"
    assert result["coverage"]["l2_bullet_slots"] == 1
