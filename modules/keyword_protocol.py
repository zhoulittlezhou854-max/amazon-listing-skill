"""Keyword quality, opportunity, traffic tier, and routing protocol."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Tuple


_BLOCKED_WEARABLE_TERMS = ("spy", "hidden")
_MISMATCH_TERMS = ("gopro", "dji", "insta360")


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    if text.endswith("%"):
        try:
            number = float(text[:-1]) / 100.0
        except ValueError:
            return 0.0
        return number if math.isfinite(number) else 0.0
    try:
        number = float(text)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return value


def _normalize_keyword(row: Dict[str, Any]) -> str:
    return str(row.get("keyword") or row.get("search_term") or row.get("search query") or "").strip()


def _score_percentile(value: float, values: List[float]) -> float:
    positives = sorted(float(item) for item in values if float(item) > 0)
    if value <= 0 or not positives:
        return 0.0
    below_or_equal = sum(1 for item in positives if item <= value)
    return below_or_equal / len(positives)


def _inverse_percentile(value: float, values: List[float]) -> float:
    positives = sorted(float(item) for item in values if float(item) > 0)
    if value <= 0 or not positives:
        return 0.5
    below_or_equal = sum(1 for item in positives if item <= value)
    return 1.0 - (below_or_equal - 1) / len(positives)


def _long_tail_flag(keyword: str) -> bool:
    tokens = [item for item in re.split(r"[\s\-_\/]+", keyword.strip()) if item]
    return len(tokens) >= 4


def _base_product_fit(row: Dict[str, Any], category_type: str) -> Tuple[float, str]:
    keyword = _normalize_keyword(row).lower()
    is_wearable = category_type == "wearable_body_camera"

    if is_wearable and any(term in keyword for term in _BLOCKED_WEARABLE_TERMS):
        return 0.0, "compliance_blocked"

    explicit = row.get("product_fit_score")
    if explicit not in {None, ""}:
        score = max(0.0, min(1.0, _to_float(explicit)))
    else:
        score = 0.7
        if is_wearable and any(
            term in keyword for term in ("body camera", "body cam", "wearable", "thumb camera", "mini camera", "travel camera")
        ):
            score = 0.9
        if any(term in keyword for term in _MISMATCH_TERMS):
            score = 0.2

    if score < 0.55:
        return score, "product_mismatch"
    return score, ""


def _build_base_rows(rows: Iterable[Dict[str, Any]], category_type: str) -> List[Dict[str, Any]]:
    raw_rows = list(rows or [])
    volumes = [_to_float(row.get("search_volume") or row.get("volume") or row.get("searches")) for row in raw_rows]
    conversions = [_to_float(row.get("conversion_rate") or row.get("cvr") or row.get("purchase_rate")) for row in raw_rows]
    clicks = [_to_float(row.get("click_share") or row.get("ctr") or row.get("click_through_rate")) for row in raw_rows]
    product_counts = [_to_float(row.get("product_count") or row.get("competitor_count")) for row in raw_rows]
    title_densities = [_to_float(row.get("title_density")) for row in raw_rows]
    cpcs = [_to_float(row.get("avg_cpc") or row.get("bid")) for row in raw_rows]
    seen: Dict[str, Dict[str, Any]] = {}

    for row in raw_rows:
        keyword = _normalize_keyword(row)
        if not keyword:
            continue

        search_volume = _to_float(row.get("search_volume") or row.get("volume") or row.get("searches"))
        conversion_rate = _to_float(row.get("conversion_rate") or row.get("cvr") or row.get("purchase_rate"))
        click_share = _to_float(row.get("click_share"))
        ctr = _to_float(row.get("ctr") or row.get("click_through_rate"))
        engagement_raw = max(click_share, ctr)
        product_count = _to_float(row.get("product_count") or row.get("competitor_count"))
        title_density = _to_float(row.get("title_density"))
        avg_cpc = _to_float(row.get("avg_cpc") or row.get("bid"))
        monthly_purchases = _to_float(row.get("monthly_purchases") or row.get("purchases") or row.get("orders"))
        click_concentration = _to_float(row.get("click_concentration"))
        conv_concentration = _to_float(row.get("conv_concentration") or row.get("conversion_concentration"))
        product_fit_score, fit_reason = _base_product_fit(row, category_type)

        demand_score = _score_percentile(search_volume, volumes)
        conversion_score = _score_percentile(conversion_rate, conversions) if conversion_rate > 0 else 0.35
        engagement_score = _score_percentile(engagement_raw, clicks) if engagement_raw > 0 else 0.35

        competition_inputs = []
        if product_count > 0:
            competition_inputs.append(_inverse_percentile(product_count, product_counts))
        if title_density > 0:
            competition_inputs.append(_inverse_percentile(title_density, title_densities))
        if avg_cpc > 0:
            competition_inputs.append(_inverse_percentile(avg_cpc, cpcs))
        competition_score = sum(competition_inputs) / len(competition_inputs) if competition_inputs else 0.5

        confidence_parts = [search_volume > 0, conversion_rate > 0, engagement_raw > 0, bool(competition_inputs), product_fit_score > 0]
        confidence_score = sum(1 for item in confidence_parts if item) / len(confidence_parts)
        keyword_quality_score = (
            product_fit_score * 0.30
            + demand_score * 0.20
            + conversion_score * 0.20
            + engagement_score * 0.15
            + competition_score * 0.10
            + confidence_score * 0.05
        )
        blue_ocean_score = (
            product_fit_score * 0.25
            + demand_score * 0.20
            + conversion_score * 0.20
            + engagement_score * 0.10
            + competition_score * 0.20
            + (1.0 if _long_tail_flag(keyword) else 0.5) * 0.05
        )

        quality_status = "qualified"
        rejection_reason = ""
        if fit_reason:
            quality_status = "rejected"
            rejection_reason = fit_reason
        elif search_volume <= 0:
            quality_status = "natural_only"
            rejection_reason = "zero_search_volume"
        elif keyword_quality_score < 0.5:
            quality_status = "watchlist"
            rejection_reason = "low_keyword_quality"

        payload = _json_safe_value(dict(row))
        payload.update(
            {
                "keyword": keyword,
                "search_volume": search_volume,
                "conversion_rate": conversion_rate,
                "click_share": click_share,
                "ctr": ctr,
                "product_count": product_count,
                "title_density": title_density,
                "avg_cpc": avg_cpc,
                "monthly_purchases": monthly_purchases,
                "click_concentration": click_concentration,
                "conv_concentration": conv_concentration,
                "product_fit_score": round(product_fit_score, 4),
                "demand_score": round(demand_score, 4),
                "engagement_score": round(engagement_score, 4),
                "conversion_score": round(conversion_score, 4),
                "competition_score": round(competition_score, 4),
                "confidence_score": round(confidence_score, 4),
                "opportunity_score": round(keyword_quality_score, 4),
                "keyword_quality_score": round(keyword_quality_score, 4),
                "blue_ocean_score": round(blue_ocean_score, 4),
                "quality_status": quality_status,
                "rejection_reason": rejection_reason,
                "long_tail_flag": _long_tail_flag(keyword),
                "source_type": row.get("source_type") or "keyword_table",
                "volume_percentile": round(demand_score, 4),
                "traffic_tier": "",
                "tier": "",
                "routing_role": "",
                "opportunity_type": "",
            }
        )

        key = keyword.lower()
        existing = seen.get(key)
        if existing is None or payload["opportunity_score"] > existing["opportunity_score"]:
            seen[key] = payload

    return list(seen.values())


def _assign_tiers(qualified: List[Dict[str, Any]]) -> None:
    ranked = sorted(qualified, key=lambda row: (row["search_volume"], row["opportunity_score"]), reverse=True)
    total = len(ranked)
    if total == 0:
        return

    for idx, row in enumerate(ranked, 1):
        pct = idx / total
        if pct <= 0.2 or idx == 1:
            tier = "L1"
        elif pct <= 0.6:
            tier = "L2"
        else:
            tier = "L3"
        row["rank_index"] = idx
        row["volume_percentile"] = round(1.0 - ((idx - 1) / total), 4)
        row["traffic_tier"] = tier
        row["tier"] = tier


def _assign_routing(row: Dict[str, Any]) -> None:
    tier = row.get("traffic_tier")
    blue = float(row.get("blue_ocean_score") or 0.0)
    conversion = float(row.get("conversion_score") or 0.0)

    if tier == "L1":
        role = "title"
        opportunity_type = "head_traffic"
    elif tier == "L2" or blue >= 0.7 or conversion >= 0.75:
        role = "bullet"
        opportunity_type = "conversion_blue_ocean" if blue >= 0.7 else "conversion"
    else:
        role = "backend"
        opportunity_type = "blue_ocean" if blue >= 0.7 else "residual"

    row["routing_role"] = role
    row["opportunity_type"] = opportunity_type


def _assign_terminal_routing(rows: List[Dict[str, Any]], tier: str, role: str, opportunity_type: str) -> None:
    for row in rows:
        row["traffic_tier"] = tier
        row["tier"] = tier
        row["routing_role"] = role
        row["opportunity_type"] = opportunity_type


def build_keyword_protocol(
    rows: Iterable[Dict[str, Any]], country: str = "US", category_type: str = "generic"
) -> Dict[str, Any]:
    """Build the authoritative keyword protocol payload for downstream modules."""
    base_rows = _build_base_rows(rows, category_type)
    blocked = [row for row in base_rows if str(row.get("rejection_reason")) in {"brand_blocked", "compliance_blocked"}]
    rejected = [row for row in base_rows if row["quality_status"] == "rejected" and row not in blocked]
    natural_only = [row for row in base_rows if row["quality_status"] == "natural_only"]
    watchlist = [row for row in base_rows if row["quality_status"] == "watchlist"]
    qualified = [row for row in base_rows if row["quality_status"] == "qualified"]

    _assign_tiers(qualified)
    for row in qualified:
        _assign_routing(row)
    _assign_terminal_routing(natural_only, "NON_TIER", "natural_only", "natural_language")
    _assign_terminal_routing(watchlist, "WATCHLIST", "watchlist", "monitor")
    _assign_terminal_routing(rejected, "REJECTED", "rejected", "rejected")
    _assign_terminal_routing(blocked, "REJECTED", "blocked", "blocked")

    metadata = qualified + natural_only + watchlist + rejected + blocked
    return {
        "country": country,
        "category_type": category_type,
        "qualified_keywords": qualified,
        "watchlist_keywords": watchlist,
        "natural_only_keywords": natural_only,
        "rejected_keywords": rejected,
        "blocked_keywords": blocked,
        "keyword_metadata": metadata,
        "tiered_keywords": {
            "l1": [row["keyword"] for row in qualified if row.get("traffic_tier") == "L1"],
            "l2": [row["keyword"] for row in qualified if row.get("traffic_tier") == "L2"],
            "l3": [row["keyword"] for row in qualified if row.get("traffic_tier") == "L3"],
        },
    }
