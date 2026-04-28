import json

from modules.keyword_protocol import build_keyword_protocol


def test_all_keywords_above_1000_still_get_relative_l3():
    rows = [
        {"keyword": "vlogging camera", "search_volume": 30000, "conversion_rate": 0.018, "click_share": 0.12, "product_fit_score": 0.95},
        {"keyword": "mini camera", "search_volume": 22000, "conversion_rate": 0.017, "click_share": 0.11, "product_fit_score": 0.94},
        {"keyword": "body camera", "search_volume": 18000, "conversion_rate": 0.02, "click_share": 0.1, "product_fit_score": 0.96},
        {"keyword": "travel camera", "search_volume": 7737, "conversion_rate": 0.021, "click_share": 0.08, "product_fit_score": 0.92},
        {"keyword": "body camera with audio", "search_volume": 7617, "conversion_rate": 0.024, "click_share": 0.07, "product_fit_score": 0.91},
        {"keyword": "thumb camera", "search_volume": 4681, "conversion_rate": 0.019, "click_share": 0.06, "product_fit_score": 0.9},
    ]

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")
    tiers = {row["keyword"]: row["traffic_tier"] for row in protocol["keyword_metadata"]}

    assert "L1" in set(tiers.values())
    assert "L2" in set(tiers.values())
    assert "L3" in set(tiers.values())
    assert tiers["thumb camera"] == "L3"


def test_high_volume_low_fit_keyword_is_rejected_not_l1():
    rows = [
        {"keyword": "hidden spy camera", "search_volume": 50000, "conversion_rate": 0.03, "click_share": 0.2, "product_fit_score": 0.2},
        {"keyword": "body camera", "search_volume": 20000, "conversion_rate": 0.02, "click_share": 0.1, "product_fit_score": 0.95},
        {"keyword": "travel camera", "search_volume": 7000, "conversion_rate": 0.02, "click_share": 0.08, "product_fit_score": 0.9},
    ]

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")
    rejected = {row["keyword"]: row for row in protocol["rejected_keywords"] + protocol["blocked_keywords"]}
    qualified = {row["keyword"]: row for row in protocol["qualified_keywords"]}

    assert "hidden spy camera" in rejected
    assert "hidden spy camera" not in qualified
    assert qualified["body camera"]["traffic_tier"] == "L1"


def test_relevant_zero_volume_keyword_is_natural_only():
    rows = [
        {"keyword": "snaproll camera", "search_volume": 0, "conversion_rate": 0, "click_share": 0, "product_fit_score": 0.9},
        {"keyword": "body camera", "search_volume": 20000, "conversion_rate": 0.02, "click_share": 0.1, "product_fit_score": 0.95},
    ]

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")
    natural = {row["keyword"]: row for row in protocol["natural_only_keywords"]}
    tiered = {row["keyword"] for row in protocol["qualified_keywords"]}

    assert "snaproll camera" in natural
    assert "snaproll camera" not in tiered


def test_nan_search_volume_is_treated_as_missing_and_natural_only():
    rows = [
        {"keyword": "snaproll camera", "search_volume": float("nan"), "conversion_rate": 0, "click_share": 0, "product_fit_score": 0.9},
        {"keyword": "body camera", "search_volume": 20000, "conversion_rate": 0.02, "click_share": 0.1, "product_fit_score": 0.95},
    ]

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")
    natural = {row["keyword"]: row for row in protocol["natural_only_keywords"]}
    tiered = {row["keyword"] for row in protocol["qualified_keywords"]}

    assert natural["snaproll camera"]["search_volume"] == 0.0
    assert natural["snaproll camera"]["traffic_tier"] == "NON_TIER"
    assert "snaproll camera" not in tiered


def test_keyword_metadata_has_stable_required_shape_for_all_statuses():
    rows = [
        {
            "keyword": "body camera",
            "search_volume": 20000,
            "conversion_rate": 0.02,
            "click_share": 0.1,
            "ctr": 0.08,
            "monthly_purchases": 300,
            "product_count": 3000,
            "title_density": 0.8,
            "avg_cpc": 0.9,
            "click_concentration": 0.5,
            "conv_concentration": 0.4,
            "product_fit_score": 0.95,
        },
        {"keyword": "snaproll camera", "search_volume": 0, "product_fit_score": 0.9},
        {"keyword": "hidden spy camera", "search_volume": 50000, "product_fit_score": 0.2},
    ]
    required_keys = {
        "keyword",
        "search_volume",
        "conversion_rate",
        "click_share",
        "ctr",
        "monthly_purchases",
        "product_count",
        "title_density",
        "avg_cpc",
        "click_concentration",
        "conv_concentration",
        "product_fit_score",
        "demand_score",
        "engagement_score",
        "conversion_score",
        "competition_score",
        "confidence_score",
        "opportunity_score",
        "keyword_quality_score",
        "blue_ocean_score",
        "quality_status",
        "rejection_reason",
        "long_tail_flag",
        "source_type",
        "volume_percentile",
        "traffic_tier",
        "tier",
        "routing_role",
        "opportunity_type",
    }

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")

    assert {row["quality_status"] for row in protocol["keyword_metadata"]} >= {"qualified", "natural_only", "rejected"}
    for row in protocol["keyword_metadata"]:
        assert required_keys <= set(row), row["keyword"]


