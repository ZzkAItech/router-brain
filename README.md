# router-brain · 模型路由大脑

> 把「决策」和「执行」分开：**大脑只做决策、不被细节干扰；工人专注干活、上下文短小**。
> 用对的钱、对的模型，把复杂任务拆开做完，还能互相验证、对抗幻觉。

<p align="center">
<a href="https://github.com/ZzkAItech/router-brain"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ZzkAItech/router-brain?style=flat-square&label=Stars"></a>
<a href="https://github.com/ZzkAItech/router-brain"><img alt="GitHub forks" src="https://img.shields.io/github/forks/ZzkAItech/router-brain?style=flat-square&label=Forks"></a>
<a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square"></a>
<a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square"></a>
<a href="#"><img alt="tests" src="https://img.shields.io/badge/tests-45%20passed-green?style=flat-square"></a>
</p>

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
- 自动挂多路**免费额度**（免费模型池），优先用免费。

> 钱花在刀刃上：决策花小钱，重活花该花的钱，能白嫖绝不自费。

---

## 除了表面痛点，它还解决了什么

### 🔗 不被任何一家模型供应商绑架

**问题**：代码一旦写死某个模型的 API，就被那家供应商绑架——它调价、下线、限流，你都得受着；换一家要重写一堆代码。

**router-brain 的做法**：模型是**可插拔的池子**。所有模型只在 `pool.yaml` 里登记，换供应商、加新模型、撤旧模型，都只是改一行配置，代码一行不动。你今天用 A 家，明天换 B 家，后天全用免费模型——框架完全无所谓。

### 🧯 一个 API 挂掉，任务不会全停

**问题**：没有调度层时，你调用的那一个 API 一旦 429、限流、配额用完、临时故障，整个任务就卡死或失败，前面全白做。

**router-brain 的做法**：**多通道 failover + 熔断 + 重试**。同一个模型可挂多个通道；主通道挂了自动切备通道；连续失败熔断冷却，不再白白撞墙。任务不会因为"那一家挂了"就中断。

### ⏳ 长任务不怕中途失败

**问题**：一个要跑几小时的大任务，任何一步失败都可能导致整条流水线作废——尤其长任务里模型容易在中间某步出错。

**router-brain 的做法**：任务被**拆成独立子任务**，每个子任务单独派活、单独验收。哪一步失败了，就只重做那一步（或换个模型），其余已完成的不受影响。长任务用 `goal` 工具跨轮持续推进，绝不中途放弃。

### 🧮 配额定额管得住，不浪费

**问题**：很多模型有每日/每周配额或金额上限。没有管理时，要么超额被停，要么不知道该省着用。

**router-brain 的做法**：**便宜优先 + 健康检查 + 熔断**。默认从最便宜的可用模型开始；`healthcheck` 逐个探测哪些模型现在真能用；配额低的通道自动降级不用。钱花在刀刃上，免费额度优先，绝不浪费配额去撞一个快没的模型。

### 🧠 上下文不爆炸，成本随任务涨

**问题**：复杂任务直接塞给一个模型，上下文越滚越大——又贵又容易"迷失"，还容易触发超长截断。

**router-brain 的做法**：**决策/执行分离天然控制上下文**。大脑只拿"目标+当前局面"这种小上下文做决策，工人每个子任务的上下文都短小专注——不需要一个模型记住全盘，也就不需要为"记忆"付出越来越高的 token 成本。

### 🔄 模型下线、新模型上线，不用改代码

**问题**：模型有生命周期——会下线、会改名、会有新版。写死在代码里的模型，下线了你还在白白调用失败。

**router-brain 的做法**：**永久性错误熔断 + 免费模型同步**。模型停服/不存在立即熔断不浪费调用；`sync-free-models` 一键把最新可用模型写进池子。模型生态变了，你只是改配置，不是改代码。

### 🎯 多模型协作，各用所长、互相兜底

**问题**：没有一个模型全知全能——有的擅长代码、有的擅长推理、有的擅长中文、有的适合看图。手动作业选模型很累，且容易用错。

**router-brain 的做法**：把多个模型当**专业工人团队**。大脑按子任务性质从池子里选最合适的；关键结论让**不同模型交叉验证**（不单模型自证）。能力互补、互相兜底，整体比单个最强模型更可靠。

### ✍️ 不会写提示词？大脑帮你写

**问题**：很多人知道 AI 能干活，但不会写提示词——不知道该怎么描述任务、该用哪个模型、该开多高的推理强度。提示词写得不好，模型就干不好，然后更觉得"AI 没用"。

**router-brain 的做法**：**把提示词工程自动化**。你只需要说清楚**目标**（"把这个项目重构一下"、"整理这些数据出报告"），剩下全是大脑的事：
- 大脑自动**拆解**成子任务，并**写出每个子任务的提示词**（含红线、产出路径、输出格式）；
- 大脑自动**选模型**——按任务性质从池子里挑合适的，你不需要知道哪个模型擅长什么；
- 大脑自动**定推理强度**——简单步骤用轻档省成本，复杂推理用重档，你不用懂这些参数。

> 你负责"要什么"，大脑负责"怎么要"。**不会写提示词也能用好 AI**——这大概是它最亲民的价值。

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

> ⚠️ **首次使用必看**：不配置模型池，`router-brain` 会提示「模型池里没有可用模型」。
> 这是正常的——先填 `config/pool.yaml` 再跑。一个最简配置（一个通道 + 一个模型）就够起步：
>
> ```yaml
> providers:
>   my_channel:
>     base_url: https://api.example.com/v1
>     credential_key: MY_API_KEY
>
> models:
>   my-model:
>     kind: general
>     cost: free
>     context: 131072
>     providers:
>       - {channel: my_channel, dsh_provider: my_channel}
> ```

