from modules import writing_policy as wp


def test_keyword_routing_uses_roles_not_l3_backend():
    tiered_keywords = {
        "_metadata": {
            "body camera": {
                "keyword": "body camera",
                "traffic_tier": "L1",
                "tier": "L1",
                "routing_role": "title",
                "quality_status": "qualified",
            },
            "travel camera": {
                "keyword": "travel camera",
                "traffic_tier": "L2",
                "routing_role": "bullet",
                "quality_status": "qualified",
                "blue_ocean_score": 0.8,
            },
            "thumb camera": {
                "keyword": "thumb camera",
                "traffic_tier": "L3",
                "routing_role": "bullet",
                "quality_status": "qualified",
            },
            "mini cam synonym": {
                "keyword": "mini cam synonym",
                "traffic_tier": "L3",
                "routing_role": "backend",
                "quality_status": "qualified",
            },
        }
    }

    routing = wp._derive_keyword_routing(tiered_keywords)

    assert routing["title_traffic_keywords"] == ["body camera"]
    assert "travel camera" in routing["bullet_conversion_keywords"]
    assert "thumb camera" in routing["bullet_conversion_keywords"]
    assert routing["backend_residual_keywords"] == ["mini cam synonym"]
    assert routing["backend_longtail_keywords"] == ["mini cam synonym"]
    assert "thumb camera" not in routing["backend_residual_keywords"]