def test_protocol_is_strict_json_safe_when_source_rows_contain_non_finite_extra_fields():
    rows = [
        {
            "keyword": "body camera",
            "search_volume": 20000,
            "conversion_rate": 0.02,
            "click_share": 0.1,
            "product_fit_score": 0.95,
            "raw_score": float("nan"),
        },
        {
            "keyword": "travel camera",
            "search_volume": 7000,
            "cvr": float("inf"),
            "click_share": 0.08,
            "product_fit_score": 0.9,
            "acos": float("-inf"),
        },
    ]

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")

    json.dumps(protocol, allow_nan=False)


def test_blue_ocean_does_not_replace_head_anchor():
    rows = [
        {"keyword": "body camera", "search_volume": 25000, "conversion_rate": 0.017, "click_share": 0.1, "product_count": 3000, "title_density": 0.8, "product_fit_score": 0.96},
        {"keyword": "body camera with audio", "search_volume": 7600, "conversion_rate": 0.028, "click_share": 0.08, "product_count": 300, "title_density": 0.25, "product_fit_score": 0.92},
        {"keyword": "thumb camera", "search_volume": 4600, "conversion_rate": 0.022, "click_share": 0.06, "product_count": 200, "title_density": 0.2, "product_fit_score": 0.9},
    ]

    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")
    meta = {row["keyword"]: row for row in protocol["keyword_metadata"]}

    assert meta["body camera"]["routing_role"] == "title"
    assert meta["body camera with audio"]["opportunity_type"] in {"conversion_blue_ocean", "blue_ocean"}
    assert meta["body camera with audio"]["routing_role"] == "bullet"


def test_extract_tiered_keywords_uses_protocol_metadata():
    from types import SimpleNamespace

    from modules.keyword_utils import extract_tiered_keywords

    preprocessed = SimpleNamespace(
        keyword_data=SimpleNamespace(
            keywords=[
                {"keyword": "body camera", "search_volume": 20000, "conversion_rate": 0.02, "click_share": 0.1, "product_fit_score": 0.95},
                {"keyword": "travel camera", "search_volume": 7737, "conversion_rate": 0.021, "click_share": 0.08, "product_fit_score": 0.92},
                {"keyword": "snaproll camera", "search_volume": 0, "conversion_rate": 0, "click_share": 0, "product_fit_score": 0.9},
            ]
        ),
        real_vocab=None,
        core_selling_points=["wearable body camera"],
        attribute_data={},
        raw_human_insights="",
    )

    tiers = extract_tiered_keywords(preprocessed, language="English")
    metadata = tiers["_metadata"]

    assert "body camera" in tiers["l1"]
    assert metadata["body camera"]["quality_status"] == "qualified"
    assert metadata["travel camera"]["routing_role"] in {"bullet", "backend"}
    assert metadata["snaproll camera"]["quality_status"] == "natural_only"
    assert "snaproll camera" not in tiers["l1"] + tiers["l2"] + tiers["l3"]


def test_wearable_body_camera_keeps_action_camera_as_broad_category_anchor():
    from types import SimpleNamespace

    from modules.keyword_utils import extract_tiered_keywords

    preprocessed = SimpleNamespace(
        keyword_data=SimpleNamespace(
            keywords=[
                {"keyword": "action camera", "search_volume": 84755, "conversion_rate": 0.0087},
                {"keyword": "vlogging camera", "search_volume": 30000, "conversion_rate": 0.018, "click_share": 0.12},
                {"keyword": "mini camera", "search_volume": 22000, "conversion_rate": 0.017, "click_share": 0.11},
                {"keyword": "body camera", "search_volume": 18000, "conversion_rate": 0.02, "click_share": 0.1},
                {"keyword": "hidden spy camera", "search_volume": 50000, "conversion_rate": 0.03, "click_share": 0.2},
            ]
        ),
        real_vocab=None,
        core_selling_points=["wearable body camera with clip"],
        attribute_data=SimpleNamespace(data={}),
        raw_human_insights="",
    )

    tiers = extract_tiered_keywords(preprocessed, language="English")
    metadata = tiers["_metadata"]

    assert metadata["action camera"]["quality_status"] == "qualified"
    assert metadata["action camera"]["routing_role"] in {"title", "bullet"}
    assert metadata["hidden spy camera"]["quality_status"] == "rejected"
