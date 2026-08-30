"""执行层原语。

agent 模式：把任务派给 DeepSeek Harness headless agent ——
  per-run settings（重定向 agent-default-model）+ patch 覆盖 → 子进程执行。
direct 模式：直连 /chat/completions（快问快答，不启动 agent）。

本模块只做"一次尝试"；重试 / 降级 / 熔断编排在 degrade.py。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import logger
from .config import Config, DSH_SETTINGS
from .llm_api import build_messages, chat, guess_image_hint
from .models import ModelSpec, ProviderRef, RouterError
from .provider_catalog import (
    load_providers,
    provider_exists,
    render_patch,
    render_run_settings,
)


@dataclass
class AgentOutcome:
    ok: bool
    output: str = ""
    error: str = ""
    exit_code: Optional[int] = None
    duration_s: float = 0.0
    stdout: str = ""
    stderr: str = ""
    run_dir: Optional[Path] = None
    transcript: str = ""
    worker_session: Optional[Path] = None
    artifacts: dict = field(default_factory=dict)


def _dsh_bin() -> str:
    path = shutil.which("dsh")
    if not path:
        raise RouterError("找不到 dsh 命令。请确认 DeepSeek Harness 已安装且在 PATH 中。")
    return path


class AgentExecutor:
    """把任务派给 DSH headless agent（由路由指定的模型驱动、带真实工具）。"""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def execute(
        self,
        model: ModelSpec,
        task: str,
        *,
        provider: ProviderRef,
        cwd: Path,
        run_dir: Path,
        timeout_s: Optional[float] = None,
        tools_mode: Optional[str] = None,
        session_cleanup: bool = True,
        images: Optional[list[str]] = None,
    ) -> AgentOutcome:
        task_id = run_dir.name
        started = time.monotonic()
        started_epoch = time.time()   # 用于会话 mtime 扫描（epoch 时钟）
        timeout_s = timeout_s or float(self._cfg.execution.get("timeout_seconds", 600))

        # 1) 复制 provider 目录并生成 per-run settings + patch
        providers = load_providers(DSH_SETTINGS)
        if not provider_exists(providers, provider.dsh_provider):
            return AgentOutcome(
                ok=False,
                error=f"DSH settings 未注册 provider '{provider.dsh_provider}'，已注册: {sorted(providers)}",
            )
        settings_path = render_run_settings(
            providers,
            provider.dsh_provider,
            model.id,
            run_dir / "settings.yaml",
            model_name=model.id,
            context_window=model.context,
        )
        patch_path = render_patch(
            settings_path,
            run_dir / "patch.yml",
            extras_path=Path(__file__).resolve().parent.parent.parent / "config" / "worker-standard.yml",
        )
        if images:
            task = guess_image_hint(task, images)
        task_file = run_dir / "task.txt"
        task_file.write_text(task, encoding="utf-8")

        # 2) 记录清理基线（会话目录）
        sessions_root = Path(os.environ.get("DSH_HOME", "~/.dsh")).expanduser() / "sessions"
        before = _snapshot_sessions(sessions_root, cwd)

        # 3) 实时事件：派活开始
        from .live import emit
        reasoning_effort = str(self._cfg.execution.get("reasoning_effort", "medium"))
        emit("dispatch", task_id=task_id, model=model.id, channel=provider.channel,
             prompt=task[:400], reasoning_effort=reasoning_effort, cwd=str(cwd))

        # 4) 子进程（temp 文件承接输出避免管道阻塞；轮询等待并实时抓工人步骤）
        import tempfile
        env = dict(os.environ)
        env["DSH_TOOLS_MODE"] = tools_mode or str(self._cfg.execution.get("dsh_tools_mode", "danger-full-access"))
        cmd = [_dsh_bin(), "--profile", "headless", "--patch", str(patch_path), task]
        logger.info(task_id, "spawn headless agent", model=model.id, dsh_provider=provider.dsh_provider, cwd=str(cwd))
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".out") as out_f, \
             tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".err") as err_f:
            proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=out_f, stderr=err_f, text=True)
            emitted_steps: set[str] = set()
            worker_session_path: Optional[Path] = None
            timed_out = False
            deadline = time.monotonic() + timeout_s
            while proc.poll() is None:
                if time.monotonic() > deadline:
                    timed_out = True
                    proc.kill()
                    proc.wait()
                    break
                # 实时抓工人步骤
                if worker_session_path is None:
                    worker_session_path = _find_worker_session(sessions_root, cwd, started_epoch)
                if worker_session_path is not None:
                    for step in _worker_step_lines(worker_session_path):
                        if step not in emitted_steps:
                            emitted_steps.add(step)
                            emit("worker_step", task_id=task_id, model=model.id, step=step)
                time.sleep(1.5)
            out_f.flush(); err_f.flush()
            out_f.seek(0); err_f.seek(0)
            stdout = (out_f.read() or "").strip()
            stderr = (err_f.read() or "").strip()
        if timed_out:
            logger.warn(task_id, "agent timeout, killing process", timeout_s=timeout_s)
            if session_cleanup:
                _cleanup_new_sessions(sessions_root, cwd, before, task_id)
            emit("fail", task_id=task_id, model=model.id, channel=provider.channel, reason=f"超时(>{timeout_s:.0f}s)")
            return AgentOutcome(
                ok=False,
                error=f"超时(>{timeout_s:.0f}s)",
                duration_s=time.monotonic() - started,
                run_dir=run_dir,
                stdout=stdout,
                stderr=stderr,
            )

        duration = time.monotonic() - started
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        # headless 约定：最后一条非空 assistant 消息在 stdout；成功时 stderr 为空
        output = stdout
        if not output and stderr:
            output = stderr
        ok = proc.returncode == 0 and bool(output)

        # 提取工人工作轨迹（让大脑/用户能看到工人一步步干了什么）
        transcript, worker_session = "", None
        if ok:
            ws = _find_worker_session(sessions_root, cwd, started_epoch)
            if ws:
                worker_session = ws
                transcript = extract_worker_transcript(ws)
        if session_cleanup:
            _cleanup_new_sessions(sessions_root, cwd, before, task_id)

        if not ok:
            logger.warn(task_id, "agent failed", exit_code=proc.returncode, stderr=stderr[:400])
            emit("fail", task_id=task_id, model=model.id, channel=provider.channel,
                 reason=(stderr or "空输出")[:200], exit_code=proc.returncode)
            return AgentOutcome(
                ok=False,
                error=f"agent 退出码 {proc.returncode}: {(stderr or '空输出')[:400]}",
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_s=duration,
                run_dir=run_dir,
            )
        logger.info(task_id, "agent succeeded", exit_code=proc.returncode, duration_s=round(duration, 2), chars=len(output))
        emit("succeed", task_id=task_id, model=model.id, channel=provider.channel,
             duration_s=round(duration, 1), chars=len(output))
        return AgentOutcome(
            ok=True,
            output=output,
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            run_dir=run_dir,
            transcript=transcript,
            worker_session=worker_session,
            artifacts={"settings": str(settings_path), "patch": str(patch_path), "task_file": str(task_file)},
        )


class DirectExecutor:
    """direct 模式单次调用（重试/降级由 degrade 层负责）。"""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def execute(
        self,
        model: ModelSpec,
        task: str,
        *,
        provider: ProviderRef,
        images: Optional[list[str]] = None,
        system: str = "",
        max_tokens: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ):
        prov_info = self._cfg.provider(provider.channel)
        max_tokens = max_tokens or int(self._cfg.execution.get("direct_max_tokens", 2048))
        messages = build_messages(task, system=system, images=images)
        return chat(prov_info, model.id, messages, max_tokens=max_tokens, timeout_s=timeout_s or 120.0)


# ---- 会话清理（尽力而为） ------------------------------------------------
def _snapshot_sessions(root: Path, cwd: Path) -> set[str]:
    anchor = _anchor(cwd)
    base = root / anchor
    if not base.exists():
        return set()
    return {p.name for p in base.iterdir() if p.is_file()}


def _anchor(cwd: Path) -> str:
    # DSH 会话目录按工作目录锚定（如 /Users/me/proj → --Users-me-proj--）
    abs_cwd = str(cwd.resolve())
    return "--" + abs_cwd.lstrip("/").replace("/", "-") + "--"


def _find_worker_session(root: Path, cwd: Path, started: float) -> Optional[Path]:
    """本次运行窗口内新出现的工人会话目录（取最新的）。"""
    base = root / _anchor(cwd)
    if not base.exists():
        return None
    candidates = []
    for p in base.iterdir():
        if p.is_dir() and p.name.startswith("session-"):
            try:
                mtime = (p / "session.jsonl.zstd").stat().st_mtime
            except OSError:
                continue
            # 运行开始前 5s 到现在的窗口
            if started - 5 <= mtime <= started + 6000:
                candidates.append((mtime, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def _zstd_cat(path: Path) -> str:
    """用 zstd CLI 解压（venv 无 zstandard 时的兜底）。"""
    try:
        out = subprocess.run(
            ["zstd", "-dc", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def _worker_step_lines(session_path: Path) -> list[str]:
    """把工人会话解析成逐步工具调用行（供实时面板/轨迹共用）。"""
    import json

    log_path = session_path / "session.jsonl.zstd"
    if not log_path.exists():
        return []
    raw = _zstd_cat(log_path)
    if not raw:
        return []

    lines_out: list[str] = []
    pending: dict[str, str] = {}
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        d = e.get("data") or {}
        if t == "tool/call":
            name = d.get("name", "?")
            args = d.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            pending[d.get("callId", "")] = f"  s{len(lines_out)+1}  {name}: {_tool_summary(name, args)}"
        elif t == "tool/result" and d.get("message"):
            call_id = (d.get("message") or {}).get("source", {}).get("callId", "")
            text = _result_text(d.get("message"))
            if call_id in pending:
                lines_out.append(pending.pop(call_id) + "  →  " + text[:160].replace("\n", " "))
    return lines_out


def extract_worker_transcript(session_path: Path, max_steps: int = 25) -> str:
    """把工人会话日志提炼成可读的工作轨迹：每步工具调用 + 结果摘要 + 最终答复。"""
    import json

    log_path = session_path / "session.jsonl.zstd"
    if not log_path.exists():
        return ""
    raw = _zstd_cat(log_path)
    if not raw:
        return ""

    lines_out = _worker_step_lines(session_path)
    finals: list[str] = []
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if isinstance(e, dict) and e.get("type") == "assistant/message":
            txt = _message_text((e.get("data") or {}).get("content"))
            if txt:
                finals.append(txt)
    if not lines_out and not finals:
        return ""
    head = f"📋 工人工作过程  session={session_path.name}"
    body = lines_out[:max_steps]
    if len(lines_out) > max_steps:
        body.append(f"  …（共 {len(lines_out)} 步，仅显示前 {max_steps}）")
    tail = ""
    if finals:
        tail = "  最终答复: " + finals[-1][:400].replace("\n", " ")
    return "\n".join([head] + body + ([tail] if tail else []))


def _tool_summary(name: str, args: dict) -> str:
    if name == "bash":
        return (args.get("command") or args.get("cmd") or "")[:90]
    if name in ("write", "edit", "read", "glob", "grep"):
        return str(args.get("file_path") or args.get("pattern") or args.get("path") or "")[:90]
    if name in ("run_code", "code"):
        return (str(args.get("code") or args.get("command") or "")[:90])
    s = json_dumps_safe(args)[:60]
    return s


def _result_text(message) -> str:
    content = message.get("content") or []
    parts = []
    for c in content if isinstance(content, list) else [content]:
        if isinstance(c, dict) and c.get("type") == "tool-result":
            inner = c.get("content") or []
            for b in inner if isinstance(inner, list) else [inner]:
                if isinstance(b, dict) and b.get("type") == "text":
                    parts.append(b.get("text", ""))
        elif isinstance(c, dict) and c.get("type") == "text":
            parts.append(c.get("text", ""))
    return " ".join(p for p in parts if p)[:200]


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
    return ""


def json_dumps_safe(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def _cleanup_new_sessions(root: Path, cwd: Path, before: set[str], task_id: str) -> None:
    """只清理本次任务创建的会话文件（通过 task_id 前缀识别）。"""
    try:
        base = root / _anchor(cwd)
        if not base.exists():
            return
        for p in base.iterdir():
            # 只删除本次任务创建的会话文件（文件名包含 task_id）
            if p.is_file() and p.name not in before and p.suffix in (".jsonl", ".json") and task_id in p.name:
                try:
                    p.unlink()
                    logger.info(None, "cleaned session", file=p.name)
                except OSError:
                    pass
    except Exception:  # 清理失败不影响主流程
        pass
