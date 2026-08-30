"""实时派活事件流：把大脑的每次派活/工人步骤写入 ~/.dsh/router-brain-live.jsonl。

dashboard 面板轮询这个文件渲染实时视图。事件都是追加写，低并发安全。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

LIVE_FILE = Path(os.environ.get("DSH_HOME", "~/.dsh")).expanduser() / "router-brain-live.jsonl"

MAX_LIVE_BYTES = 2 * 1024 * 1024  # 超过后轮转清空（避免无限膨胀）


def _safe(value: Any) -> Any:
    """非 JSON 可序列化值（如 Mock）转字符串，避免面板事件崩溃。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def emit(kind: str, **fields: Any) -> None:
    """写一条实时事件。kind: dispatch / worker_step / succeed / fail / route。"""
    rec: dict[str, Any] = {"ts": time.strftime("%H:%M:%S"), "kind": kind}
    rec.update({k: _safe(v) for k, v in fields.items()})
    try:
        LIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LIVE_FILE.exists() and LIVE_FILE.stat().st_size > MAX_LIVE_BYTES:
            # 轮转：保留尾部一半
            data = LIVE_FILE.read_text(encoding="utf-8", errors="replace")
            tail = data[-MAX_LIVE_BYTES // 2:]
            LIVE_FILE.write_text(tail, encoding="utf-8")
        with open(LIVE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_recent(limit: int = 200) -> list[dict[str, Any]]:
    """读取最近的实时事件（供面板轮询）。"""
    if not LIVE_FILE.exists():
        return []
    try:
        lines = LIVE_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
