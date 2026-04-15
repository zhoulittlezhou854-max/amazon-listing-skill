"""Minimal reproducible tests for keyword tiering and capability-scene binding."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from modules import scoring


def _preprocessed(keyword_rows: List[Dict[str, Any]]) -> Any:
    """Build a lightweight preprocessed_data namespace compatible with scoring."""
    return SimpleNamespace(
        run_config=SimpleNamespace(brand_name="ProtoBrand"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=keyword_rows),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        capability_constraints={},
        keyword_metadata=[],
    )


def _copy_with_trace(assignments: List[Dict[str, Any]],
                     bullet_trace: Optional[List[Dict[str, Any]]] = None,
                     search_bytes: int = 180,
                     audit_trail: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Construct a minimal generated_copy payload containing metadata trace."""
    return {
        "decision_trace": {
            "keyword_assignments": assignments,
            "bullet_trace": bullet_trace or [],
            "search_terms_trace": {
                "byte_length": search_bytes,
                "max_bytes": 249,
                "backend_only_used": 0,
            },
        },
        "audit_trail": audit_trail or [],
        "aplus_content": "",
        "title": "",
        "bullets": [],
        "search_terms": [],
    }


def run_keyword_cases() -> Dict[str, Dict[str, Any]]:
    """Return scoring excerpts for K1-K3."""
    keyword_rows = [
        {"keyword": "aktionskamera 4k", "search_volume": 15000},
        {"keyword": "wasserdichte kamera", "search_volume": 5000},
        {"keyword": "helm kamera kinder", "search_volume": 200},
    ]
    preprocessed = _preprocessed(keyword_rows)

    # Case definitions
    cases = {
        "K1": _copy_with_trace(
            assignments=[
                {"keyword": "aktionskamera 4k", "tier": "L1", "assigned_fields": ["title"]},
                {"keyword": "wasserdichte kamera", "tier": "L2", "assigned_fields": ["bullet_b1", "bullet_b2", "bullet_b3"]},
                {"keyword": "helm kamera kinder", "tier": "L3", "assigned_fields": ["search_terms"]},
            ],
        ),
        "K2": _copy_with_trace(
            assignments=[
                {"keyword": "aktionskamera 4k", "tier": "L1", "assigned_fields": ["bullet_b1"]},
                {"keyword": "wasserdichte kamera", "tier": "L2", "assigned_fields": ["bullet_b1"]},
                {"keyword": "helm kamera kinder", "tier": "L3", "assigned_fields": []},
            ],
            search_bytes=80,
        ),
        "K3": _copy_with_trace(assignments=[], search_bytes=20),
    }

    results = {}
    empty_policy = {"scene_priority": [], "capability_scene_bindings": []}
    for case_id, generated_copy in cases.items():
        scores = scoring.calculate_scores(generated_copy, empty_policy, preprocessed)
        results[case_id] = {
            "a10_score": scores["a10"]["subtotal"],
            "l1": scores["a10"]["l1_title_alignment"]["score"],
            "l2": scores["a10"]["l2_bullet_distribution"]["score"],
            "l3": scores["a10"]["l3_search_terms"]["score"],
        }
    return results


def run_capability_cases() -> Dict[str, Dict[str, Any]]:
    """Return capability binding excerpts for C1-C3."""
    keyword_rows = [
        {"keyword": "action camera", "search_volume": 12000},
    ]
    preprocessed = _preprocessed(keyword_rows)
    base_bullet_trace = [
        {"slot": "B1", "scene_code": "underwater", "capability": "waterproof build", "numeric_expectation": False, "numeric_met": False},
        {"slot": "B2", "scene_code": "cycling", "capability": "stabilization engine", "numeric_expectation": False, "numeric_met": False},
    ]
    base_copy = _copy_with_trace(assignments=[], bullet_trace=base_bullet_trace)
    intent_graph = {
        "capability_metadata": [
            {"capability": "waterproof", "is_supported": True},
            {"capability": "stabilization", "is_supported": True},
        ],
        "scene_metadata": [
            {"scene": "underwater", "visibility": "visible"},
            {"scene": "cycling", "visibility": "visible"},
        ],
    }

    cases = {
        "C1": {
            "writing_policy": {
                "scene_priority": ["underwater", "cycling"],
                "capability_scene_bindings": [
                    {
                        "capability": "waterproof",
                        "binding_type": "environmental_feature",
                        "allowed_scenes": ["underwater"],
                    },
                    {
                        "capability": "stabilization",
                        "binding_type": "performance_feature",
                        "allowed_scenes": ["cycling"],
                    },
                ],
            },
            "generated_copy": base_copy,
            "intent_graph": intent_graph,
        },
        "C2": {
            "writing_policy": {
                "scene_priority": ["unterwasser", "radfahren"],
                "capability_scene_bindings": [
                    {
                        "capability": "防水",
                        "binding_type": "environmental_feature",
                        "allowed_scenes": ["unterwasser"],
                    },
                ],
            },
            "generated_copy": base_copy,
            "intent_graph": {
                "capability_metadata": [
                    {"capability": "waterproof", "is_supported": True},
                ],
                "scene_metadata": [
                    {"scene": "unterwasser", "visibility": "visible"},
                ],
            },
        },
        "C3": {
            "writing_policy": {
                "scene_priority": ["underwater"],
                "capability_scene_bindings": [
                    {
                        "capability": "waterproof",
                        "binding_type": "environmental_feature",
                        "allowed_scenes": ["underwater"],
                    },
                ],
            },
            "generated_copy": _copy_with_trace(
                assignments=[],
                bullet_trace=[{"slot": "B1", "scene_code": "travel", "capability": "lightweight", "numeric_expectation": False, "numeric_met": False}],
            ),
            "intent_graph": intent_graph,
        },
    }

    results = {}
    for case_id, cfg in cases.items():
        scores = scoring.calculate_scores(
            cfg["generated_copy"],
            cfg["writing_policy"],
            preprocessed,
            intent_graph=cfg.get("intent_graph"),
        )
        results[case_id] = {
            "cosmo_score": scores["cosmo"]["subtotal"],
            "cap_score": scores["cosmo"]["capability_coverage"]["score"],
            "scene_score": scores["cosmo"]["scene_distribution"]["score"],
        }
    return results


def main():
    keyword_results = run_keyword_cases()
    capability_results = run_capability_cases()
    print(json.dumps({"keyword_cases": keyword_results, "capability_cases": capability_results}, indent=2))


if __name__ == "__main__":
    main()
