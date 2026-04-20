# Project Status

## Current Release Baseline
- Version: 2.1.0
- Run: H91lite_US_r28_hybrid_stabilize
- Date: 2026-04-20
- generation_status: live_success
- listing_status: READY_FOR_LISTING
- recommended_output: hybrid
- 四维评分: A10 90 / COSMO 92 / Rufus 100 / Fluency 30
- 全量测试: 321 passed
- 结论: hybrid v3 launch gate 通过，可作为当前上线基线

## Release Notes
- 统一 Title / Bullet 长度规则
- Title 从关键词拼接改为语义引导
- Blueprint 注入 audience allocation 并写入输出
- Bullet 维度去重检验与 repair 注入落地
- readiness_summary / listing_report / risk_report 状态源统一
- r16_v2a_fix 修复 mobility_commute 重复问题并恢复 READY_FOR_LISTING
- hybrid launch gate / final readiness verdict / LISTING_READY 导出已上线
- 修复 unsupported stabilization 重复注入、scrub 残句、hybrid 污染继承
- 修复 hybrid L2 backfill 句子拼接问题，避免 `capture.ideal ...` 残缺输出
