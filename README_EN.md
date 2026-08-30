# router-brain · LLM Routing Brain

> **Separate decision from execution**: a small "brain" model makes decisions (decompose → pick model → dispatch → read feedback); focused workers do one short-context subtask each. Use the right model for the right job, verify across models, fight hallucinations, and save money.

> **AI orchestration framework · multi-model router · prompt automation · DeepSeek Harness** — You don't need to know how to write prompts: tell it *what* you want, and the brain decomposes the task, writes the subtask prompts, picks the model, sets the reasoning effort, dispatches workers, reads feedback, and iterates until done.

<p align="center">
<a href="https://github.com/ZzkAItech/router-brain"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ZzkAItech/router-brain?style=flat-square&label=Stars"></a>
<a href="https://github.com/ZzkAItech/router-brain"><img alt="GitHub forks" src="https://img.shields.io/github/forks/ZzkAItech/router-brain?style=flat-square&label=Forks"></a>
<a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square"></a>
<a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square"></a>
<a href="https://github.com/ZzkAItech/router-brain/actions"><img alt="tests" src="https://github.com/ZzkAItech/router-brain/actions/workflows/test.yml/badge.svg"></a>
</p>

---

## Problems it solves

### 🎯 Problem 1: LLMs lose focus in long contexts

**Problem**: Shove a whole long task into one model and it must hold the goal, background, progress, and current step all at once. The longer the context, the more it drifts ("lost in the middle").

**router-brain's approach**: **Separate decision from execution.**
- The **brain model only decides** — it sees "goal + current state + who to dispatch". It never touches execution details, so its attention stays on judgment.
- Each **worker handles one short-context subtask** — it only focuses on the one thing in front of it.

> The brain doesn't do the work, so the brain doesn't tire; the worker does one thing, so it doesn't get lost.

### 🌀 Problem 2: Hallucination

**Problem**: A single model generates once, with no one checking. In multi-step tasks one hallucinated step corrupts everything downstream.

**router-brain's approach**: **Dispatch → feedback → re-dispatch loop.**
- Brain dispatches → worker finishes → **result returns to the brain**;
- Brain checks whether it meets the bar; if not, **re-dispatch / switch model** until done or truly unsolvable;
- Key conclusions are **cross-validated by different models** — one model may fool you, several rarely fool you together.

### 💰 Problem 3: Uncontrollable cost

**Problem**: Using an expensive model for everything burns money; using cheap ones for everything can't handle hard tasks.

**router-brain's approach**: **Right-size the spend, cheap-first.**
- The **brain uses a cheap/free model** (it only judges, doesn't need the strongest);
- **Simple tasks (QA/classify/extract) go direct** — instant reply, no agent boot;
- **Complex tasks dispatch a worker**, trying cheap → expensive in order;
- Hooks into **free quotas** automatically.

### 🔗 And deeper problems it solves

- **No vendor lock-in**: models are a pluggable pool — switch providers by editing config, not code.
- **One API down doesn't stop the task**: multi-channel failover + circuit breaker + retry.
- **Long tasks survive mid-way failures**: subtasks are independent; retry only the failed step.
- **Quotas stay managed**: cheap-first + healthcheck + auto-degrade low-quota channels.
- **Context stays small**: decision/execution separation keeps each worker's context short.
- **Model lifecycle handled**: deprecated models auto-fuse; `sync-free-models` pulls the latest.
- **Multi-model as a team**: pick the best for each job, cross-validate key results.

### ✍️ Can't write prompts? The brain writes them

You only state the **goal** ("refactor this project", "turn this data into a report"). The brain:
- decomposes into subtasks and **writes each subtask's prompt** (with guardrails, output path, format);
- **picks the model** — you don't need to know which model is good at what;
- **sets reasoning effort** — light for simple steps, heavy for deep reasoning.

---

## Architecture in one line

```
You (goal)
  └─> 🧠 Brain (cheap model, decides only) ──decompose──> 👷 Worker 1 (model A, one task)
                                                 ├──> 👷 Worker 2 (model B, another task)
                                                 └──> 🔁 feedback back; re-dispatch / switch if not OK
```

- **Decision plane** (this process): classify → pick model → dispatch → read feedback → decide next.
- **Execution plane** (DeepSeek Harness headless agent): a real agent with tools (bash/files/workspace) actually does the work.

> Every worker is a **real agent** — not "ask a question, get text back", but "write files, run scripts, read results".

---

## Quick start

### 1. Install

```bash
cd router-brain
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

Only dependency is PyYAML. Requires **DeepSeek Harness** installed (`dsh` on PATH).

### 2. Configure your model pool

router-brain ships **no models/channels** — it's a scheduling framework; you add yours.

`config/pool.yaml` is a template. Fill in:
- **providers**: API channels (base_url + credential key name)
- **models**: the models you can use (id + channel + cost + kind)

Credentials go in `~/.dsh/.credentials.yaml` or same-named env vars; the framework reads them and **never prints keys**. Changes take effect immediately — no restart.

### 3. Run

```bash
router-brain list-models                            # see your pool
router-brain route "write a python script"          # routing decision only (no execution)
router-brain run "turn /tmp data into a report"     # route → dispatch → fallback → summary
```

### 4. (Optional) Enable the "Router Brain" commander in DeepSeek Harness

The repo ships `agent-presets/router-brain/` (commander persona + dispatch skill). Enable it and a new **「路由大脑 / Router Brain」** preset appears in the DSH session picker — it becomes a persistent commander: give it a goal, it decomposes, dispatches, reads feedback, iterates to completion, and gives a final summary.

```bash
mkdir -p ~/.dsh/.agent-presets
cp -r agent-presets/router-brain ~/.dsh/.agent-presets/
# restart dsh web, pick 「路由大脑」 in the new-session picker
```

> The preset ships only the commander tools (bash/fs/jobs/goal/todo/skill) and no models — brain and workers both use models from *your* `config/pool.yaml`.

---

## Highlights

| Capability | Description |
|---|---|
| Decision/execution separation | Brain judges, worker executes → fights attention drift |
| Dispatch-feedback-re-dispatch | Results return; re-dispatch/switch on failure → fights hallucination |
| Cross-model validation | Key results validated by different models, never self-proven |
| No hardcoded division | Brain decides allocation at runtime |
| Multi-channel failover | One model on many channels; auto-switch on limit/shutdown |
| Retry + degrade + fuse | 429/timeout/5xx retry; fallback chain; circuit breaker |
| Permanent-error fuse | Deprecated/not-found models fuse instantly |
| Cheap-first | Defaults to free/low-cost available models |
| Direct fast-answer | QA/classify/extract reply instantly, no agent boot |
| Worker channel switch | `worker:false` marks brain-only channels |
| Millisecond classifier | Deterministic rules, zero cost, zero latency |
| Program-readable decision | `route` emits JSON for the brain or other programs |
| Full-task trace | `task_id` through everything; JSON logs, no secrets |
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

## Security

- Never reads-and-prints any key; direct mode resolves once, agent mode never touches keys.
- Worker subprocess cwd = `--cwd`; file permissions follow DSH sandbox policy.
- healthcheck consumes real API quota (~a dozen tiny calls per full run).
- Keys never appear in logs or output.
