"""实时派活面板：一个本地网页，实时展示大脑给每个工人什么任务/提示词/推理强度/进度。

用法：router-brain dashboard [--port 8090]
打开 http://127.0.0.1:8090 即可看到实时派活流。
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .live import read_recent

HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>路由大脑 · 实时派活面板</title>
<style>
:root{color-scheme:dark}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:20px}
h1{font-size:18px;margin:0 0 4px}
.sub{color:#888;font-size:12px;margin-bottom:16px}
#summary{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.sum-card{background:#171a21;border:1px solid #2a2f3a;border-radius:10px;padding:10px 14px;min-width:110px}
.sum-card .n{font-size:22px;font-weight:600}
.sum-card .l{font-size:11px;color:#888}
#feed{display:flex;flex-direction:column;gap:10px}
.dispatch{background:#171a21;border:1px solid #2a2f3a;border-left:4px solid #4a6cf7;border-radius:10px;padding:12px 14px}
.dispatch.running{border-left-color:#f5a623}
.dispatch.ok{border-left-color:#2ecc71}
.dispatch.fail{border-left-color:#e74c3c}
.dhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;background:#2a2f3a;color:#ccc}
.badge.model{background:#223;color:#7aa2ff}
.badge.ch{background:#232;color:#7ee07e}
.badge.rt{background:#332;color:#ffcc7a}
.status{font-size:11px;font-weight:600}
.status.running{color:#f5a623}.status.ok{color:#2ecc71}.status.fail{color:#e74c3c}
.prompt{font-size:12px;color:#ccc;background:#0f1115;border-radius:6px;padding:6px 8px;white-space:pre-wrap;word-break:break-all}
.steps{margin-top:8px;font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#9ee7a0;white-space:pre-wrap}
.steps .new{color:#5cff8a;animation:fade .6s}
@keyframes fade{from{background:#1e3a24}to{background:transparent}}
.empty{color:#666;font-size:13px;padding:30px;text-align:center}
</style></head><body>
<h1>🧠 路由大脑 · 实时派活面板</h1>
<div class="sub">大脑给每个工人什么任务 / 什么模型 / 什么推理强度 / 干到哪一步 —— 实时刷新</div>
<div id="summary">
  <div class="sum-card"><div class="n" id="c-total">0</div><div class="l">派活次数</div></div>
  <div class="sum-card"><div class="n" id="c-running" style="color:#f5a623">0</div><div class="l">进行中</div></div>
  <div class="sum-card"><div class="n" id="c-ok" style="color:#2ecc71">0</div><div class="l">成功</div></div>
  <div class="sum-card"><div class="n" id="c-fail" style="color:#e74c3c">0</div><div class="l">失败</div></div>
</div>
<div id="feed"><div class="empty">等待派活…（在大脑会话里给任务，这里会实时出现）</div></div>
<script>
let lastLen = 0, lastTask='';
async function refresh(){
  try{
    const r = await fetch('/live?t='+Date.now());
    const j = await r.json();
    const ev = j.events||[];
    render(ev);
  }catch(e){}
}
function render(ev){
  // 按 task_id 聚合
  const tasks={}, order=[];
  for(const e of ev){
    const tid=e.task_id||'direct';
    if(!tasks[tid]){tasks[tid]={id:tid,model:'',channel:'',rt:'',prompt:'',status:'running',steps:[],ts:e.ts};order.push(tid);}
    const t=tasks[tid];
    if(e.model)t.model=e.model;
    if(e.channel)t.channel=e.channel;
    if(e.reasoning_effort)t.rt=e.reasoning_effort;
    if(e.prompt)t.prompt=e.prompt;
    if(e.kind==='worker_step'){t.steps.push({s:e.step,new:(e.ts===t.lastTs?false:true)});t.lastTs=e.ts;}
    if(e.kind==='succeed'){t.status='ok';t.duration=e.duration_s;}
    if(e.kind==='fail'){t.status='fail';t.reason=e.reason;}
  }
  // 统计
  let run=0,ok=0,fl=0;
  for(const id of order){const t=tasks[id];if(t.status==='running')run++;else if(t.status==='ok')ok++;else fl++;}
  document.getElementById('c-total').textContent=order.length;
  document.getElementById('c-running').textContent=run;
  document.getElementById('c-ok').textContent=ok;
  document.getElementById('c-fail').textContent=fl;
  const feed=document.getElementById('feed');
  const cards=[];
  for(const id of order.slice(-25).reverse()){
    const t=tasks[id];
    const stCls=t.status;
    const stTxt={running:'进行中…',ok:'成功 ✓',fail:'失败 ✗'}[t.status]||t.status;
    cards.push(`<div class="dispatch ${stCls}">
      <div class="dhead">
        <span class="badge model">${esc(t.model||'?')}</span>
        <span class="badge ch">${esc(t.channel||'')}</span>
        <span class="badge rt">🧠 ${esc(t.rt||'medium')}</span>
        <span class="status ${stCls}">${stTxt}${t.duration?' · '+t.duration+'s':''}</span>
        <span style="font-size:10px;color:#666">${esc(t.ts||'')} · ${esc(id.slice(0,8))}</span>
      </div>
      <div class="prompt">${esc(t.prompt||'(无提示词)')}</div>
      <div class="steps">${t.steps.map(s=>esc(s.s)).join('\\n')}${t.reason?('\\n❌ '+esc(t.reason)):''}</div>
    </div>`);
  }
  feed.innerHTML = cards.join('') || '<div class="empty">等待派活…</div>';
}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
refresh(); setInterval(refresh, 1500);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/live"):
            body = json.dumps({"events": read_recent(limit=300), "now": time.time()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass  # 静默访问日志


def run(port: int = 8090) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"🧠 路由大脑实时派活面板: http://127.0.0.1:{port}")
    print("在大脑会话里给任务，这里实时显示派活/提示词/推理强度/工人进度。Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8090)
    args = p.parse_args()
    raise SystemExit(run(args.port))
