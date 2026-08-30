"""结构化 JSON 日志（写 stderr，绝不落任何密钥）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _emit(level: str, task_id: Optional[str], msg: str, **fields: Any) -> None:
    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),  # 统一使用 UTC
        "level": level,
        "msg": msg,
    }
    if task_id:
        rec["task_id"] = task_id
    rec.update({k: _safe(v) for k, v in fields.items() if v is not None})
    sys.stderr.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def info(task_id: Optional[str], msg: str, **fields: Any) -> None:
    _emit("info", task_id, msg, **fields)


def warn(task_id: Optional[str], msg: str, **fields: Any) -> None:
    _emit("warn", task_id, msg, **fields)


def error(task_id: Optional[str], msg: str, **fields: Any) -> None:
    _emit("error", task_id, msg, **fields)


def result(task_id: str, result: Any) -> None:
    """任务终结事件（含完整结果，输出到 stdout 的最终答复除外）。"""
    payload = dict(result)
    payload.pop("task_id", None)  # task_id 已作为位置参数，避免撞车
    _emit("result", task_id, "task finished", **payload)
