"""配置加载：模型池 + 路由参数，支持实时重载。

pool.yaml 是唯一数据源：改文件后调用 reload()（或下一次 CLI 调用天然重读）
即刻生效，无需重启、无需改代码。模型支持多通道，一个模型挂了自动换通道/换模型。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import ModelSpec, ProviderInfo, ProviderRef, RouterError

DEFAULT_POOL = Path(__file__).resolve().parent.parent.parent / "config" / "pool.yaml"
DEFAULT_ROUTING = Path(__file__).resolve().parent.parent.parent / "config" / "routing.yaml"
DSH_HOME = Path(os.environ.get("DSH_HOME", "~/.dsh")).expanduser()
DSH_SETTINGS = DSH_HOME / "settings.yaml"
DSH_CREDENTIALS = DSH_HOME / ".credentials.yaml"

COST_ORDER = {"free": 0, "low": 1, "medium": 2, "high": 3}

# 通道配额阈值（5h 请求数低于此值视为「配额过少」→ 该通道禁用）
LOW_QUOTA_5H_THRESHOLD = 500

# 国内模型前缀示例（用户可根据自己的模型池修改）
CN_PREFIXES: tuple[str, ...] = ()


def classify_region(model_id: str) -> str:
    low = model_id.lower()
    if any(low.startswith(p) for p in CN_PREFIXES):
        return "cn"
    return "foreign"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RouterError(f"配置文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        raise RouterError(f"配置文件不是 map: {path}")
    return doc


class Config:
    def __init__(
        self,
        pool_path: Path = DEFAULT_POOL,
        routing_path: Path = DEFAULT_ROUTING,
    ) -> None:
        self.pool_path = pool_path
        self.routing_path = routing_path
        self._providers: dict[str, ProviderInfo] = {}
        self._models: dict[str, ModelSpec] = {}
        self.reload()

    # ---- 加载与校验 -------------------------------------------------
    def reload(self) -> None:
        """重新读取 pool.yaml / routing.yaml（实时生效）。"""
        pool_doc = _load(self.pool_path)
        routing_doc = _load(self.routing_path)
        self.routing_doc = routing_doc
        self._providers = {}
        prov_doc = pool_doc.get("providers") or {}
        for channel, info in prov_doc.items():
            self._providers[channel] = ProviderInfo(
                channel=channel,
                base_url=info["base_url"],
                credential_key=info.get("credential_key", ""),
                tunnel_host=info.get("tunnel_host", ""),
                tunnel_port=int(info.get("tunnel_port", 0) or 0),
                worker=bool(info.get("worker", True)),
            )
        models_doc = pool_doc.get("models") or {}
        self._models = {}
        for mid, spec in models_doc.items():
            raw_provs = spec.get("providers") or []
            provs = []
            for p in raw_provs:
                ch = p.get("channel")
                if ch not in self._providers:
                    raise RouterError(f"模型 {mid} 引用未注册通道: {ch}")
                provs.append(ProviderRef(channel=ch, dsh_provider=p.get("dsh_provider", "")))
            if not provs:
                raise RouterError(f"模型 {mid} 没有可用通道")
            self._models[mid] = ModelSpec(
                id=mid,
                providers=tuple(provs),
                kind=spec.get("kind", "general"),
                cost=spec.get("cost", "low"),
                context=spec.get("context", 1000000),
                roles=tuple(spec.get("roles") or ()),
                banned=bool(spec.get("banned", False)),
                unreliable=bool(spec.get("unreliable", False)),
                region=spec.get("region") or classify_region(mid),
                quota=dict(spec.get("quota") or {}),
                note=spec.get("note", ""),
            )
        # （原 keyword 校验空循环已移除——无实际作用）

    # ---- 访问器 -----------------------------------------------------
    @property
    def rules(self) -> dict[str, list[str]]:
        # 兼容旧字段；新架构不依赖硬分工规则
        return self.routing_doc.get("rules") or {}

    @property
    def keywords(self) -> dict[str, list[str]]:
        return self.routing_doc.get("classifier") or {}

    @property
    def direct_execution(self) -> set[str]:
        return set(self.routing_doc.get("direct_execution") or [])

    @property
    def execution(self) -> dict[str, Any]:
        return self.routing_doc.get("execution") or {}

    def provider(self, channel: str) -> ProviderInfo:
        if channel not in self._providers:
            raise RouterError(f"未注册逻辑通道: {channel}")
        return self._providers[channel]

    def model(self, mid: str) -> ModelSpec:
        if mid not in self._models:
            raise RouterError(f"未注册模型: {mid}")
        return self._models[mid]

    def models(self) -> dict[str, ModelSpec]:
        return dict(self._models)

    def available_models(self) -> list[ModelSpec]:
        """全部可用模型（非 banned，openrouter 仅免费；force_channel 时只返回该通道模型），按成本升序。"""
        force = str(self.execution.get("force_channel", "") or "")
        out = [m for m in self._models.values() if not self.excluded_reason(m)]
        if force:
            out = [m for m in out if force in m.channels]
        return sorted(out, key=lambda m: (COST_ORDER.get(m.cost, 9), m.id))

    def channel_blocked(self, m: ModelSpec, channel: str) -> str | None:
        """某通道被封锁的原因（配额过少等）；None 表示可用。"""
        if m.quota.get("h5"):
            if int(m.quota["h5"]) < LOW_QUOTA_5H_THRESHOLD:
                return f"{channel} 配额过少(5h={m.quota['h5']})"
        return None

    def usable_channels(self, m: ModelSpec) -> list[ProviderRef]:
        """该模型未被封锁的通道（跳过 banned/openrouter非免费/低配额/不作工人的通道；force_channel 时只返回该通道）。"""
        force = str(self.execution.get("force_channel", "") or "")
        out = []
        for p in m.providers:
            if m.banned:
                continue
            if force and p.channel != force:
                continue
            # 通道标记 worker:false（只作大脑驱动、不作工人）→ 跳过
            prov = self._providers.get(p.channel)
            if prov is not None and not prov.worker:
                continue
            if p.channel == "openrouter" and m.cost != "free":
                continue
            if self.channel_blocked(m, p.channel):
                continue
            out.append(p)
        return out

    def excluded_reason(self, m: ModelSpec) -> str | None:
        """模型被排除的原因：banned / openrouter 非免费 / 全通道配额过少；None 表示可用。"""
        if m.banned:
            return "banned"
        if not self.usable_channels(m):
            if any(p.channel == "openrouter" for p in m.providers) and m.cost != "free":
                return "openrouter 仅限免费模型"
            blocked = [self.channel_blocked(m, p.channel) for p in m.providers]
            low_quota = [b for b in blocked if b and "配额过少" in b]
            if low_quota:
                return low_quota[0]
            return "无可用通道"
        return None

    def cheapest_available(self, exclude: set[str] | None = None, kind: str | None = None) -> ModelSpec | None:
        """当前最便宜的可用模型（排除集+易限流默认不优先；kind 限定类型如 vision），用于大脑未指定时的智能默认。"""
        exclude = exclude or set()
        pool = [m for m in self.available_models() if (kind is None or m.kind == kind)]
        # 优先非 unreliable；都没有才回退到 unreliable
        for allow_unreliable in (False, True):
            for m in pool:
                if m.id in exclude:
                    continue
                if m.unreliable and not allow_unreliable:
                    continue
                return m
        return None
