# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的语义版本化约定。

## [1.1.4] — 2026-09-01

### 文档
- README 精简为 PyPI 友好版（504行→264行，英文为主+中文快速上手）。

### 工程
- 分类关键词表（classifier 段）补全英文词（只增不删）：zh、creative、vision、writing 类别扩充地道英文关键词（每个 10–18 个），清除无意义堆砌词（semantic/semantics 等废话）。
- 清理残留文件：`temp_edit8.py`、`config/routing.yaml.backup` 已删除。

## [1.1.1] — 2026-08-31

### 修复
- 移除 `config.py` 中 `reload()` 里无实际作用的空循环（重构残留）。

### 文档
- README 改为双语一体：英文在前、中文在后，移除语言切换元注释，保持专业简洁。
- README 描述改为地道英文翻译（`Decisions and execution, separated.` 等）。
- 仓库描述、Topics 更新，便于搜索发现。

### 工程
- 新增 GitHub Actions CI（Python 3.10–3.13 自动测试）。
- 测试徽章改用真实 CI 徽章（`actions/workflows/test.yml/badge.svg`）。
- 发布到 PyPI（`pip install router-brain`）。

## [1.1.0] — 2026-08-30

### 新增
- 首次公开发布，完整框架：决策/执行分离架构。
- 派活-反馈-重派闭环，多模型交叉验证对抗幻觉。
- 多通道 failover / 重试 / 降级 / 熔断 / 永久性错误熔断。
- 便宜优先 + direct 快问快答。
- 中英关键词分类器（毫秒级、零成本）。
- 一键免费模型同步（`sync-free-models`）。
- 全链路 `task_id` 贯穿 + 结构化 JSON 日志（不落密钥）。
- `healthcheck` 全量冒烟探测。
- 工人完整标准工具集（`worker-standard.yml`）+ 过程可审计（`📋 工人工作过程`）。
- 通用隧道支持（网络受限地区直连海外 API）。
- DSH `agent-presets/router-brain/` 预设（复制即用）。

### 文档
- README 痛点导向（注意力涣散 / 幻觉 / 成本 + 深层价值）。
- 中英双语完整文档、示例配置（`examples/pool.example.yaml`）、Issue/PR 模板。
- CONTRIBUTING、CHANGELOG、MIT License。

### 工程
- 45 个离线单元测试（独立 fixture，不依赖任何真实配置）。
- 空池报错改为引导提示（指向 `config/pool.yaml` 与 README）。
- 发布版与本地工作版分离（`bai_link.py` 本地私有，不进仓库/包）。
