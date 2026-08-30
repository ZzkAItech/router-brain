"""命令行入口：route / run / healthcheck / list-models。"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Optional

from . import __version__
from . import logger
from .config import Config, DEFAULT_POOL, DEFAULT_ROUTING
from .degrade import Runner
from .models import RouterError


def _build_config(args) -> Config:
    return Config(
        pool_path=Path(args.pool),
        routing_path=Path(args.routing),
    )


def _cmd_route(args) -> int:
    cfg = _build_config(args)
    runner = Runner(cfg)
    task_type, decision = runner.decide(args.task, args.hints or "")
    print(json.dumps(decision.as_dict(), ensure_ascii=False))
    return 0


def _cmd_run(args) -> int:
    cfg = _build_config(args)
    runner = Runner(cfg)
    images = args.images.split(",") if args.images else None
    result = runner.run(
        args.task,
        cwd=Path(args.cwd).resolve() if args.cwd else None,
        images=images,
        force_model=args.force_model,
        hints=args.hints or "",
        timeout_s=args.timeout,
        tools_mode=args.tools_mode,
        auto_failover=args.auto_failover,
    )
    # 最终答复（只输出一次）
    if result.ok:
        print("=" * 64)
        print(f"由 {result.model} 完成 ｜ 任务类型: {result.task_type} ｜ 执行: {result.execution} ｜ "
              f"task_id: {result.task_id} ｜ 用时 {result.duration_s:.1f}s")
        print("=" * 64)
        print(result.output)
        print()
        return 0
    print("=" * 64)
    print(f"❌ 执行失败 ｜ 任务类型: {result.task_type} ｜ task_id: {result.task_id}")
    print("=" * 64)
    print(result.error or "未知错误")
    print("尝试序列:", " → ".join(result.attempts))
    return 1


def _cmd_list_models(args) -> int:
    cfg = _build_config(args)
    if args.json:
        models = [
            {
                "id": mid,
                "channels": [p.channel for p in spec.providers],
                "kind": spec.kind,
                "cost": spec.cost,
                "region": spec.region,
                "context": spec.context,
                "roles": list(spec.roles),
                "unreliable": spec.unreliable,
                "excluded": cfg.excluded_reason(spec),
                "note": spec.note,
            }
            for mid, spec in sorted(cfg.models().items())
        ]
        print(json.dumps(models, ensure_ascii=False, indent=2))
        return 0
    print(f"{'模型':<28}{'通道':<18}{'类型':<12}{'成本':<8}{'状态'}")
    # force_channel 设置时只展示该通道可用模型（保持池子干净）
    force = str(cfg.execution.get("force_channel", "") or "")
    iter_models = cfg.available_models() if force else cfg.models().values()
    for spec in sorted(iter_models, key=lambda s: s.id):
        reason = cfg.excluded_reason(spec)
        if reason == "banned":
            status = "🚫 禁用"
        elif reason:
            status = f"❌ {reason}"
        else:
            status = "⚠️ 易限流" if spec.unreliable else "✅"
        # 只显示可用的工人通道（隐藏 worker:false 的）
        ch = ",".join(p.channel for p in spec.providers
                      if cfg.provider(p.channel).worker)
        if force:
            ch = force  # force_channel 下只显示强制通道
        print(f"{spec.id:<28}{ch:<18}{spec.kind:<12}{spec.cost:<8}{status}")
    return 0


def _cmd_healthcheck(args) -> int:
    cfg = _build_config(args)
    runner = Runner(cfg)
    models = cfg.models()
    if args.models:
        wanted = set(args.models.split(","))
        models = {k: v for k, v in models.items() if k in wanted}
    # 有 banned 的展示但跳过实际调用
    targets = [m for m in models.values() if not m.banned]
    if args.limit:
        targets = targets[: args.limit]
    if args.direct_only:
        targets = [m for m in targets if m.channels]
    if not targets:
        print("没有可检查的模型")
        return 1

    def probe(spec) -> dict:
        prov = spec.primary
        probe_text = args.probe or "只回复两个字：正常"
        try:
            # --direct-only 强制走 direct 模式， bypass 路由决策
            if args.direct_only:
                reply = runner._direct.execute(spec, probe_text, provider=prov)
                return {"model": spec.id, "provider": prov.channel, "mode": "direct", "ok": True,
                        "reply": reply.content[:40], "err": ""}
            task_type, decision = runner.decide(probe_text)
            if decision.execution == "direct":
                reply = runner._direct.execute(spec, probe_text, provider=prov)
                return {"model": spec.id, "provider": prov.channel, "mode": "direct", "ok": True,
                        "reply": reply.content[:40], "err": ""}
            # agent 模式
            from .executor import AgentExecutor
            outcome = AgentExecutor(cfg).execute(
                spec,
                probe_text,
                provider=prov,
                cwd=Path.cwd(),
                run_dir=(Path(cfg.execution.get("run_dir", ".run")).resolve())
                / f"hc-{spec.id.replace('/', '_')}-{uuid.uuid4().hex[:8]}",
                timeout_s=args.timeout or 120,
                tools_mode=args.tools_mode,
            )
            return {"model": spec.id, "provider": prov.channel, "mode": "agent", "ok": outcome.ok,
                    "reply": outcome.output[:40], "err": outcome.error[:120]}
        except Exception as exc:
            return {"model": spec.id, "provider": prov.channel, "mode": "?",
                    "ok": False, "reply": "", "err": str(exc)[:120]}

    # 改为顺序执行，避免并发导致的资源竞争
    print(f"healthcheck：{len(targets)} 个模型，顺序执行")
    results: list[dict] = []
    for t in targets:
        results.append(probe(t))
    results.sort(key=lambda r: r["model"])
    print()
    print(f"{'模型':<30}{'provider':<18}{'模式':<8}{'状态':<8}{'回包/错误'}")
    for r in results:
        status = "✅" if r["ok"] else "❌"
        print(f"{r['model']:<30}{r['provider']:<18}{r['mode']:<8}{status:<8}{(r['reply'] or r['err'])[:80]}")
    ok_count = sum(1 for r in results if r["ok"])
    print()
    print(f"可用 {ok_count}/{len(results)}")
    return 0 if ok_count == len(results) else 1


def _cmd_sync_free_models(args) -> int:
    from .openrouter_sync import sync_free_models
    from .config import DEFAULT_POOL
    try:
        added, skipped = sync_free_models(Path(args.pool) if args.pool != str(DEFAULT_POOL) else DEFAULT_POOL)
    except Exception as exc:
        print(f"❌ 同步失败: {exc}")
        return 1
    print(f"✅ 同步完成：新增 {added} 个免费模型，跳过已有 {skipped} 个")
    print("下次 `router-brain list-models` / 派活即可实时使用（配置实时读取）")
    return 0


def _cmd_bai(args) -> int:
    """bai 链路管理（start-bai / bai-usage）。仅当本地存在 bai_link 模块时可用。"""
    from .bai_link import main as bai_main
    bai_argv = []
    if args.bai_once:
        bai_argv.append("--once")
    if args.bai_install:
        bai_argv.append("--install")
    if args.bai_usage:
        bai_argv.append("--usage")
    return bai_main(bai_argv)


def _cmd_dashboard(args) -> int:
    from .dashboard import run
    return run(port=args.port)





def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="router-brain", description="模型路由大脑 v" + __version__)
    parser.add_argument("--pool", default=str(DEFAULT_POOL), help="模型池配置文件")
    parser.add_argument("--routing", default=str(DEFAULT_ROUTING), help="路由规则配置文件")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_route = sub.add_parser("route", help="只输出第一轮路由 JSON")
    p_route.add_argument("task")
    p_route.add_argument("--hints")
    p_route.set_defaults(func=_cmd_route)

    p_run = sub.add_parser("run", help="完整两轮：路由 → 派活 → 降级 → 汇总")
    p_run.add_argument("task")
    p_run.add_argument("--cwd", help="agent 工作目录（默认当前目录）")
    p_run.add_argument("--images", help="逗号分隔的图片路径/URL（vision 任务）")
    p_run.add_argument("--force-model", help="强制指定模型，绕过路由")
    p_run.add_argument("--hints")
    p_run.add_argument("--timeout", type=float, help="agent 超时秒数")
    p_run.add_argument("--tools-mode", help="headless 工具模式（native / code / both，默认 native）")
    p_run.add_argument("--auto-failover", action="store_true", help="失败时由引擎自动换模型（默认停下让大脑决定）")
    p_run.set_defaults(func=_cmd_run)

    p_list = sub.add_parser("list-models", help="列出模型池")
    p_list.add_argument("--json", action="store_true", help="输出 JSON（供大脑程序化读取）")
    p_list.set_defaults(func=_cmd_list_models)

    p_sync = sub.add_parser("sync-free-models", help="从 OpenRouter 拉取最新免费模型并写入配置")
    p_sync.set_defaults(func=_cmd_sync_free_models)

    p_dash = sub.add_parser("dashboard", help="启动实时派活面板（看大脑给工人的任务/提示词/推理强度/进度）")
    p_dash.add_argument("--port", type=int, default=8090)
    p_dash.set_defaults(func=_cmd_dashboard)

    p_hc = sub.add_parser("healthcheck", help="全量冒烟：逐个 ping 模型池")
    p_hc.add_argument("--models", help="逗号分隔，只检查这些模型")
    p_hc.add_argument("--limit", type=int)
    p_hc.add_argument("--direct-only", action="store_true")
    p_hc.add_argument("--timeout", type=float)
    p_hc.add_argument("--tools-mode")
    p_hc.add_argument("--probe", help="冒烟任务文本（默认：只回复两个字：正常）")
    p_hc.set_defaults(func=_cmd_healthcheck)

    # ── 本地私有命令：bai 链路管理（仅当 bai_link 模块存在时注册）──
    try:
        from . import bai_link  # noqa: F401
        p_bai = sub.add_parser("start-bai", help="bai(api.b.ai) 链路自检/自愈/保活（仅本地可用）")
        p_bai.add_argument("--once", action="store_true", help="只自检拉起，不起保活")
        p_bai.add_argument("--install", action="store_true", help="生成 launchd 开机自启")
        p_bai.add_argument("--usage", dest="bai_usage", action="store_true", help="打印用量统计")
        p_bai.add_argument("--bai-once", dest="bai_once", action="store_true", help=argparse.SUPPRESS)
        p_bai.add_argument("--bai-install", dest="bai_install", action="store_true", help=argparse.SUPPRESS)
        p_bai.set_defaults(func=_cmd_bai, bai_once=False, bai_install=False, bai_usage=False)
    except ImportError:
        pass  # 公开版无 bai_link：start-bai 不出现

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RouterError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
