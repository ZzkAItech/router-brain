"""direct 模式：OpenAI 兼容 /chat/completions 调用（stdlib，单次尝试）。

- 推理型模型：max_tokens 必须给足（默认 2048），否则 content 被 reasoning 吃空；
  返回时剔除 reasoning_content，只留 content。
- 错误分类：AuthError / RateLimitError / UpstreamError / TimeoutError / EmptyContentError，
  供 degrade 层选择重试策略。
- 输入含图片（vision）：content 数组 + base64 data URL。
"""
from __future__ import annotations

import base64
import http.client
import json
import mimetypes
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from .credentials import resolve_key
from .models import ProviderInfo, RouterError

DEFAULT_MAX_TOKENS = 2048


class DirectError(RouterError):
    kind = "unknown"

    def __init__(self, message: str, *, retryable: bool = True, detail: str = "") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.detail = detail


class AuthError(DirectError):
    kind = "auth"

    def __init__(self, detail: str = ""):
        super().__init__("鉴权失败(401/403)，请检查凭据", retryable=False, detail=detail)


class RateLimitError(DirectError):
    kind = "rate_limit"

    def __init__(self, detail: str = "", retry_after: float = 1.0):
        super().__init__(f"触发限流(429)，{retry_after:.0f}s 后重试", retryable=True, detail=detail)
        self.retry_after = retry_after


class UpstreamError(DirectError):
    kind = "upstream"

    def __init__(self, detail: str = ""):
        super().__init__("上游服务错误(5xx)", retryable=True, detail=detail)


class TimeoutError_(DirectError):
    kind = "timeout"

    def __init__(self, detail: str = ""):
        super().__init__("请求超时", retryable=True, detail=detail)


class EmptyContentError(DirectError):
    kind = "empty"

    def __init__(self, detail: str = ""):
        super().__init__("模型只返回了思考、没有正文（可能是 max_tokens 不够）", retryable=True, detail=detail)


@dataclass
class DirectReply:
    content: str
    model: str
    finish_reason: str
    usage: dict[str, Any]
    raw: dict[str, Any]


def _image_content(path_or_url: str, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any]:
    if path_or_url.startswith(("http://", "https://")):
        return {"type": "image_url", "image_url": {"url": path_or_url}}
    p = Path(path_or_url).expanduser()
    if not p.exists():
        raise RouterError(f"图片文件不存在: {p}")
    file_size = p.stat().st_size
    if file_size > max_bytes:
        raise RouterError(f"图片过大(>{max_bytes // 1024 // 1024}MB): {p}")
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def build_messages(
    text: str,
    system: str = "",
    images: Optional[list[str]] = None,
    max_image_bytes: int = 8 * 1024 * 1024,
) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    if images:
        for img in images:
            p = Path(img).expanduser() if not img.startswith(("http://", "https://")) else None
            if p is not None and p.exists() and p.stat().st_size > max_image_bytes:
                raise RouterError(f"图片过大(>{max_image_bytes//1024//1024}MB): {img}")
        content: Any = [{"type": "text", "text": text}]
        content += [_image_content(img) for img in images]
        msgs.append({"role": "user", "content": content})
    else:
        msgs.append({"role": "user", "content": text})
    return msgs


class _TunnelHTTPSConnection(http.client.HTTPSConnection):
    """连到隧道地址，但 TLS SNI / Host 仍用目标主机（用于网络受限时的中转）。"""

    def __init__(self, host, port=443, tunnel_host="127.0.0.1", tunnel_port=8443,
                 timeout=120.0, context=None):
        super().__init__(host, port, timeout=timeout, context=context)
        self._tunnel_addr = (tunnel_host, tunnel_port)

    def connect(self):
        self.sock = socket.create_connection(self._tunnel_addr, self.timeout)
        self.sock.settimeout(self.timeout)
        if self._context is None:
            self._context = ssl._create_default_https_context()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _TunnelHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, tunnel_host, tunnel_port, **kwargs):
        super().__init__(**kwargs)
        self._tunnel = (tunnel_host, tunnel_port)

    def https_open(self, req):
        def make_conn(host, **kw):
            return _TunnelHTTPSConnection(
                host,
                tunnel_host=self._tunnel[0],
                tunnel_port=self._tunnel[1],
                timeout=kw.pop("timeout", 120.0),
                **kw,
            )
        return self.do_open(make_conn, req)


def _build_opener(provider: ProviderInfo) -> urllib.request.OpenerDirector:
    """普通 opener；有隧道配置时用走隧道的 opener（绕过系统代理）。"""
    if provider.tunnel_host and provider.tunnel_port:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({}),  # 隧道直连 127.0.0.1，必须绕过系统代理(Clash 等)
            _TunnelHTTPSHandler(provider.tunnel_host, provider.tunnel_port),
        )
    return urllib.request.build_opener()


def chat(
    provider: ProviderInfo,
    model: str,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.6,
    timeout_s: float = 120.0,
    extra_body: Optional[dict[str, Any]] = None,
) -> DirectReply:
    key = resolve_key(provider.credential_key)
    url = provider.base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if extra_body:
        body.update(extra_body)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    opener = _build_opener(provider)
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = _safe_detail(exc)
        status = exc.code
        if status in (401, 403):
            raise AuthError(detail)  # 移除 from exc，避免 key 泄露
        if status == 429:
            retry_after = float(exc.headers.get("Retry-After", "1")) if exc.headers else 1.0
            raise RateLimitError(detail, retry_after=max(0.5, retry_after))  # 移除 from exc
        if status >= 500:
            raise UpstreamError(detail)  # 移除 from exc
        raise DirectError(f"HTTP {status}: {detail}", retryable=False)  # 移除 from exc
    except urllib.error.URLError as exc:
        raise UpstreamError(str(exc))  # 移除 from exc
    except TimeoutError as exc:
        raise TimeoutError_(str(exc))  # 移除 from exc

    try:
        choice = raw["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content")
        finish = choice.get("finish_reason", "")
        usage = raw.get("usage") or {}
    except (KeyError, IndexError) as exc:
        raise DirectError("上游返回结构异常", retryable=True, detail=_safe_detail(raw)) from exc

    if content is None or not str(content).strip():
        raise EmptyContentError(f"finish={finish}, usage={usage}")

    return DirectReply(
        content=str(content),
        model=raw.get("model", model),
        finish_reason=finish,
        usage=usage,
        raw=raw,
    )


def _safe_detail(obj: Any) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False)[:500]
    except Exception:
        text = str(obj)[:500]
    # 防呆：任何情况下不打印 key/Authorization
    if "Authorization" in text or "Bearer " in text:
        return "<redacted upstream detail>"
    return text


def guess_image_hint(task: str, images: Optional[list[str]]) -> str:
    """agent 模式无法直接传图时，把图片路径拼进任务文本作为提示。"""
    if not images:
        return task
    return task + "\n\n[以下图片文件位于工作目录，请用工具查看:] " + " ".join(images)
