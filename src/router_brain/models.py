"""数据结构定义（纯 dataclass，零依赖）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass(frozen=True)
class ProviderInfo:
    """逻辑通道信息（direct 模式 API 调用用）。"""
    channel: str
    base_url: str
    credential_key: str
    tunnel_host: str = ""   # 若有，direct 客户端连这里但 SNI/Host 用 base_url 的主机
    tunnel_port: int = 0
    worker: bool = True     # False = 该通道只作大脑驱动、不作工人（派活时跳过）


@dataclass(frozen=True)
class ProviderRef:
    """一个模型在某通道上的可用性（agent 模式用 dsh_provider，direct 用 channel）。"""
    channel: str
    dsh_provider: str


@dataclass(frozen=True)
class ModelSpec:
    """模型池里的一个模型条目。一个模型可挂多个通道，限流/停服时自动换通道或换模型。"""
    id: str
    providers: tuple[ProviderRef, ...]
    kind: str = "general"
    cost: str = "low"              # low | medium | high | free
    context: int = 1000000
    roles: tuple[str, ...] = ()
    banned: bool = False
    unreliable: bool = False
    region: str = "cn"             # cn | foreign
    quota: dict = field(default_factory=dict)   # {h5, weekly, monthly, allowance_usd}
    note: str = ""

    @property
    def primary(self) -> ProviderRef:
        return self.providers[0]

    @property
    def channels(self) -> list[str]:
        return [p.channel for p in self.providers]


@dataclass
class RoutingDecision:
    """第一轮路由输出。"""
    task_type: str
    selected_model: str
    dsh_provider: str
    channel: str
    provider: str
    candidates: list[str]
    execution: str                 # "agent" | "direct"
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "selected_model": self.selected_model,
            "provider": self.provider,
            "execution": self.execution,
            "reason": self.reason,
        }


@dataclass
class RunResult:
    """一次任务的完整执行结果。"""
    task_id: str
    ok: bool
    model: str
    task_type: str
    execution: str
    output: str = ""
    error: str = ""
    attempts: list[str] = field(default_factory=list)   # 依次尝试过的 (model/provider)
    duration_s: float = 0.0
    dsh_provider: str = ""
    channel: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "ok": self.ok,
            "model": self.model,
            "task_type": self.task_type,
            "execution": self.execution,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
            "duration_s": round(self.duration_s, 2),
        }


class RouterError(Exception):
    """路由/执行层的业务异常。"""


class CredentialsError(RouterError):
    """凭据缺失或不可解析。"""
