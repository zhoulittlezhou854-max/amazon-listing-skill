# fixtures/ INDEX

## 目的
存放测试夹具数据，用于测试和模拟。

## 内容结构
```
fixtures/
├── INDEX.md (此文件)
└── (暂无夹具文件)
```

## 夹具类型
### 数据夹具
- JSON/CSV测试数据
- 模拟API响应
- 配置文件

### 对象夹具
- 模拟对象
- 测试双体
- 桩和模拟

### 资源夹具
- 测试图片
- 模板文件
- 临时文件

## 命名规范
```
fixture_<purpose>_<description>.<ext>
```
示例：
- `fixture_scoring_input.json`
- `fixture_copy_output.md`
- `fixture_risk_data.csv`

## 使用指南
1. 夹具应小而专注
2. 保持与生产数据格式一致
3. 避免敏感信息
4. 定期更新

## 相关链接
- [tests/INDEX.md](../INDEX.md): 测试目录总索引
- [data/fixtures/](../../data/fixtures/): 数据测试夹具

## 最后更新
2026-04-03: 初始创建