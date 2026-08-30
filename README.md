# router-brain · LLM Routing Brain

> **Decisions and execution, separated.** A lightweight "brain" model handles the thinking—decomposing your goal, choosing a model, dispatching workers, and reading their feedback. Each worker gets one focused, short-context subtask. Use the right model for the job, cross-validate important results, and keep costs down.

> **AI orchestration · multi-model routing · prompt automation · DeepSeek Harness** — You don't need to be a prompt engineer. Tell it *what* you want; the brain breaks the task down, writes the prompts, picks the model, sets the reasoning effort, dispatches workers, checks their output, and iterates until it's done.

<p align="center">
<a href="https://github.com/ZzkAItech/router-brain"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ZzkAItech/router-brain?style=flat-square&label=Stars"></a>
<a href="https://github.com/ZzkAItech/router-brain"><img alt="GitHub forks" src="https://img.shields.io/github/forks/ZzkAItech/router-brain?style=flat-square&label=Forks"></a>
<a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square"></a>
<a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square"></a>
<a href="https://github.com/ZzkAItech/router-brain/actions"><img alt="tests" src="https://github.com/ZzkAItech/router-brain/actions/workflows/test.yml/badge.svg"></a>
</p>

---

## Why router-brain

### 🎯 Problem 1: LLMs lose focus in long contexts
Hand a whole complex task to a single model and it has to hold the goal, background, progress, and current step all in one context. The longer the context, the more it drifts ("lost in the middle").

**router-brain separates decision from execution:**
- The **brain only decides**—it sees "goal + current state + whom to dispatch." It never wades into execution details, so its attention stays on judgment.
- Each **worker handles one short-context subtask**—it focuses on the single thing in front of it.

> The brain doesn't do the work, so the brain doesn't burn out; the worker does one thing, so it doesn't get lost.

### 🌀 Problem 2: Hallucination
A single model generates an answer with nobody checking it. In multi-step work, one hallucinated step corrupts everything downstream.

**router-brain uses a dispatch → feedback → re-dispatch loop:**
- The brain dispatches → the worker finishes → **the result comes back to the brain**;
- The brain checks whether it meets the bar; if not, it **re-dispatches or switches models** until the result is good enough—or confirms the task is truly unsolvable;
- Important conclusions are **cross-validated by different models**—one model might fool you, but several rarely agree on a lie.

### 💰 Problem 3: Costs that spiral out of control
Use an expensive model for everything and you burn through money fast; use cheap models for everything and hard tasks come out wrong.

**router-brain right-sizes every call, cheap first:**
- The **brain runs on a cheap or free model**—it only judges, it doesn't need the strongest model;
- **Simple tasks (QA / classify / extract) go direct**—instant reply, no agent startup;
- **Complex tasks dispatch a worker**, trying cheap models before expensive ones;
- **Free quotas get used automatically** whenever available.

---

## Architecture in one line

```
You (goal)
  └─> 🧠 Brain (cheap model, decides only) ──decompose──> 👷 Worker 1 (model A, one task)
                                                    ├──> 👷 Worker 2 (model B, another task)
                                                    └──> 🔁 feedback loop; re-dispatch / switch if not OK
```

- **Decision plane** (this process): classify → pick model → dispatch → read feedback → decide next.
- **Execution plane** (DeepSeek Harness headless agent): a real agent with tools (bash / files / workspace) actually does the work.

> Every worker is a **real agent**—not "ask a question and get text back," but "write files, run scripts, read the results."

---

## Quick start

### 1. Install

```bash
cd router-brain
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

The only dependency is PyYAML. You'll also need **DeepSeek Harness** installed (`dsh` on your PATH) and `~/.dsh/settings.yaml` configured (with your API providers). Without these, the agent-dispatch feature won't run—though `route` and `list-models` still work for testing.

### 2. Configure your model pool

router-brain ships with **no models or channels**—it's a scheduling framework; you add yours.

`config/pool.yaml` is a template. Fill in:
- **providers**: API channels (base_url + credential key name)
- **models**: the models you can use (id + channel + cost + kind)

Credentials go in `~/.dsh/.credentials.yaml` or same-named environment variables; the framework reads them and **never prints keys**. Changes take effect immediately—no restart needed.

### 3. Run

```bash
router-brain list-models                            # see your pool
router-brain route "write a python script"          # routing decision only (no execution)
router-brain run "turn /tmp data into a report"     # route → dispatch → fallback → summary
```

### 4. (Optional) Enable the "Router Brain" commander in DeepSeek Harness

The repo ships `agent-presets/router-brain/` (commander persona + dispatch skill). Enable it and a **「路由大脑 / Router Brain」** preset appears in the DSH session picker—it becomes a persistent commander: give it a goal, and it decomposes, dispatches, reads feedback, iterates to completion, then gives you a final summary.

```bash
mkdir -p ~/.dsh/.agent-presets
cp -r agent-presets/router-brain ~/.dsh/.agent-presets/
# restart dsh web, pick 「路由大脑」 in the new-session picker
```

> The preset ships only the commander's tools (bash / fs / jobs / goal / todo / skill) and no models—both brain and workers use models from *your* `config/pool.yaml`.

---

## Highlights

| Capability | Description |
|---|---|
| Decision / execution separation | Brain judges, worker executes → fights attention drift |
| Dispatch–feedback–re-dispatch | Results come back; re-dispatch or switch on failure → fights hallucination |
| Cross-model validation | Key results checked by different models, never self-proven |
| No hardcoded division of labor | The brain decides allocation at runtime |
| Multi-channel failover | One model on many channels; auto-switch on limit or shutdown |
| Retry + degrade + circuit breaker | Retry on 429/timeout/5xx; fall back down a chain; fuse on repeated failure |
| Permanent-error fuse | Deprecated / not-found models fuse instantly |
| Cheap-first | Defaults to free or low-cost available models |
| Direct fast-answer | QA / classify / extract reply instantly, no agent startup |
| Worker channel switch | `worker:false` marks brain-only channels |
| Millisecond classifier | Deterministic rules, zero cost, zero latency |
| Program-readable decisions | `route` emits JSON for the brain or other programs |
| Full-task trace | One `task_id` through everything; JSON logs, no secrets |
| healthcheck | Probe the whole pool to see what actually works |

---

## Configuration

### config/routing.yaml

```yaml
execution:
  max_retries: 2              # transient-failure retries
  max_fallbacks: 4            # model-fallback cap
  timeout_seconds: 600        # per-task timeout
  auto_failover: false        # false = stop and let the brain choose
  force_channel: ""           # "" = all channels; a name = only that channel
  direct_max_tokens: 2048     # direct-mode token budget
