from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from modules.language_utils import canonicalize_capability, canonicalize_scene_label, english_capability_label


def _pick_first(row: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and row.get(key) not in {None, ""}:
            return row.get(key)
    return default


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    if text.endswith("%"):
        text = text[:-1]
    try:
        value_float = float(text)
    except ValueError:
        return 0.0
    if value_float > 1.0:
        return value_float / 100.0
    return value_float


def _normalize_channel(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def build_intent_weight_snapshot(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    weights = []
    for row in rows or []:
        ctr = _to_float(_pick_first(row, "ctr", "click_through_rate", "click rate"))
        cvr = _to_float(_pick_first(row, "cvr", "conversion_rate", "conversion rate", "order_rate"))
        orders = _to_float(_pick_first(row, "orders", "sales", "purchases"))
        keyword = str(
            _pick_first(
                row,
                "keyword",
                "search term",
                "search_query",
                "term",
                "query",
                default="",
            )
            or ""
        ).strip()
        theme = str(_pick_first(row, "theme", "topic", "content_theme", "review_theme", default="") or "").strip()
        source_type = str(
            _pick_first(row, "source_type", "source", "traffic_source", "content_type", default="")
            or ""
        ).strip()
        traffic_channel = _normalize_channel(
            _pick_first(row, "traffic_channel", "channel", "platform", "site_channel", default="")
        )
        scene = str(_pick_first(row, "scene", "usage_scene", default="") or "").strip()
        capability = str(_pick_first(row, "capability", "feature", default="") or "").strip()
        clicks = _to_float(_pick_first(row, "clicks", "sessions", default=0.0))
        impressions = _to_float(_pick_first(row, "impressions", "views", default=0.0))
        theme_weight = ctr * 0.4 + cvr * 0.4 + min(0.2, orders / 100.0)
        weights.append(
            {
                "keyword": keyword,
                "scene": scene,
                "capability": capability,
                "theme": theme,
                "source_type": source_type,
                "traffic_channel": traffic_channel,
                "clicks": clicks,
                "impressions": impressions,
                "orders": orders,
                "traffic_weight": ctr,
                "conversion_weight": cvr,
                "scene_weight": ctr * 0.6 + cvr * 0.4,
                "capability_weight": cvr * 0.7 + ctr * 0.3,
                "theme_weight": theme_weight,
                "confidence_score": 1.0 if orders > 0 else 0.5,
            }
        )
    return {"weights": weights}


def save_intent_weight_snapshot(
    workspace_dir: str,
    rows: List[Dict[str, Any]],
    product_code: str,
    site: str,
    source_file: str = "",
) -> str:
    workspace = Path(workspace_dir)
    target_dir = workspace / "intent_weights"
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot = build_intent_weight_snapshot(rows)
    saved_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "product_code": product_code,
        "site": site,
        "source_file": source_file,
        "saved_at": saved_at,
        **snapshot,
    }
    stamp = saved_at.replace(":", "-")[:19]
    target = target_dir / f"intent_weight_{stamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def load_intent_weight_snapshot(snapshot_path: str) -> Dict[str, Any]:
    path = Path(snapshot_path)
    if not path.exists():
        raise FileNotFoundError(snapshot_path)
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_intent_weight_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    weights = list((snapshot or {}).get("weights") or [])
    ranked = sorted(
        weights,
        key=lambda item: (
            float(item.get("traffic_weight") or 0.0),
            float(item.get("conversion_weight") or 0.0),
            float(item.get("scene_weight") or 0.0),
        ),
        reverse=True,
    )
    scenes = {
        str(item.get("scene") or "").strip()
        for item in weights
        if str(item.get("scene") or "").strip()
    }
    capabilities = {
        str(item.get("capability") or "").strip()
        for item in weights
        if str(item.get("capability") or "").strip()
    }
    themes = [
        str(item.get("theme") or "").strip()
        for item in ranked
        if str(item.get("theme") or "").strip()
    ]
    channels = {
        str(item.get("traffic_channel") or "").strip()
        for item in weights
        if str(item.get("traffic_channel") or "").strip()
    }
    source_types = {
        str(item.get("source_type") or "").strip()
        for item in weights
        if str(item.get("source_type") or "").strip()
    }
    return {
        "updated_keyword_count": len(weights),
        "top_promoted_keywords": [
            str(item.get("keyword") or "").strip()
            for item in ranked
            if str(item.get("keyword") or "").strip()
        ][:5],
        "scene_count": len(scenes),
        "capability_count": len(capabilities),
        "channel_count": len(channels),
        "channels": sorted(channels),
        "external_theme_count": len({theme for theme in themes if theme}),
        "top_external_themes": list(dict.fromkeys(themes))[:5],
        "source_types": sorted(source_types),
    }


def apply_intent_weight_to_intent_graph(
    intent_graph_data: Dict[str, Any],
    intent_weight_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    updated = dict(intent_graph_data or {})
    normalized_snapshot = {"weights": list((intent_weight_snapshot or {}).get("weights") or [])}
    weights = normalized_snapshot["weights"]

    metadata = dict(updated.get("metadata") or {})
    metadata["intent_weight_summary"] = summarize_intent_weight_snapshot(normalized_snapshot)
    updated["metadata"] = metadata
    updated["intent_weight_snapshot"] = normalized_snapshot

    if not weights:
        return updated

    scene_rollups: Dict[str, Dict[str, Any]] = {}
    capability_rollups: Dict[str, Dict[str, Any]] = {}
    normalized_rows: List[Dict[str, Any]] = []

    def _ensure_rollup(bucket: Dict[str, Dict[str, Any]], key: str) -> Dict[str, Any]:
        entry = bucket.get(key)
        if entry is None:
            entry = {
                "learned_weight": 0.0,
                "traffic_weight": 0.0,
                "conversion_weight": 0.0,
                "promoted_keywords": [],
            }
            bucket[key] = entry
        return entry

    for row in weights:
        keyword = str(row.get("keyword") or "").strip()
        scene_key = canonicalize_scene_label(str(row.get("scene") or ""))
        capability_key = english_capability_label(canonicalize_capability(str(row.get("capability") or "")))
        traffic_weight = float(row.get("traffic_weight") or 0.0)
        conversion_weight = float(row.get("conversion_weight") or 0.0)
        scene_weight = float(row.get("scene_weight") or 0.0)
        capability_weight = float(row.get("capability_weight") or 0.0)

        normalized_rows.append(
            {
                "keyword": keyword,
                "scene": scene_key,
                "capability": capability_key,
                "traffic_weight": traffic_weight,
                "conversion_weight": conversion_weight,
                "scene_weight": scene_weight,
                "capability_weight": capability_weight,
            }
        )

        if scene_key and scene_key != "unknown_scene":
            entry = _ensure_rollup(scene_rollups, scene_key)
            entry["learned_weight"] += scene_weight
            entry["traffic_weight"] += traffic_weight
            entry["conversion_weight"] += conversion_weight
            if keyword and keyword not in entry["promoted_keywords"]:
                entry["promoted_keywords"].append(keyword)

        if capability_key and capability_key != "unknown capability":
            entry = _ensure_rollup(capability_rollups, capability_key.lower())
            entry["learned_weight"] += capability_weight
            entry["traffic_weight"] += traffic_weight
            entry["conversion_weight"] += conversion_weight
            if keyword and keyword not in entry["promoted_keywords"]:
                entry["promoted_keywords"].append(keyword)

    updated_nodes = []
    for node in list(updated.get("intent_graph") or []):
        new_node = dict(node or {})
        source_keywords = {
            str(item or "").strip().lower()
            for item in (new_node.get("source_keywords") or [])
            if str(item or "").strip()
        }
        usage_scenarios = {
            canonicalize_scene_label(str(item or ""))
            for item in (new_node.get("usage_scenarios") or [])
            if str(item or "").strip()
        }
        capabilities = {
            english_capability_label(canonicalize_capability(str(item or ""))).lower()
            for item in (new_node.get("capabilities") or [])
            if str(item or "").strip()
        }

        learned_rank_score = 0.0
        learned_keywords: List[str] = []
        for row in normalized_rows:
            keyword_match = row["keyword"].lower() in source_keywords if row["keyword"] else False
            scene_match = row["scene"] in usage_scenarios if row["scene"] else False
            capability_match = row["capability"].lower() in capabilities if row["capability"] else False
            if not any([keyword_match, scene_match, capability_match]):
                continue
            learned_rank_score = max(
                learned_rank_score,
                row["scene_weight"] + row["capability_weight"] + row["traffic_weight"],
            )
            if row["keyword"] and row["keyword"] not in learned_keywords:
                learned_keywords.append(row["keyword"])

        new_node["learned_rank_score"] = round(learned_rank_score, 4)
        new_node["learned_keywords"] = learned_keywords[:5]
        updated_nodes.append(new_node)

    updated_nodes.sort(
        key=lambda item: (
            float(item.get("learned_rank_score") or 0.0),
            float(item.get("search_volume") or 0.0),
        ),
        reverse=True,
    )
    updated["intent_graph"] = updated_nodes

    updated_scene_meta = []
    for entry in list(updated.get("scene_metadata") or []):
        new_entry = dict(entry or {})
        rollup = scene_rollups.get(canonicalize_scene_label(str(new_entry.get("scene") or "")), {})
        new_entry["learned_weight"] = round(float(rollup.get("learned_weight") or 0.0), 4)
        new_entry["traffic_weight"] = round(float(rollup.get("traffic_weight") or 0.0), 4)
        new_entry["conversion_weight"] = round(float(rollup.get("conversion_weight") or 0.0), 4)
        new_entry["promoted_keywords"] = list(rollup.get("promoted_keywords") or [])[:5]
        updated_scene_meta.append(new_entry)
    updated["scene_metadata"] = updated_scene_meta

    updated_capability_meta = []
    for entry in list(updated.get("capability_metadata") or []):
        new_entry = dict(entry or {})
        lookup_key = str(new_entry.get("capability") or "").strip().lower()
        rollup = capability_rollups.get(lookup_key, {})
        new_entry["learned_weight"] = round(float(rollup.get("learned_weight") or 0.0), 4)
        new_entry["traffic_weight"] = round(float(rollup.get("traffic_weight") or 0.0), 4)
        new_entry["conversion_weight"] = round(float(rollup.get("conversion_weight") or 0.0), 4)
        new_entry["promoted_keywords"] = list(rollup.get("promoted_keywords") or [])[:5]
        updated_capability_meta.append(new_entry)
    updated["capability_metadata"] = updated_capability_meta

    updated_stag_groups = []
    for group in list(updated.get("stag_groups") or []):
        new_group = dict(group or {})
        group_weight = 0.0
        promoted_keywords: List[str] = []
        for scene in (new_group.get("primary_scenarios") or []):
            rollup = scene_rollups.get(canonicalize_scene_label(str(scene or "")), {})
            group_weight = max(group_weight, float(rollup.get("learned_weight") or 0.0))
            for keyword in rollup.get("promoted_keywords") or []:
                if keyword not in promoted_keywords:
                    promoted_keywords.append(keyword)
        new_group["learned_scene_weight"] = round(group_weight, 4)
        new_group["promoted_keywords"] = promoted_keywords[:5]
        updated_stag_groups.append(new_group)
    updated["stag_groups"] = updated_stag_groups

    return updated


def apply_intent_weight_overrides(
    policy: Dict[str, Any],
    retention_strategy: Dict[str, Any],
    intent_weight_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    updated = dict(policy or {})
    keyword_routing = dict(updated.get("keyword_routing") or {})
    normalized_snapshot = {"weights": list((intent_weight_snapshot or {}).get("weights") or [])}
    weights = list(normalized_snapshot.get("weights") or [])
    scene_priority = list(updated.get("scene_priority") or [])

    promoted_title = list(keyword_routing.get("title_traffic_keywords") or [])
    promoted_bullets = list(keyword_routing.get("bullet_conversion_keywords") or [])
    promoted_keywords: List[str] = []
    title_anchors = {str(item).strip().lower() for item in (retention_strategy.get("title_anchor_keywords") or []) if item}
    scene_rollup: Dict[str, float] = {}

    ranked = sorted(
        weights,
        key=lambda item: (
            float(item.get("traffic_weight") or 0.0),
            float(item.get("conversion_weight") or 0.0),
            float(item.get("scene_weight") or 0.0),
        ),
        reverse=True,
    )
    for row in ranked[:5]:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        promoted_keywords.append(keyword)
        normalized = keyword.lower()
        if normalized not in {item.lower() for item in promoted_title}:
            promoted_title.append(keyword)
        if normalized not in {item.lower() for item in promoted_bullets} and normalized not in title_anchors:
            promoted_bullets.append(keyword)
        scene_key = canonicalize_scene_label(str(row.get("scene") or ""))
        if scene_key and scene_key != "unknown_scene":
            scene_rollup[scene_key] = scene_rollup.get(scene_key, 0.0) + float(row.get("scene_weight") or 0.0)

    keyword_routing["title_traffic_keywords"] = promoted_title[:5]
    keyword_routing["bullet_conversion_keywords"] = promoted_bullets[:6]
    updated["keyword_routing"] = keyword_routing
    if scene_rollup:
        ranked_scenes = [name for name, _score in sorted(scene_rollup.items(), key=lambda item: item[1], reverse=True)]
        preserved = [scene for scene in scene_priority if scene not in ranked_scenes]
        updated["scene_priority"] = ranked_scenes + preserved
    updated["intent_weight_snapshot"] = normalized_snapshot
    summary_weights = [row for row in ranked if str(row.get("keyword") or "").strip() or str(row.get("theme") or "").strip()]
    updated["intent_weight_summary"] = summarize_intent_weight_snapshot({"weights": summary_weights})
    return updated
