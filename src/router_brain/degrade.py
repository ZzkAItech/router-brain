"""降级编排：动态故障切换。

不再有硬分工候选链。分工由大脑指定（--force-model）；派活失败时按「当前实时模型池」
自动换模型/换通道：429/超时/5xx/空结果 → 重试/换通道；模型停服/不存在 → 立即熔断换模型。
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import logger
from .classifier import Classifier
from .config import Config
from .executor import AgentExecutor, DirectExecutor
from .llm_api import DirectError
from .models import ProviderRef, RunResult, RoutingDecision
from .router import Router


@dataclass
class BreakerState:
    failures: int = 0
    open_until: float = 0.0


def _bk_key(model_id: str, channel: str) -> str:
    return f"{model_id}@{channel}"


class CircuitBreaker:
    """按 (模型,通道) 记连续失败；达到阈值后冷却期跳过。鉴权/停服类立即熔断。"""

    def __init__(self, failures: int = 3, cooldown: float = 60.0) -> None:
        self._failures = failures
        self._cooldown = cooldown
        self._state: dict[str, BreakerState] = {}

    def is_open(self, model_id: str, channel: str) -> bool:
        st = self._state.get(_bk_key(model_id, channel))
        if not st or st.open_until == 0.0:
            return False
        if time.monotonic() >= st.open_until:
            st.failures = 0
            st.open_until = 0.0
            return False
        return True

    def record_failure(self, model_id: str, channel: str, kind: str) -> None:
        st = self._state.setdefault(_bk_key(model_id, channel), BreakerState())
        if kind in ("auth", "permanent"):  # 鉴权/停服：立即熔断，不再消耗配额
            st.failures = self._failures
        else:
            st.failures += 1
        if st.failures >= self._failures:
            st.open_until = time.monotonic() + self._cooldown
            logger.warn(None, "circuit breaker opened", model=model_id, channel=channel, kind=kind, cooldown=self._cooldown)

    def record_success(self, model_id: str, channel: str) -> None:
        st = self._state.get(_bk_key(model_id, channel))
        if st:
            st.failures = 0


class Runner:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._classifier = Classifier(cfg)
        self._router = Router(cfg)
        self._agent = AgentExecutor(cfg)
        self._direct = DirectExecutor(cfg)
        ex = cfg.execution
        self._breaker = CircuitBreaker(
            failures=int(ex.get("circuit_breaker_failures", 3)),
            cooldown=float(ex.get("circuit_breaker_cooldown", 60)),
        )
        self._permanent_patterns = [
            re.compile(p, re.IGNORECASE) for p in ex.get("permanent_model_errors", [])
        ]

    # ---- 第一轮：路由 ------------------------------------------------
    def decide(self, task: str, hints: str = "") -> tuple[str, RoutingDecision]:
        task_type = self._classifier.classify(task, hints)
        decision = self._router.route(task_type)
        return task_type, decision

    # ---- 故障分类 -----------------------------------------------------
    def _is_permanent_model_error(self, text: str) -> bool:
        return any(p.search(text or "") for p in self._permanent_patterns)

    # ---- 第二轮：执行 + 动态故障切换 ---------------------------------
    def run(
        self,
        task: str,
        *,
        cwd: Optional[Path] = None,
        images: Optional[list[str]] = None,
        force_model: Optional[str] = None,
        hints: str = "",
        timeout_s: Optional[float] = None,
        tools_mode: Optional[str] = None,
        max_fallbacks: Optional[int] = None,
        auto_failover: Optional[bool] = None,
    ) -> RunResult:
        task_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        cwd = (cwd or Path.cwd()).resolve()
        run_root = Path(self._cfg.execution.get("run_dir", ".run")).resolve()
        (run_root / task_id).mkdir(parents=True, exist_ok=True)

        task_type, decision = self.decide(task, hints)
        # 派活顺序：大脑指定的模型优先。
        # 默认：一个模型失败就停（由大脑决定换哪个模型），不再引擎自动换模型。
        # auto_failover=True 时才由引擎自动沿可用池换模型（非大脑直用场景）。
        if auto_failover is None:
            auto_failover = bool(self._cfg.execution.get("auto_failover", False))
        if force_model:
            if force_model not in self._cfg.models():
                raise ValueError(f"强制模型未注册: {force_model}")
            order_ids = [force_model]
            if auto_failover:
                order_ids += [m.id for m in self._cfg.available_models() if m.id != force_model]
        else:
            default = self._cfg.cheapest_available()
            order_ids = [default.id] if default else []
            if auto_failover:
                order_ids += [m.id for m in self._cfg.available_models() if m.id != default.id]

        max_fallbacks = max_fallbacks if max_fallbacks is not None else int(self._cfg.execution.get("max_fallbacks", 4))
        max_retries = int(self._cfg.execution.get("max_retries", 2))
        attempts: list[str] = []
        result = RunResult(
            task_id=task_id,
            ok=False,
            model="",
            task_type=task_type,
            execution=decision.execution,
            dsh_provider=decision.dsh_provider,
            channel=decision.channel,
        )

        logger.info(task_id, "route", **decision.as_dict(), order=order_ids)
        # 第一轮输出：路由 JSON
        print(json.dumps(decision.as_dict(), ensure_ascii=False))
        print()  # 与最终答复分隔

        fallbacks_used = 0
        for model_id in order_ids:
            if fallbacks_used > max_fallbacks:
                logger.warn(task_id, "fallback limit reached", model=model_id)
                break
            model = self._cfg.model(model_id)
            run_dir = run_root / task_id

            # 执行模式：若模型没有任何 agent 能力通道（dsh_provider 非空），则对该模型强制 direct
            model_can_agent = any(p.dsh_provider for p in self._cfg.usable_channels(model))
            mode = decision.execution if model_can_agent or decision.execution == "direct" else "direct"
            if decision.execution == "agent" and not model_can_agent:
                logger.info(task_id, "model has no agent channel, use direct", model=model_id)

            # 该模型的可用通道依次尝试（跳过配额过少/国外/熔断的通道；agent 模式只走有 dsh_provider 的）
            channels = [
                p for p in self._cfg.usable_channels(model)
                if not self._breaker.is_open(model_id, p.channel)
                and (mode != "agent" or p.dsh_provider)
            ]
            if not channels:
                logger.warn(task_id, "all channels of model are down, skip", model=model_id)
                continue

            for prov in channels:
                if fallbacks_used > max_fallbacks:
                    break
                ok = False
                error = ""
                output = ""
                transcript = ""
                duration = 0.0
                for attempt in range(max_retries + 1):
                    attempts.append(f"{model_id}@{prov.channel}#{attempt + 1}")
                    logger.info(task_id, "try", model=model_id, channel=prov.channel, attempt=attempt + 1, mode=mode)
                    try:
                        if mode == "direct":
                            reply = self._direct.execute(model, task, images=images, provider=prov)
                            output, duration, ok = reply.content, 0.0, True
                        else:
                            outcome = self._agent.execute(
                                model,
                                task,
                                provider=prov,
                                cwd=cwd,
                                run_dir=run_dir,
                                timeout_s=timeout_s,
                                tools_mode=tools_mode,
                                images=images,
                            )
                            output, duration, ok = outcome.output, outcome.duration_s, outcome.ok
                            error = outcome.error
                            transcript = outcome.transcript
                            if not ok:
                                # 停服/不存在：永久失败，立即换模型
                                if self._is_permanent_model_error(error):
                                    logger.error(task_id, "model discontinued/unknown", model=model_id, channel=prov.channel, err=error[:160])
                                    self._breaker.record_failure(model_id, prov.channel, "permanent")
                                    ok = False
                                    break
                                # 硬失败（退出码≠0）不重试同通道；超时才重试
                                if error.startswith("超时"):
                                    logger.warn(task_id, "agent timeout, retry same channel", model=model_id, channel=prov.channel)
                                    continue
                                break
                    except DirectError as exc:
                        error = str(exc)
                        if exc.kind == "auth":
                            ok = False
                            self._breaker.record_failure(model_id, prov.channel, "auth")
                            logger.error(task_id, "auth failure", model=model_id, channel=prov.channel)
                            break
                        if self._is_permanent_model_error(exc.detail + " " + str(exc)):
                            self._breaker.record_failure(model_id, prov.channel, "permanent")
                            logger.error(task_id, "model discontinued/unknown", model=model_id, channel=prov.channel, detail=exc.detail[:160])
                            ok = False
                            break
                        logger.warn(task_id, "direct error", model=model_id, channel=prov.channel, kind=exc.kind, detail=exc.detail[:160])
                        continue  # 可重试：下一 attempt
                    except (RuntimeError, OSError) as exc:
                        error = str(exc)
                        logger.warn(task_id, "unexpected error", model=model_id, channel=prov.channel, err=type(exc).__name__)
                        continue
                    if ok:
                        break

                if ok:
                    self._breaker.record_success(model_id, prov.channel)
                    result.ok = True
                    result.model = model_id
                    result.execution = mode   # 实际执行模式（可能被 direct-only 模型覆盖）
                    result.output = output.strip()
                    if transcript:
                        result.output += "\n\n" + transcript
                    result.duration_s = duration
                    result.dsh_provider = prov.dsh_provider
                    result.channel = prov.channel
                    logger.info(task_id, "succeeded", model=model_id, channel=prov.channel, attempts=len(attempts))
                    break
                else:
                    self._breaker.record_failure(model_id, prov.channel, "agent" if decision.execution == "agent" else "direct")
                    result.error = error or "执行失败"
                    result.model = model_id   # 记录最后尝试失败的模型，供大脑决策
                    fallbacks_used += 1
                    logger.warn(task_id, "failover", failed_model=model_id, channel=prov.channel, next_index=len(attempts))
            if result.ok:
                break

        result.duration_s = time.monotonic() - started
        result.attempts = attempts
        logger.result(task_id, result.to_json())
        if not result.ok:
            result.error = result.error or "执行失败"
            # 给大脑的换模型决策信息：失败模型 + 可选替换模型清单
            avail = [
                m.id for m in self._cfg.available_models()
                if not self._breaker.is_open(m.id, m.primary.channel)
            ]
            hint = (
                f"\n\n[换模型决策] 模型 {result.model or '?'} 执行失败（原因见上）。"
                f"请大脑从下列可用模型中选择替换模型，用 --force-model 重新派活：\n  "
                + "、".join(avail[:15])
            )
            if result.output:
                result.output += hint
            else:
                result.error += hint
        return result
