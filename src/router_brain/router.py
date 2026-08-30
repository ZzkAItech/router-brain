"""路由决策：只定执行模式 + 给出一个「智能默认」建议模型。

不再有硬分工规则表。分工由大脑决定（--force-model）；这里只在大脑没指定时
给出当前最便宜的可用模型作为兜底默认。真实派活失败会自动换模型/换通道。
"""
from __future__ import annotations

from .config import Config
from .models import ModelSpec, RoutingDecision, RouterError


class Router:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def route(self, task_type: str) -> RoutingDecision:
        execution = "direct" if task_type in self._cfg.direct_execution else "agent"
        # vision 任务优先选 vision 类型模型；其它任务选最便宜的
        kind = "vision" if task_type == "vision" else None
        default = self._cfg.cheapest_available(kind=kind)
        if default is None:
            # vision 无专用模型时回退到普通
            default = self._cfg.cheapest_available()
        if default is None:
            raise RouterError(
                "模型池里没有可用模型（全部禁用或池为空）——请先在 config/pool.yaml 配置你的模型和通道，"
                "详见 README「配置你的模型池」。"
            )
        # 实际可用通道（尊重 force_channel）；空则用 primary
        usable = self._cfg.usable_channels(default)
        if not usable:
            raise RouterError(f"模型 {default.id} 没有可用通道")
        prim = usable[0]
        reason = (
            "直答（快问快答，不派活），默认最便宜模型"
            if execution == "direct"
            else f"派给 DSH headless agent 执行；默认最便宜可用模型 {default.id}（大脑可用 --force-model 覆盖）"
        )
        return RoutingDecision(
            task_type=task_type,
            selected_model=default.id,
            dsh_provider=prim.dsh_provider,
            channel=prim.channel,
            provider=prim.channel,
            candidates=[default.id],
            execution=execution,
            reason=reason,
        )