```

### config/pool.yaml template

```yaml
providers:
  my_channel:
    base_url: https://api.example.com/v1
    credential_key: MY_API_KEY   # put the key in ~/.dsh/.credentials.yaml

models:
  my-model:
    kind: general
    cost: low
    context: 131072
    providers:
      - {channel: my_channel, dsh_provider: my_channel}
```

---

## Directory

```
router-brain/
├── config/
│   ├── pool.yaml             your model pool (template)
│   └── routing.yaml          routing rules + execution params
├── agent-presets/
│   └── router-brain/         DSH preset (copy to ~/.dsh/.agent-presets/ to use)
├── src/router_brain/
│   ├── config.py             config + pool/channel/degrade management
│   ├── router.py             model selection
│   ├── degrade.py            retry + degrade + circuit breaker
│   ├── executor.py           agent/direct execution
│   ├── llm_api.py            direct-mode client (error classification)
│   └── cli.py                CLI entry
├── tests/                    unit tests (fully offline)
├── CONTRIBUTING.md           contribution guide
├── CHANGELOG.md              changelog
├── LICENSE                   MIT
└── README.md                 this file
```

---

## Security

- Never reads-and-prints any key; direct mode resolves a key once, agent mode never touches keys.
- Worker subprocess cwd = `--cwd`; file permissions follow the DSH sandbox policy.
- healthcheck consumes real API quota (~a dozen tiny calls per full run).
- Keys never appear in logs or output.

---

## 中文快速上手

> **把「决策」和「执行」分开：大脑只做决策、不被细节干扰；工人专注干活、上下文短小。用对的钱、对的模型，把复杂任务拆开做完，还能互相验证、对抗幻觉。**

### 核心价值
- **对抗注意力涣散**：决策/执行分离，大脑只看「目标+局面+派谁」，工人各司其职、上下文短小
- **对抗幻觉**：派活→反馈→重派闭环，关键结论多模型交叉验证
- **成本可控**：便宜优先，简单任务直连秒回，免费额度自动挂载
- **零厂商锁定**：模型全在 `pool.yaml` 配，换源不改代码
- **生产级容错**：多通道 failover、重试降级熔断、永久错误即熔断

### 一分钟上手

```bash
# 1. 安装
cd router-brain
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# 2. 配置模型池（必填，否则报错）
# 编辑 config/pool.yaml，填入你的通道与模型，最简示例：
# providers:
#   my_channel:
#     base_url: https://api.example.com/v1
#     credential_key: MY_API_KEY
# models:
#   my-model:
#     kind: general
#     cost: free
#     context: 131072
#     providers:
#       - {channel: my_channel, dsh_provider: my_channel}

# 3. 跑起来
router-brain list-models                            # 确认模型池
router-brain route "写个 Python 脚本"               # 仅看路由决策
router-brain run "把 /tmp 下的数据整理成一份报告"   # 全流程：路由→派活→降级→汇总
```

### 关键 CLI 参数

| 参数 | 作用 |
|---|---|
| `--force-model <模型>` | 大脑绕过路由，强制指定模型 |
| `--cwd <目录>` | 工人工作目录 |
| `--images <路径>` | 逗号分隔的图片路径/URL（vision 任务） |
| `--timeout <秒数>` | 工人超时 |
| `--auto-failover` | 失败时引擎自动换模型（默认停下让大脑决定） |
| `--hints <提示>` | 给路由的额外提示 |

### 在 DeepSeek Harness 里用「路由大脑」常驻指挥官

```bash
mkdir -p ~/.dsh/.agent-presets
cp -r agent-presets/router-brain ~/.dsh/.agent-presets/
# 重启 dsh web，新会话选择器里选「路由大脑」
```

> 预设只带指挥官工具（bash/fs/jobs/goal/todo/skill），不内置模型——大脑和工人都用你的 `config/pool.yaml` 里的模型。

### 目录结构
见上方英文版 **Directory** 一节。

### 安全
- 从不打印 key：direct 模式按需取一次，agent 模式连 key 都不碰
- 工人子进程 cwd = `--cwd`，权限遵循 DSH 沙箱
- 密钥永不出现在日志与输出中

### 完整文档
英文版见上方各章节；配置模板、目录树、安全说明均已包含。