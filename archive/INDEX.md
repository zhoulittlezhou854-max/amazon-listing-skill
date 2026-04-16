# archive/ INDEX

## 目的
存放归档文件、历史数据和不再活跃的文件。

## 内容结构
```
archive/
├── INDEX.md (此文件)
├── legacy/            # 遗留文件
├── tmp_snapshots/     # 临时快照
├── deprecated_docs/   # 废弃文档
└── test_scripts/      # 测试脚本归档
```

## 目录说明
| 目录 | 说明 | 文件数量 | 用途 |
|------|------|----------|------|
| legacy/ | 遗留文件和历史输出 | 0目录 | 历史运行输出和旧版本 |
| tmp_snapshots/ | 临时快照 | 0文件 | 临时备份和快照 |
| deprecated_docs/ | 废弃文档 | 0文件 | 不再使用的文档 |
| test_scripts/ | 测试脚本归档 | 4文件 | 压力测试和性能测试脚本 |

## 归档策略
1. **legacy/**: 历史运行输出、旧配置、不再使用的代码
2. **tmp_snapshots/**: 临时备份，可定期清理
3. **deprecated_docs/**: 废弃文档，保留参考价值
4. **test_scripts/**: 测试脚本归档，不再使用的测试和压测脚本

## 使用指南
1. 不再活跃但需要保留的文件放入对应目录
2. 使用描述性目录名
3. 定期审查（每季度）
4. 完全无价值的文件可删除

## 命名规范
归档目录命名：`<type>_<yyyy-mm>_<description>`
示例：
- `output_de_2026-04_german_runs`
- `config_old_2026-03_deprecated`

## 相关链接
- [REPO_RULES.md](../REPO_RULES.md): 仓库规则
- [cleanup_candidates.md](../cleanup_candidates.md): 清理候选项

## 最后更新
2026-04-03: 初始创建