# Amazon Listing Skill

项目为 Amazon Listing 生成和优化工具，提供评分、文案生成、风险检查等功能。

## 功能特性

- **智能评分**: 对 Amazon Listing 进行多维度评分
- **文案生成**: 基于关键词库生成优化文案
- **风险检查**: 识别潜在风险和违规内容
- **策略优化**: 多种写作策略和变体支持
- **压力测试**: 策略性能测试和比较

## 项目结构

```
amazon-listing-skill/
├── modules/          # 核心业务模块
├── tools/           # 工具函数
├── config/          # 配置文件
├── data/            # 数据文件
├── output/          # 输出文件
├── docs/            # 文档
├── tests/           # 测试文件
├── archive/         # 归档文件
└── utils/           # 工具目录
```

详细结构请参考 [INDEX.md](INDEX.md) 和 [REPO_RULES.md](REPO_RULES.md)。

## 快速开始

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **配置环境**
   - 复制 `config/samples/` 中的配置文件
   - 根据产品和国家修改配置

3. **运行主程序**
   ```bash
   python main.py --config config/de-t70m-run.json
   ```

4. **启动本地控制台**
   ```bash
   streamlit run app/streamlit_app.py
   ```
   - Tab 1：新品上架，上传 4 张核心表并直接生成报告
   - Tab 2：老品数据反补，导入 SellerSprite/PPC 词表后做人机共审并重构 Listing

## 核心模块

| 模块 | 功能 |
|------|------|
| `scoring.py` | 评分算法 |
| `copy_generation.py` | 文案生成 |
| `writing_policy.py` | 写作策略 |
| `keyword_arsenal.py` | 关键词库 |
| `risk_check.py` | 风险检查 |
| `report_generator.py` | 报告生成 |

完整模块列表见 [modules/INDEX.md](modules/INDEX.md)。

## 测试

运行测试：
```bash
python -m pytest tests/ -v
```

## 文档

- [REPO_RULES.md](REPO_RULES.md): 仓库结构和命名规则
- [CLAUDE.md](CLAUDE.md): Claude代理规则
- [docs/](docs/): 详细文档目录

## 许可证

版权所有 (c) 2026 Amazon Listing Skill 项目团队。
