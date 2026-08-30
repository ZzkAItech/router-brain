# router-brain · 模型路由大脑

> 把「决策」和「执行」分开：**大脑只做决策、不被细节干扰；工人专注干活、上下文短小**。
> 用对的钱、对的模型，把复杂任务拆开做完，还能互相验证、对抗幻觉。

---

## 它解决什么痛点

### 🎯 痛点一：大模型注意力不集中——上下文一长就抓不住重点

**问题**：一个超长任务全部塞给一个模型，它要同时记住目标、背景、已完成部分、当前步骤……上下文越长，模型越容易迷失重点（Lost in the Middle），前面讲的到后面就忘。

**router-brain 的做法**：**决策与执行分离**。

- **大脑模型只做决策**——它只看「目标 + 当前局面 + 该派谁」，不接触任务的具体细节。因为**大脑不被过多细节干扰**，它的注意力始终集中在判断上，不会迷失。
- **工人模型专注单点**——每个子任务独立派发、上下文短小，工人只盯着眼前这一件事，不会因为要"记得全盘"而走神。

> 大脑不干活，所以大脑不累；工人只干一件活，所以工人不迷。

### 🌀 痛点二：大模型幻觉——一本正经地胡说八道

**问题**：单个模型一次生成，错了也没人拦。多步任务里一旦某一步产生幻觉，后面全跟着错，而且很难发现。

**router-brain 的做法**：**派活-反馈-重派闭环**。

- 大脑派活 → 工人干完 → **结果回传给大脑**；
- 大脑检查是否达标：不达标就**重派/换模型**，直到达标或确认无解；
- 一个模型反复失败/输出可疑时，自动换另一个模型试——**模型之间互相兜底，幻觉很难一路错到底**。

> 一个人可能骗你，多个人交叉验证就不容易骗到底。

### 💰 痛点三：成本不可控——好模型贵、烂模型浪费

**问题**：复杂任务全程用贵模型，简单步骤也用贵模型，钱烧得快；反过来为省钱全用便宜模型，又干不动复杂活。

**router-brain 的做法**：**按需分配、便宜优先**。

- **大脑用便宜/免费模型**——它只做判断，不需要最强模型；
- **简单任务（问答/分类/提取）走 direct 快问快答**——不启动 agent，秒回；
- **复杂任务才派工人**——从便宜到贵逐级尝试，能省则省；
- 自动挂多路**免费额度**（OpenRouter 免费、各厂商免费模型），优先用免费。

> 钱花在刀刃上：决策花小钱，重活花该花的钱，能白嫖绝不自费。

---

## 一句话架构

```
你（目标）
  └─> 🧠 大脑（便宜模型，只看决策）──拆解──> 👷 工人1（模型A，干一件活）
                                       ├──> 👷 工人2（模型B，干另一件活）
                                       └──> 🔁 反馈回来，不达标重派/换模型
```

- **决策面**（本进程）：分类任务 → 选模型 → 派活 → 看反馈 → 决定下一步；
- **执行面**（DeepSeek Harness headless agent）：带真实工具（bash/文件/工作区）的 agent 实际干活。

> 每个工人都是**真 agent**：不是"问一句返回一段文字"，而是能**写文件、跑脚本、读回结果**的完整执行单元。

---

## 快速开始

### 1. 安装

