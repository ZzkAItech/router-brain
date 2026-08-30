# router-brain · LLM Routing Brain

> **English**: this file · **中文**: [README_CN.md](README_CN.md)

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

## The problems it solves

### 🎯 Problem 1: LLMs lose focus in long contexts

**Problem**: Hand a whole complex task to a single model and it has to hold the goal, the background, the progress, and the current step all in one context. The longer the context, the more it drifts—a phenomenon often called "lost in the middle."

**What router-brain does**: **Separate decision-making from execution.**
- The **brain only decides**—it sees "goal + current state + whom to dispatch." It never wades into execution details, so its attention stays on judgment.
- Each **worker handles one short-context subtask**—it focuses on the single thing in front of it, no more.

> The brain doesn't do the work, so the brain doesn't burn out; the worker does one thing, so it doesn't get lost.

### 🌀 Problem 2: Hallucination

**Problem**: A single model generates an answer with nobody checking it. In multi-step work, one hallucinated step corrupts everything downstream, and it's hard to even notice.

**What router-brain does**: **A dispatch → feedback → re-dispatch loop.**
- The brain dispatches → the worker finishes → **the result comes back to the brain**;
- The brain checks whether it meets the bar; if not, it **re-dispatches or switches models** until the result is good enough—or it confirms the task is truly unsolvable;
- Important conclusions are **cross-validated by different models**—one model might fool you, but several rarely agree on a lie.

### 💰 Problem 3: Costs that spiral out of control

**Problem**: Use an expensive model for everything and you burn through money fast; use cheap models for everything and hard tasks come out wrong.

**What router-brain does**: **Right-size every call, cheap first.**
- The **brain runs on a cheap or free model**—it only judges, it doesn't need the strongest model;
- **Simple tasks (QA / classify / extract) go direct**—instant reply, no agent startup;
- **Complex tasks dispatch a worker**, trying cheap models before expensive ones;
- **Free quotas get used automatically** whenever available.

### 🔗 Deeper problems it also solves

- **No vendor lock-in**: models live in a pluggable pool—switch providers by editing config, not code.
- **One API going down doesn't stop your task**: multi-channel failover + circuit breaker + retry.
- **Long tasks survive mid-way failures**: subtasks are independent, so only the failed step gets redone.
- **Quotas stay under control**: cheap-first selection + healthcheck + auto-degrading low-quota channels.
- **Context stays small**: decision/execution separation keeps every worker's context short.
- **Model lifecycles handled**: deprecated models auto-fuse; `sync-free-models` pulls in the latest ones.
- **Many models, one team**: pick the best model for each job, and cross-validate key results.

### ✍️ Can't write prompts? The brain writes them for you

You just state the **goal** ("refactor this project", "turn this data into a report"). The brain:
- breaks it into subtasks and **writes each subtask's prompt** (with guardrails, output path, and format);
- **picks the model**—you never need to know which model is good at what;
- **sets the reasoning effort**—light for simple steps, heavy for deep reasoning.

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

The only dependency is PyYAML. You'll also need **DeepSeek Harness** installed (`dsh` on your PATH).

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
├── README_CN.md              Chinese README
├── LICENSE                   MIT
└── README.md                 this file (English)
```

## Security

- Never reads-and-prints any key; direct mode resolves a key once, agent mode never touches keys.
- Worker subprocess cwd = `--cwd`; file permissions follow the DSH sandbox policy.
- healthcheck consumes real API quota (~a dozen tiny calls per full run).
- Keys never appear in logs or output.
