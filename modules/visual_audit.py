#!/usr/bin/env python3
"""
Node 2 - 视觉审计基础框架

当前实现为占位逻辑：根据提供的图片路径推断简单的视觉标签、
挂载方式、使用场景及合规标志，确保工作流可执行。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _guess_tags_from_filename(filename: str) -> List[str]:
    name = filename.lower()
    tags = []
    if any(word in name for word in ["bike", "ride", "cycle"]):
        tags.append("骑行场景")
    if any(word in name for word in ["surf", "water", "diving", "underwater"]):
        tags.append("水下探索")
    if any(word in name for word in ["mountain", "hike", "trail"]):
        tags.append("户外徒步")
    if not tags:
        tags.append("日常记录")
    return tags


def run_visual_audit(image_paths: List[str]) -> Dict[str, Any]:
    """
    基础视觉审计：根据图片文件名输出结构化标签

    Args:
        image_paths: 图片文件路径列表（可为空）
    """
    if not image_paths:
        image_paths = []

    visual_tags = []
    mount_visuals = set()
    usage_contexts = set()

    for path in image_paths:
        filename = os.path.basename(path)
        tags = _guess_tags_from_filename(filename)
        visual_tags.extend(tags)

        if "helmet" in filename.lower():
            mount_visuals.add("头盔固定")
        if "bike" in filename.lower():
            mount_visuals.add("车把固定")
            usage_contexts.add("骑行记录")
        if "surf" in filename.lower() or "water" in filename.lower():
            usage_contexts.add("水下探索")

    if not visual_tags:
        visual_tags = ["日常记录", "室外场景"]
    if not mount_visuals:
        mount_visuals.add("多配件通用挂载")
    if not usage_contexts:
        usage_contexts.add("户外运动")

    audit = {
        "visual_tags": list(dict.fromkeys(visual_tags))[:5],
        "mount_visuals": list(mount_visuals),
        "usage_context_hints": list(usage_contexts),
        "compliance_flags": [
            {"flag": "no_weapon", "status": "pass"},
            {"flag": "no_sensitive_scene", "status": "pass"}
        ]
    }

    return audit


__all__ = ["run_visual_audit"]