```bash
cd router-brain
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

依赖仅 PyYAML。需要本机已安装 **DeepSeek Harness**（`dsh` 在 PATH）。

### 2. 配置你的模型池

router-brain **不内置任何模型/通道**——它只是一个调度框架，模型由你自己配。

`config/pool.yaml` 是模板，按结构填你的：
- **providers**：API 通道（base_url + 凭据名）
- **models**：你能用的模型（id + 通道 + 成本 + 类型）

凭据放 `~/.dsh/.credentials.yaml` 或同名环境变量，框架自动读取，**从不打印 key**。
改完配置文件**即刻生效**，无需重启。

### 3. 跑起来

```bash
router-brain run "把 /tmp 下的数据整理成一份报告"   # 路由→派活→降级→汇总
router-brain list-models                            # 看你的模型池
router-brain route "写个 Python 脚本"               # 只看路由决策（不执行）
router-brain dashboard                              # 实时看大脑派活过程
```

### 4.（可选）在 DeepSeek Harness 里启用「路由大脑」模式

仓库自带 `agent-presets/router-brain/` 预设（指挥官 persona + 派活 skill）。启用后，DSH 新会话选择器里会出现「路由大脑」选项——它变成**常驻指挥官**：你给一个目标，它自己拆解、派活、看反馈、迭代到完成，最后全面汇总。

**安装**（把预设拷到 DSH 的预设目录）：

```bash
mkdir -p ~/.dsh/.agent-presets
cp -r agent-presets/router-brain ~/.dsh/.agent-presets/
# 重启 dsh web，新会话的选择器里选「路由大脑」
```

> 该预设只带指挥官需要的工具（bash/fs/jobs/goal/todo/skill），不内置任何模型——
> 大脑和工人用的模型都来自你的 `config/pool.yaml`。预设通过 bash 调用 `router-brain` CLI 派活。

---

## 核心能力

| 能力 | 说明 |
|---|---|
| 决策/执行分离 | 大脑只判断，工人专注干活 → 缓解注意力涣散 |
| 派活-反馈闭环 | 结果回传、不达标重派/换模型 → 对抗幻觉 |
| 无硬分工 | 不写死"任务类型→模型"，分工由大脑判断 |
| 多通道 failover | 一个模型挂多通道，主通道限流自动切备 |
| 重试+降级+熔断 | 429/超时/5xx 重试；失败换模型；连续失败熔断冷却 |
| 便宜优先 | 默认选 cost=free/low 的可用模型 |
| direct 快问快答 | 问答/分类/提取秒回，不启动 agent |
| worker 通道开关 | 通道可标记 `worker:false`（只作大脑、不派工人） |
| 实时派活面板 | 网页看大脑每步派活/工人进度/耗时 |

---

## 配置说明

### config/routing.yaml

```yaml
execution:
  max_retries: 2              # 瞬态失败重试次数
  max_fallbacks: 4            # 换模型降级上限
  timeout_seconds: 600        # 单任务超时
  auto_failover: false        # false=失败停下让大脑决定换谁
  force_channel: ""           # 空=全部通道；填某通道名=只走该通道
  direct_max_tokens: 2048     # direct 模式 token 预算
```

### config/pool.yaml 模板

```yaml
providers:
  my_channel:
    base_url: https://api.example.com/v1
    credential_key: MY_API_KEY   # 在 ~/.dsh/.credentials.yaml 里放同名 key

models:
  my-model:
    kind: general
    cost: low
    context: 131072
    providers:
      - {channel: my_channel, dsh_provider: my_channel}
```

---

## 目录

```
router-brain/
├── config/
│   ├── pool.yaml             你的模型池（模板见文件内注释）
│   └── routing.yaml          路由规则 + 执行参数
├── src/router_brain/
│   ├── config.py             配置加载 + 模型池/通道/降级管理
│   ├── router.py             选模型
│   ├── degrade.py            重试 + 降级 + 熔断
│   ├── executor.py           agent/direct 执行
│   ├── llm_api.py            direct 模式客户端（错误分类）
│   └── cli.py                CLI 入口
├── tests/                    单元测试（全离线）
├── LICENSE                   MIT
└── README.md                 本文件
```

## 安全

- 从不读取并打印任何 key；direct 模式按需取一次，agent 模式连 key 都不碰。
- 工人子进程工作目录 = `--cwd`，文件权限遵循 DSH 沙箱策略。
- healthcheck 会消耗真实 API 配额（每次约十几次极小调用）。
- 密钥永不出现在日志与输出中。