### 3. 跑起来

```bash
router-brain list-models                            # 先看你的模型池（确认配置生效）
router-brain route "写个 Python 脚本"               # 只看路由决策（不执行）
router-brain run "把 /tmp 下的数据整理成一份报告"   # 路由→派活→降级→汇总
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

## 核心亮点

### 🧠 决策 / 执行分离 —— 对抗注意力涣散

大脑只看「目标 + 当前局面 + 该派谁」，不接触执行细节，注意力始终集中在判断上；
工人每个子任务上下文短小，只盯眼前一件事，不会因为要"记得全盘"而迷失。

### 🔁 派活-反馈-重派闭环 —— 对抗幻觉

大脑派活 → 工人干完 → 结果回传 → 大脑检查达标 → 不达标重派/换模型。
关键结论强制**多模型交叉验证**（不同厂商独立计算，一致才采信）——一个人会骗你，多个模型互相兜底不容易骗到底。

### 💰 便宜优先 + 一键免费模型同步

- 默认选 `cost=free/low` 的可用模型；简单问答走 direct 秒回，不启动 agent；
- `router-brain sync-free-models`：一键拉取**最新免费模型**写入池子，派活实时可用，自动跳过已存在。

### 🛡️ 生产级容错

| 机制 | 说明 |
|---|---|
| 多通道 failover | 一个模型挂多通道，主通道限流/停服自动切备通道 |
| 重试 + 降级 + 熔断 | 429/超时/5xx 重试；失败沿候选链换模型；连续失败熔断冷却 |
| 永久性错误熔断 | 模型停服/不存在（deprecated/not found）→ 立即熔断，不浪费配额 |
| 实时生效 | 改 `pool.yaml`/`routing.yaml` 即刻生效，无需重启 |

### 🧭 智能调度细节

- **无硬分工**：不写死"任务类型→模型"，分工由大脑运行时判断；
- **中英关键词分类器**：任务自动分类（code/debug/math/plan/complex/writing/creative/vision/qa…），快问快答直走 API；
- **vision 图片支持**：`--images` 传逗号分隔的图片路径/URL，自动派给视觉模型；
- **worker 通道开关**：通道可标记 `worker:false`（只作大脑、不派工人）；
- **配置模板化**：`pool.yaml` 是空模板，用户自己填模型和 key，框架不绑定任何具体厂商。

### ⚡ 其它闪光点

- **毫秒级任务分类**：分类器是确定性规则（零成本、零延迟），不消耗任何模型调用就能判任务类型；
- **决策即可程序化读取**：`route` 只输出路由 JSON（执行模式+建议模型+理由），供大脑或其它程序直接消费，不附带执行副作用；
- **失败换模型辅助决策**：派活失败时引擎列出「失败模型 + 当前可用模型清单」，帮大脑快速决定换哪个，而不是盲试；
- **全链路 task_id 贯穿**：一次派活从路由到执行到日志，同一个 `task_id` 贯穿全程，任意一步可回查；
- **结构化 JSON 日志**：日志写 stderr、JSON 格式、**绝不落任何密钥**，方便接日志系统或脚本分析；
- **healthcheck 冒烟**：`router-brain healthcheck` 逐个探测模型池，确认哪些现在真能用（限流/停服一目了然）。

### 👷 工人 = 完整 agent，过程可审计

- **工人 = 完整标准工具集**：派出去的 worker 注入 `worker-standard.yml`（bash/fs/jobs/goal/todo/skill/web 等），不是精简 bundle——工人具备与 GUI 同等的完整能力来干活。
- **工人过程全透明**：每次派活后，工人的实际步骤轨迹（写了什么文件、跑了什么命令、中间输出）会被提取出来，附在结果里（`📋 工人工作过程` 区块），大脑读进汇报，用户也能看到工人每一步干了什么。
- **跨轮长任务持续**：复杂任务用 `goal` 工具创建目标，跨轮持续推进，绝不中途放弃；`--cwd` 指定工作目录，工人不会跑错位置。

### 🌐 网络受限地区也能用

框架内置**通用隧道支持**：在 `pool.yaml` 的 provider 配置里设 `tunnel_host` / `tunnel_port`，direct 客户端连到隧道地址，但 TLS SNI 和 Host 头仍用目标主机——网络受限地区（如国内访问海外 API）也能用。

### 🔧 丰富的派活参数

`router-brain run` 支持：

| 参数 | 作用 |
|---|---|
| `--force-model <模型>` | 大脑绕过路由，强制指定模型 |
| `--cwd <目录>` | 工人工作目录 |
| `--images <图片路径>` | 逗号分隔的图片路径/URL（vision 任务） |
| `--timeout <秒数>` | 工人超时 |
| `--tools-mode <模式>` | headless 工具模式（native/code/both） |
| `--auto-failover` | 失败时由引擎自动换模型（默认停下让大脑决定） |
| `--hints <提示>` | 给路由的额外提示 |

### 🔒 安全设计

- **从不打印 key**：direct 模式按需取一次，agent 模式连 key 都不碰；
- 工人子进程工作目录 = `--cwd`，文件权限遵循 DSH 沙箱策略；
- 密钥永不出现在日志与输出中。

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
├── agent-presets/
│   └── router-brain/         DSH 预设（复制到 ~/.dsh/.agent-presets/ 即用）
│       ├── agent.cordis.yml  指挥官 persona + 工具集
│       ├── preset.yml        预设元信息
│       └── skills/           派活 skill（SKILL.md）
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
