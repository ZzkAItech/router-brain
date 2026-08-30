"""凭据解析：环境变量优先，回退到 ~/.dsh/.credentials.yaml。

安全约定：
- 绝不把 key 值写进日志/输出/异常消息；
- 只按需读取指定的键名；
- 外部调用方拿到 key 后自行负责不落盘。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

from .config import DSH_CREDENTIALS
from .models import CredentialsError


def _parse_credentials_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - 防御性
        # 不传播原始异常，避免泄露敏感信息
        raise CredentialsError(f"凭据文件解析失败: {path.name}")
    if not isinstance(doc, dict):
        raise CredentialsError(f"凭据文件格式错误: {path.name}")
    return {str(k): str(v) for k, v in doc.items() if v}


def resolve_key(key_name: str, file_path: Optional[Path] = None) -> str:
    """按 key_name 解析凭据：env 优先，其次凭据文件。找不到抛异常。"""
    env_val = os.environ.get(key_name)
    if env_val:
        return env_val
    creds = _parse_credentials_file(file_path or DSH_CREDENTIALS)
    val = creds.get(key_name)
    if not val:
        raise CredentialsError(
            f"缺少凭据 {key_name}（未设置环境变量，{DSH_CREDENTIALS.name} 中也不存在）"
        )
    return val


def redact(value: str) -> str:
    """日志脱敏：只保留首尾各 3 字符。"""
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:3]}…{value[-3:]}"
