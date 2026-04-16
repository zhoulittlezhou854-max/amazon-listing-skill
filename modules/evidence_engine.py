from __future__ import annotations

from typing import Any, Dict


def summarize_evidence_bundle(evidence_bundle: Dict[str, Any]) -> Dict[str, Any]:
    claim_support_matrix = list((evidence_bundle or {}).get("claim_support_matrix") or [])
    rufus_readiness = dict((evidence_bundle or {}).get("rufus_readiness") or {})

    supported_claim_count = 0
    weak_support_count = 0
    unsupported_claim_count = 0
    for row in claim_support_matrix:
        support_status = str((row or {}).get("support_status") or "").strip().lower()
        if support_status == "supported":
            supported_claim_count += 1
        elif support_status == "weakly_supported":
            weak_support_count += 1
        elif support_status == "unsupported":
            unsupported_claim_count += 1

    return {
        "claim_count": len(claim_support_matrix),
        "supported_claim_count": supported_claim_count,
        "weak_support_count": weak_support_count,
        "unsupported_claim_count": unsupported_claim_count,
        "rufus_score": float(rufus_readiness.get("score") or 0.0),
        "rufus_supported_claim_count": int(rufus_readiness.get("supported_claim_count") or 0),
        "rufus_total_claim_count": int(rufus_readiness.get("total_claim_count") or 0),
    }


def build_evidence_bundle(preprocessed_data: Any, entity_profile: Dict[str, Any]) -> Dict[str, Any]:
    attribute_data = getattr(getattr(preprocessed_data, "attribute_data", None), "data", {}) or {}
    insights = getattr(getattr(preprocessed_data, "review_data", None), "insights", []) or []

    positive_clusters = []
    negative_clusters = []
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        topic = str(insight.get("field_name") or "").strip() or "general"
        if insight.get("positive"):
            positive_clusters.append({"topic": topic, "evidence": insight.get("positive")})
        if insight.get("negative"):
            negative_clusters.append({"topic": topic, "evidence": insight.get("negative")})

    claim_support_matrix = []
    evidence_text = " ".join(str(value) for value in attribute_data.values())
    evidence_text += " " + " ".join(
        str(item.get("positive") or "") + " " + str(item.get("negative") or "")
        for item in insights
        if isinstance(item, dict)
    )
    evidence_text = evidence_text.lower()
    for claim in entity_profile.get("claim_registry", []) or []:
        claim_text = str((claim or {}).get("claim") or "")
        support_status = "weakly_supported"
        if claim_text and claim_text.lower() in evidence_text:
            support_status = "supported"
        claim_support_matrix.append(
            {
                "claim": claim_text,
                "source_type": (claim or {}).get("source_type", ""),
                "support_status": support_status,
            }
        )

    supported_count = sum(1 for row in claim_support_matrix if row["support_status"] == "supported")
    total_claims = len(claim_support_matrix)
    return {
        "attribute_evidence": attribute_data,
        "review_positive_clusters": positive_clusters,
        "review_negative_clusters": negative_clusters,
        "qa_clusters": [],
        "claim_support_matrix": claim_support_matrix,
        "rufus_readiness": {
            "score": supported_count / total_claims if total_claims else 0.0,
            "supported_claim_count": supported_count,
            "total_claim_count": total_claims,
        },
    }
