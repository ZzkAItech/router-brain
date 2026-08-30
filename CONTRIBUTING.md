# 贡献指南

欢迎贡献!router-brain 是一个开放框架,任何改进都被欢迎。

## 怎么开始

1. Fork 本仓库
2. `pip install -e ".[dev]"` 安装开发依赖
3. 在 `config/pool.yaml` 配你的模型(参考 README)
4. 跑 `python -m unittest discover -s tests` 确保测试能过

## 代码风格

- Python 3.10+,类型注解
- 测试用 `unittest`(不是 pytest)
- 新增功能必须带测试

## 提 PR 前

- 测试全绿: `python -m unittest discover -s tests`
- 如果你的改动涉及模型选择逻辑,确保 `config/pool.yaml` 模板不变(不内置具体模型)
- 不要提交任何 API key 或个人配置

## 发布原则

- `config/pool.yaml` 是模板,不包含任何具体模型
- 所有凭据走 `~/.dsh/.credentials.yaml` 或环境变量
- 代码里**绝不硬编码 API key**