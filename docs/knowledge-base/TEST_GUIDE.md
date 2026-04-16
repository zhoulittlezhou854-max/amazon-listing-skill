# TEST GUIDE – Amazon Listing Generator

日期：2026-04-03  
目的：验证增量实现（Step 0~9）在本地可一次跑通，并产出 PRD v8.4.0 要求的核心文件。

---

## 1. 准备
1. 确认当前目录为 `amazon-listing-skill`。
2. 已创建 `config/samples/run_config.json`，其中文件路径均指向 `sample_data/` 目录。
3. Python 版本 ≥3.9（系统自带即可）。

---

## 2. 执行命令
```bash
python3 main.py --steps 0,3,5,6,7,8,9 --config config/samples/run_config.json --output-dir output
```
- 若要跑完整链路，可将 `--steps` 省略，默认执行 0~9。
- 输出日志会在控制台展示每个 Step 的结果。

---

## 3. 预期输出

运行成功后，`output/` 目录下应包含：

| 文件 | 说明 |
| --- | --- |
| `preprocessed_data.json` | Step 0 预处理摘要 |
| `writing_policy.json` | Step 5 生成的策略 |
| `generated_copy.json` | Step 6 文案草稿 |
| `risk_report.json` | Step 7 风险检查 |
| `scoring_results.json` | Step 8 算法评分（含 Module 8 细表） |
| `listing_report.md` | Step 9 最终仲裁报告（Module 1-8） |
| `execution_summary.json` | 整体执行摘要 |

如需调试 Node 2/3/4，可运行：
```bash
python3 main.py --steps 0,1,2,4 --config config/samples/run_config.json
```
生成 `visual_audit.json`, `arsenal_output.json`, `intent_graph.json`。

---

## 4. 结果检视要点
- `scoring_results.json` 中 `total_score` 应大于 0，`rating` 字段存在。
- `listing_report.md` 的 Module 8 部分应含 A10/COSMO/Rufus/价格四张表以及算法对齐摘要。
- `risk_report.json` 的 `overall_passed` 为 `true`（若为 false，查看 `issues`）。

---

## 5. 常见问题 & 解决
- **文件路径找不到**：确认 `config/samples/run_config.json` 中的相对路径在当前仓库根目录执行时可访问。
- **编码问题**：所有样例文件均为 UTF-8，无需额外处理。
- **缺少依赖**：本项目仅依赖标准库，如启动报错请检查 Python 版本或虚拟环境。

---

> 按以上步骤即可完成明天的冒烟测试。若需替换真实数据，只需更新 `sample_data/` 内文件并调整 `config/samples/run_config.json` 指向即可。
