#!/usr/bin/env python3
"""
简化的策略压测脚本 - 修正版
"""

import json
import os
import shutil
import subprocess
import sys
import importlib
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
VARIANTS_DIR = PROJECT_ROOT / "strategy_variants"

VARIANTS = ["scene_v1", "scene_v2", "scene_v3", "kw_aggressive_l1", "kw_l2_focus", "kw_conservative"]


def run_steps(output_dir: str, steps: str) -> bool:
    """运行指定步骤"""
    cmd = [
        sys.executable, "main.py",
        "--config", str(PROJECT_ROOT / "run_config.json"),
        "--output-dir", output_dir,
        "--steps", steps
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.returncode == 0


def load_scores(output_dir: str) -> dict:
    """加载评分结果"""
    path = Path(output_dir) / "scoring_results.json"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def extract_metrics(scores: dict) -> dict:
    """提取关键指标"""
    a10 = scores.get("a10", {})
    cosmo = scores.get("cosmo", {})
    rufus = scores.get("rufus", {})

    return {
        "total_score": scores.get("total_score", 0),
        "a10_total": scores.get("a10_score", 0),
        "cosmo_total": scores.get("cosmo_score", 0),
        "rufus_total": scores.get("rufus_score", 0),
        "price_score": scores.get("price_competitiveness_score", 0),
        "title_front_80": a10.get("title_front_80", {}).get("score", 0) if isinstance(a10.get("title_front_80"), dict) else 0,
        "keyword_tiering": a10.get("keyword_tiering", {}).get("score", 0) if isinstance(a10.get("keyword_tiering"), dict) else 0,
        "conversion_signals": a10.get("conversion_signals", {}).get("score", 0) if isinstance(a10.get("conversion_signals"), dict) else 0,
        "scene_coverage": cosmo.get("scene_coverage", {}).get("score", 0) if isinstance(cosmo.get("scene_coverage"), dict) else 0,
        "capability_binding": cosmo.get("capability_scene_binding", {}).get("score", 0) if isinstance(cosmo.get("capability_scene_binding"), dict) else 0,
        "audience_tags": cosmo.get("audience_tags", {}).get("score", 0) if isinstance(cosmo.get("audience_tags"), dict) else 0,
    }


def main():
    print("=" * 80)
    print("策略压测开始 (修正版)")
    print("=" * 80)

    results = {}

    # 1. 首先建立 baseline - 运行完整流程
    print("\n>>> 建立 Baseline (完整流程 0,3,5,6,7,8,9)...")
    run_steps(str(OUTPUT_DIR), "0,3,5,6,7,8,9")
    baseline_scores = load_scores(OUTPUT_DIR)
    baseline_metrics = extract_metrics(baseline_scores)
    results["baseline"] = {
        "metrics": baseline_metrics,
        "scores": baseline_scores
    }
    print(f"Baseline: {baseline_metrics['total_score']}/310")
    print(f"  A10: {baseline_metrics['a10_total']} (title={baseline_metrics['title_front_80']}, tiering={baseline_metrics['keyword_tiering']}, conv={baseline_metrics['conversion_signals']})")
    print(f"  COSMO: {baseline_metrics['cosmo_total']} (scene={baseline_metrics['scene_coverage']}, binding={baseline_metrics['capability_binding']}, audience={baseline_metrics['audience_tags']})")

    # 读取baseline的generated_copy用于对比
    with open(OUTPUT_DIR / "generated_copy.json") as f:
        baseline_copy = json.load(f)
    print(f"\nBaseline Title: {baseline_copy.get('title', '')[:80]}")

    # 2. 对每个变体运行测试
    for variant_id in VARIANTS:
        print(f"\n>>> 测试变体: {variant_id}")
        variant_wp_path = VARIANTS_DIR / variant_id / "writing_policy.json"

        if not variant_wp_path.exists():
            print(f"  跳过: {variant_wp_path} 不存在")
            continue

        # 读取variant的writing_policy
        with open(variant_wp_path) as f:
            variant_wp = json.load(f)

        print(f"  keyword_allocation_strategy: {variant_wp.get('keyword_allocation_strategy', 'N/A')}")
        print(f"  scene_priority: {variant_wp.get('scene_priority', [])[:3]}...")

        # 复制 variant 的 writing_policy.json 到 output 目录
        # 注意：这会覆盖step 5生成的writing_policy
        shutil.copy2(variant_wp_path, OUTPUT_DIR / "writing_policy.json")

        # 清除copy_generation模块缓存，强制重新导入
        for mod in list(sys.modules.keys()):
            if 'copy_generation' in mod or 'modules.copy_generation' in mod:
                del sys.modules[mod]

        # 重新导入modules
        from modules import copy_generation
        importlib.reload(copy_generation)

        # 运行步骤 6,7,8,9 (文案生成、风险检查、评分、报告)
        # 注意：由于step 5已经运行过，writing_policy.json已被覆盖
        # 我们需要先恢复variant的writing_policy再运行6,7,8,9
        shutil.copy2(variant_wp_path, OUTPUT_DIR / "writing_policy.json")

        success = run_steps(str(OUTPUT_DIR), "6,7,8,9")

        if success:
            scores = load_scores(OUTPUT_DIR)
            metrics = extract_metrics(scores)
            results[variant_id] = {
                "metrics": metrics,
                "scores": scores
            }

            # 读取生成的copy用于对比
            with open(OUTPUT_DIR / "generated_copy.json") as f:
                variant_copy = json.load(f)
            print(f"  {variant_id} Title: {variant_copy.get('title', '')[:80]}")

            print(f"  {variant_id}: {metrics['total_score']}/310")
            print(f"  A10: {metrics['a10_total']} (title={metrics['title_front_80']}, tiering={metrics['keyword_tiering']})")
            print(f"  COSMO: {metrics['cosmo_total']} (scene={metrics['scene_coverage']}, binding={metrics['capability_binding']})")
        else:
            print(f"  运行失败")
            results[variant_id] = {"metrics": {}, "scores": {}}

    # 3. 生成对比表
    print("\n" + "=" * 80)
    print("策略压测对比表")
    print("=" * 80)

    baseline_m = results["baseline"]["metrics"]

    print("\n### A10 维度对比")
    print("| 策略变体 | title_front_80 | keyword_tiering | conversion_signals | A10总分 |")
    print("|----------|---------------|-----------------|-------------------|---------|")
    for vid, data in results.items():
        m = data["metrics"]
        if not m:
            continue
        d_title = f"+{m['title_front_80'] - baseline_m['title_front_80']}" if m['title_front_80'] != baseline_m['title_front_80'] else "="
        d_tier = f"+{m['keyword_tiering'] - baseline_m['keyword_tiering']}" if m['keyword_tiering'] != baseline_m['keyword_tiering'] else "="
        d_conv = f"+{m['conversion_signals'] - baseline_m['conversion_signals']}" if m['conversion_signals'] != baseline_m['conversion_signals'] else "="
        print(f"| {vid} | {m['title_front_80']} ({d_title}) | {m['keyword_tiering']} ({d_tier}) | {m['conversion_signals']} ({d_conv}) | {m['a10_total']} |")

    print("\n### COSMO 维度对比")
    print("| 策略变体 | scene_coverage | capability_binding | audience_tags | COSMO总分 |")
    print("|----------|----------------|-------------------|---------------|---------|")
    for vid, data in results.items():
        m = data["metrics"]
        if not m:
            continue
        d_scene = f"+{m['scene_coverage'] - baseline_m['scene_coverage']}" if m['scene_coverage'] != baseline_m['scene_coverage'] else "="
        d_bind = f"+{m['capability_binding'] - baseline_m['capability_binding']}" if m['capability_binding'] != baseline_m['capability_binding'] else "="
        d_aud = f"+{m['audience_tags'] - baseline_m['audience_tags']}" if m['audience_tags'] != baseline_m['audience_tags'] else "="
        print(f"| {vid} | {m['scene_coverage']} ({d_scene}) | {m['capability_binding']} ({d_bind}) | {m['audience_tags']} ({d_aud}) | {m['cosmo_total']} |")

    print("\n### 总分对比")
    print("| 策略变体 | A10 | COSMO | Rufus | 价格 | 总分 | 评级 |")
    print("|----------|-----|-------|-------|------|------|------|")
    for vid, data in results.items():
        m = data["metrics"]
        if not m:
            continue
        grade = "优秀" if m['total_score'] >= 250 else "良好" if m['total_score'] >= 200 else "需改进"
        d_total = f"+{m['total_score'] - baseline_m['total_score']}" if m['total_score'] != baseline_m['total_score'] else "="
        print(f"| {vid} | {m['a10_total']} | {m['cosmo_total']} | {m['rufus_total']} | {m['price_score']} | {m['total_score']} ({d_total}) | {grade} |")

    # 4. 保存结果
    output_path = VARIANTS_DIR / "stress_test_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")

    # 5. 总结
    print("\n" + "=" * 80)
    print("策略压测总结")
    print("=" * 80)

    valid_results = {k: v for k, v in results.items() if v["metrics"]}
    if valid_results:
        best_total = max(valid_results.items(), key=lambda x: x[1]["metrics"].get("total_score", 0))
        best_tiering = max(valid_results.items(), key=lambda x: x[1]["metrics"].get("keyword_tiering", 0))
        best_scene = max(valid_results.items(), key=lambda x: x[1]["metrics"].get("scene_coverage", 0))

        print(f"\n最高总分: {best_total[0]} ({best_total[1]['metrics'].get('total_score', 0)}/310)")
        print(f"最高keyword_tiering: {best_tiering[0]} ({best_tiering[1]['metrics'].get('keyword_tiering', 0)}/30)")
        print(f"最高scene_coverage: {best_scene[0]} ({best_scene[1]['metrics'].get('scene_coverage', 0)}/40)")

        # 关键洞察
        print("\n### 关键洞察")

        for vid, data in valid_results.items():
            if vid == "baseline":
                continue
            m = data["metrics"]
            insights = []

            if m.get('keyword_tiering', 0) > baseline_m.get('keyword_tiering', 0):
                insights.append(f"keyword_tiering提升{m['keyword_tiering'] - baseline_m['keyword_tiering']}分")
            elif m.get('keyword_tiering', 0) < baseline_m.get('keyword_tiering', 0):
                insights.append(f"keyword_tiering下降{baseline_m['keyword_tiering'] - m['keyword_tiering']}分")

            if m.get('scene_coverage', 0) > baseline_m.get('scene_coverage', 0):
                insights.append(f"scene_coverage提升{m['scene_coverage'] - baseline_m['scene_coverage']}分")
            elif m.get('scene_coverage', 0) < baseline_m.get('scene_coverage', 0):
                insights.append(f"scene_coverage下降{baseline_m['scene_coverage'] - m['scene_coverage']}分")

            if m.get('total_score', 0) > baseline_m.get('total_score', 0):
                insights.append(f"总分提升{m['total_score'] - baseline_m['total_score']}分")
            elif m.get('total_score', 0) < baseline_m.get('total_score', 0):
                insights.append(f"总分下降{baseline_m['total_score'] - m['total_score']}分")

            if insights:
                print(f"\n- {vid}:")
                for ins in insights:
                    print(f"  - {ins}")

    print("\n策略压测完成！")


if __name__ == "__main__":
    main()