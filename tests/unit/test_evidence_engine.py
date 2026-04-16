from types import SimpleNamespace

from modules.evidence_engine import build_evidence_bundle, summarize_evidence_bundle


def _sample_preprocessed_data():
    return SimpleNamespace(
        review_data=SimpleNamespace(
            insights=[
                {"field_name": "battery", "positive": "battery lasts all ride"},
                {"field_name": "battery", "negative": "battery drains in cold"},
                {"field_name": "waterproof", "positive": "works well with the case"},
            ]
        ),
        attribute_data=SimpleNamespace(
            data={
                "runtime_minutes": 150,
                "waterproof_depth_m": 30,
                "waterproof_requires_case": True,
            }
        ),
        target_country="DE",
    )


def test_evidence_bundle_contains_support_sections():
    entity_profile = {
        "claim_registry": [
            {"claim": "150 minute runtime", "source_type": "spec"},
            {"claim": "30 m waterproof with case", "source_type": "spec"},
        ]
    }

    bundle = build_evidence_bundle(_sample_preprocessed_data(), entity_profile)

    assert set(bundle) >= {
        "attribute_evidence",
        "review_positive_clusters",
        "review_negative_clusters",
        "qa_clusters",
        "claim_support_matrix",
        "rufus_readiness",
    }


def test_evidence_bundle_returns_claim_support_matrix_rows():
    entity_profile = {"claim_registry": [{"claim": "150 minute runtime", "source_type": "spec"}]}

    bundle = build_evidence_bundle(_sample_preprocessed_data(), entity_profile)

    assert isinstance(bundle["claim_support_matrix"], list)


def test_summarize_evidence_bundle_counts_support_states():
    summary = summarize_evidence_bundle(
        {
            "claim_support_matrix": [
                {"claim": "150 minute runtime", "support_status": "supported"},
                {"claim": "30 m waterproof with case", "support_status": "weakly_supported"},
                {"claim": "stormproof usage", "support_status": "unsupported"},
            ],
            "rufus_readiness": {
                "score": 0.33,
                "supported_claim_count": 1,
                "total_claim_count": 3,
            },
        }
    )

    assert summary["supported_claim_count"] == 1
    assert summary["weak_support_count"] == 1
    assert summary["unsupported_claim_count"] == 1
    assert summary["rufus_score"] == 0.33
