"""从 ~/.dsh/settings.yaml 提取 llm-pi-ai.providers 目录，供 per-run settings 生成。

headless 执行时把 settings 文档重定向到 per-run 文件，其中的 provider 目录必须
与用户真实 settings 保持一致（本模块只做透传复制，不改造）。
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .config import DSH_SETTINGS
from .models import RouterError

# 所有已知模型安全的 max_tokens 上限
MAX_SAFE_TOKENS = 131072


def load_providers(settings_path: Path = DSH_SETTINGS) -> dict[str, Any]:
    """返回 settings.yaml 中 llm-pi-ai.providers 的原始 dict（无则空 dict）。"""
    if not settings_path.exists():
        raise RouterError(
            f"找不到 DSH settings 文件: {settings_path}。"
            "请确认 DSH 已配置 llm-pi-ai.providers（Web 的 Models 页会写它）。"
        )
    with open(settings_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    pi = doc.get("llm-pi-ai") or {}
    providers = pi.get("providers") or {}
    if not isinstance(providers, dict):
        raise RouterError(f"settings.yaml 里 llm-pi-ai.providers 不是 map: {settings_path}")
    return providers


def provider_exists(providers: dict[str, Any], dsh_provider: str) -> bool:
    return dsh_provider in providers


def render_run_settings(
    providers: dict[str, Any],
    dsh_provider: str,
    model_id: str,
    dest: Path,
    *,
    model_name: str = "",
    context_window: int = 1000000,
) -> Path:
    """生成 per-run settings.yaml：复制 provider 目录 + 覆盖 agent-default-model。

    若目标模型不在 provider 的 models 列表里（例如上游刚迁移的新 id），自动补一条，
    保证 pi-ai provider 校验通过，无需改动用户全局 DSH settings。
    """
    # 深拷贝 providers 避免修改原始对象（副作用）
    providers = deepcopy(providers)
    if not provider_exists(providers, dsh_provider):
        raise RouterError(
            f"DSH settings 未注册 provider '{dsh_provider}'，无法用 agent 模式执行。"
            f"已注册: {sorted(providers)}"
        )
    prov = providers[dsh_provider]
    if not isinstance(prov, dict):
        raise RouterError(f"provider '{dsh_provider}' 配置不是 map")
    # 多通道方案：pool id 即 DSH provider 的真实模型 id
    dsh_model_id = model_id

    models = prov.get("models")
    if not isinstance(models, list):
        models = []
        prov["models"] = models
    if not any(isinstance(m, dict) and m.get("id") == dsh_model_id for m in models):
        # maxTokens 不能用 context_window：上游对多数新模型有硬上限（qwen/longcat=131072，
        # 取 min(context, MAX_SAFE_TOKENS) 对所有已知模型安全（超大 context 会 400）。
        max_tokens = min(int(context_window or 1000000), MAX_SAFE_TOKENS)
        models.append(
            {
                "id": dsh_model_id,
                "name": model_name or dsh_model_id,
                "contextWindow": context_window,
                "maxTokens": max_tokens,
            }
        )
    doc: dict[str, Any] = {"llm-pi-ai": {"providers": providers}}
    doc["agent-default-model"] = {"provider": dsh_provider, "model": dsh_model_id}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
    return dest


def render_patch(settings_path: Path, dest: Path, extras_path: Path | None = None) -> Path:
    """生成 --patch 覆盖文件：把 settings 行重定向到 per-run 文件，并追加标准工具行。"""
    patch = [
        {"id": "settings", "config": {"path": str(settings_path)}},
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        yaml.safe_dump(patch, f, allow_unicode=True, sort_keys=False)
        if extras_path and extras_path.exists():
            f.write("\n")
            f.write(extras_path.read_text(encoding="utf-8"))
    return dest
