"""OpenRouter 免费模型自动同步。

用 OPENROUTER_API_KEY 拉取 OpenRouter 最新模型列表，筛出免费模型
（id 带 :free 后缀，或 prompt/completion 定价均为 0），写入 pool.yaml 的
models 段，下次派活实时可用。跳过已存在的模型 id，保留 pool.yaml 注释。
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from .credentials import resolve_key
from .models import RouterError

MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_KEY = "OPENROUTER_API_KEY"


def fetch_free_models(api_key: str) -> list[dict[str, Any]]:
    """拉取 OpenRouter 免费模型（:free 后缀或定价全 0）。"""
    req = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        raise RouterError(f"拉取 OpenRouter 模型失败: {exc}") from exc

    all_models = data.get("data") or []
    free = []
    for m in all_models:
        mid = m.get("id", "")
        pricing = m.get("pricing") or {}
        prompt_zero = pricing.get("prompt") in ("0", "0.0", 0)
        comp_zero = pricing.get("completion") in ("0", "0.0", 0)
        if mid.endswith(":free") or (prompt_zero and comp_zero):
            free.append(m)
    return free


def _entry_block(mid: str, m: dict[str, Any]) -> str:
    from .config import classify_region
    ctx = m.get("context_length") or 1000000
    name = (m.get("name") or mid)[:80].replace('"', '\\"')
    region = classify_region(mid)
    note = f"OpenRouter 免费模型(自动同步)：{name}"
    lines = [
        f"  {mid}:",
        f"    kind: general",
        f"    cost: free",
        f"    context: {ctx}",
        f"    region: {region}",
        f"    providers:",
        f"      - {{channel: openrouter, dsh_provider: openrouter}}",
        f'    note: "{note}"',
        "",
    ]
    return "\n".join(lines)


def sync_free_models(pool_path: Path, api_key: str | None = None) -> tuple[int, int]:
    """把 OpenRouter 免费模型写入 pool.yaml。返回 (新增数, 已有跳过数)。"""
    api_key = api_key or resolve_key(OPENROUTER_KEY)
    free = fetch_free_models(api_key)

    text = pool_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text) or {}
    existing = set((doc.get("models") or {}).keys())

    added = 0
    skipped = 0
    block = ""
    for m in free:
        mid = m.get("id", "")
        if not mid:
            continue
        if mid in existing:
            skipped += 1
            continue
        block += _entry_block(mid, m)
        existing.add(mid)
        added += 1

    if added == 0:
        return 0, skipped

    # 插入到「禁用」段之前；找不到就追加到文件尾
    marker = "  # ── 禁用"
    header = "\n  # ── OpenRouter 免费模型（router-brain sync-free-models 自动同步）──\n"
    if marker in text:
        text = text.replace(marker, header + block + marker, 1)
    else:
        text = text.rstrip() + "\n" + header + block

    pool_path.write_text(text, encoding="utf-8")
    return added, skipped
