#!/usr/bin/env python3
"""
andon_board.py — render an .andon/ledger.json (v2) as a live value-stream board.

Two layouts:
  --layout linear  (default)  the stream as a left-to-right lit pipeline
  --layout wheel              the stream as a ring; render wraps back to crate as
                              the "next pass" arc, the hub shows cycle/pass — the
                              PDCA wheel made literal

Both share one step scrubber over the ledger's `history` (each entry a step,
kind: pass | subcycle), color wires green/red/unknown, glow the constraint as an
andon lamp, draw sub-cycle backtracks, badge accelerated steps (subagent / MCP),
and mark the converged pass.

Usage:
    python andon_board.py [LEDGER_JSON] [-o OUTPUT_HTML] [--layout linear|wheel]

Pure standard library; the emitted HTML has no external dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Andon Board — __TITLE__</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --ink:#e6edf3; --muted:#8b949e;
    --line:#30363d; --green:#3fb950; --red:#f85149; --unknown:#6e7681;
    --lamp:#d29922; --slow:#a371f7; --pill:#1b2230;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:1040px;margin:0 auto;padding:28px 20px 48px}
  header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:6px}
  h1{font-size:20px;font-weight:650;margin:0;letter-spacing:.2px}
  .meta{color:var(--muted);font-size:13px}
  .board{background:var(--panel);border:1px solid var(--line);border-radius:14px;
         padding:14px 10px 6px;margin:14px 0}
  svg{width:100%;height:auto;display:block}
  .caption{min-height:22px;color:var(--muted);font-size:13px;margin:10px 4px 0}
  .caption b{color:var(--ink);font-weight:600}
  .controls{display:flex;align-items:center;gap:14px;margin:8px 4px 0}
  input[type=range]{flex:1;accent-color:var(--lamp)}
  .cyc{font-variant-numeric:tabular-nums;color:var(--muted);font-size:13px;white-space:nowrap}
  .legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin:14px 4px 0}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .sw{width:22px;height:0;border-top:3px solid}
  .dot{width:11px;height:11px;border-radius:50%}
  .note{color:var(--muted);font-size:12.5px;margin:10px 4px 0;font-style:italic}
  @keyframes pulse{0%,100%{opacity:.4}50%{opacity:1}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Andon Board</h1>
    <span class="meta" id="meta"></span>
  </header>
  <div class="board"><div id="svg"></div></div>
  <div class="controls">
    <span class="cyc">step</span>
    <input type="range" id="scrub" min="0" max="0" value="0" step="1">
    <span class="cyc" id="lbl1"></span>
  </div>
  <div class="caption" id="cap"></div>
  <div class="legend">
    <span><i class="sw" style="border-color:var(--green)"></i>green</span>
    <span><i class="sw" style="border-color:var(--red)"></i>red</span>
    <span><i class="sw" style="border-color:var(--unknown)"></i>unknown</span>
    <span><i class="sw" style="border-color:var(--slow);border-top-style:dashed"></i>slow lane</span>
    <span><i class="dot" style="background:var(--lamp);box-shadow:0 0 8px var(--lamp)"></i>constraint</span>
    <span style="color:var(--lamp)">&#8617; sub-cycle backtrack</span>
    <span>&#9889; subagent &nbsp; &#9670; MCP</span>
  </div>
  <div class="note" id="note"></div>
</div>
<script>
const L = __LEDGER_JSON__;
const LAYOUT = "__LAYOUT__";
const wireKey = (f,t) => f + "\u2192" + t;
const COLOR = {green:"var(--green)", red:"var(--red)", unknown:"var(--unknown)"};
function esc(s){ return String(s).replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }
function trunc(s,n){ s=String(s||""); return s.length>n ? s.slice(0,n-1)+"\u2026" : s; }

function buildSteps(){
  const steps = [];
  (L.history || []).forEach(h => { if(h.wires||h.constraint||h.kind) steps.push(Object.assign({},h)); });
  steps.push({kind:"pass", pass:L.pass, cycle:L.cycle, wires:L.wires,
              constraint:L.constraint, cursor:L.cursor, via:[], current:true, converged:false});
  return steps;
}
const STEPS = buildSteps();
const NODES = (L.stages && L.stages.length) ? L.stages
            : Array.from(new Set([].concat(...L.wires.map(w=>[w.from,w.to]))));
const REAL = new Set(L.wires.map(w => wireKey(w.from,w.to)));
const WIRE = {}; L.wires.forEach(w => WIRE[wireKey(w.from,w.to)] = w);

function statusFor(step, w){
  if(step.wires){ const m = step.wires.find(x => wireKey(x.from,x.to)===wireKey(w.from,w.to)); if(m) return m.status; }
  return step.current ? w.status : "unknown";
}
function crefOf(step){ const c = step.constraint; return c ? (c.ref||c) : null; }

function badges(svg, step, W){
  const via = step.via || []; let bx = W-6, by = 16;
  if(step.converged){ svg.push(`<text x="${bx}" y="${by}" fill="var(--green)" font-size="12" text-anchor="end">\u2713 converged</text>`); by+=17; }
  via.forEach(v => {
    const icon = v.startsWith("mcp:") ? "\u25C6 "+v.slice(4) : (v==="subagent" ? "\u26A1 subagent" : v);
    svg.push(`<text x="${bx}" y="${by}" fill="var(--slow)" font-size="11.5" text-anchor="end">${esc(icon)}</text>`); by+=16;
  });
}

// ---------- LINEAR ----------
function renderLinear(step){
  const n = NODES.length, W=1040, padX=78, rowY=78, H=196;
  const span = n>1 ? (W-padX*2)/(n-1) : 0;
  const xOf = {}; NODES.forEach((nm,i)=> xOf[nm]=padX+i*span);
  const boxW = Math.min(108,(span*0.6)||108), boxH=40;
  const cref = crefOf(step), cursor = step.cursor && step.cursor.stage;
  const s = [`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-family="inherit">`];
  s.push(`<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="var(--muted)"/></marker><marker id="ahb" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="var(--lamp)"/></marker></defs>`);
  L.wires.forEach(w => {
    const x1=xOf[w.from], x2=xOf[w.to]; if(x1==null||x2==null) return;
    const st=statusFor(step,w), col=COLOR[st]||COLOR.unknown;
    const sx=x1+boxW/2, ex=x2-boxW/2, mx=(sx+ex)/2, dash=w.lane==="slow"?` stroke-dasharray="7 5"`:"";
    const isC = cref && wireKey(w.from,w.to)===cref;
    s.push(`<line x1="${sx}" y1="${rowY}" x2="${ex}" y2="${rowY}" stroke="${col}" stroke-width="${isC?5:3}"${dash} marker-end="url(#ah)"/>`);
    const lbl = trunc(w.contract||(w.lane==="slow"?"slow":""),15);
    if(lbl){ const lw=lbl.length*6.0+10;
      s.push(`<rect x="${mx-lw/2}" y="${rowY-23}" width="${lw}" height="15" rx="4" fill="var(--pill)"/>`);
      s.push(`<text x="${mx}" y="${rowY-12}" fill="${w.lane==='slow'?'var(--slow)':'var(--muted)'}" font-size="10.5" text-anchor="middle">${esc(lbl)}</text>`); }
    if(isC) s.push(`<circle cx="${mx}" cy="${rowY-32}" r="7" fill="var(--lamp)" style="filter:drop-shadow(0 0 6px var(--lamp));animation:pulse 1.1s infinite"/>`);
  });
  if(step.kind==="subcycle" && xOf[step.from_stage]!=null && xOf[step.back_to]!=null){
    const fx=xOf[step.from_stage], bx=xOf[step.back_to], dipY=rowY+56, y0=rowY+boxH/2;
    s.push(`<path d="M ${fx} ${y0} C ${fx} ${dipY}, ${bx} ${dipY}, ${bx} ${y0}" fill="none" stroke="var(--lamp)" stroke-width="2.5" stroke-dasharray="6 4" marker-end="url(#ahb)"/>`);
    s.push(`<text x="${(fx+bx)/2}" y="${dipY+14}" fill="var(--lamp)" font-size="11" text-anchor="middle">\u21A9 sub-cycle: re-verify ${esc(step.back_to)}</text>`);
  }
  NODES.forEach(nm => {
    const x=xOf[nm]-boxW/2, y=rowY-boxH/2, isC = cref && nm===cref;
    s.push(`<rect x="${x}" y="${y}" width="${boxW}" height="${boxH}" rx="9" fill="#0d1117" stroke="${isC?'var(--lamp)':'var(--line)'}" stroke-width="${isC?2:1.5}"/>`);
    s.push(`<text x="${xOf[nm]}" y="${rowY+4}" fill="var(--ink)" font-size="12" text-anchor="middle">${esc(trunc(nm,14))}</text>`);
    if(cursor===nm) s.push(`<path d="M ${xOf[nm]-6} ${y-9} L ${xOf[nm]+6} ${y-9} L ${xOf[nm]} ${y-2} Z" fill="var(--ink)"/>`);
  });
  badges(s, step, W);
  s.push(`</svg>`); return s.join("");
}

// ---------- WHEEL ----------
function polar(cx,cy,R,i,n){ const a=-Math.PI/2 + 2*Math.PI*i/n; return [cx+R*Math.cos(a), cy+R*Math.sin(a)]; }
function renderWheel(step){
  const n = NODES.length, W=660, H=500, cx=330, cy=250, R=168;
  const pos = {}; NODES.forEach((nm,i)=> pos[nm]=polar(cx,cy,R,i,n));
  const idxOf = {}; NODES.forEach((nm,i)=> idxOf[nm]=i);
  const cref = crefOf(step), cursor = step.cursor && step.cursor.stage;
  const s = [`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-family="inherit">`];
  s.push(`<defs><marker id="ahw" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="var(--muted)"/></marker><marker id="ahl" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="var(--lamp)"/></marker></defs>`);

  function edge(aName,bName,col,dash,marker,width,label,labelColor){
    const [ax,ay]=pos[aName], [bx,by]=pos[bName];
    let dx=bx-ax, dy=by-ay; const len=Math.hypot(dx,dy)||1; dx/=len; dy/=len;
    const off=34; const sx=ax+dx*off, sy=ay+dy*off, ex=bx-dx*off, ey=by-dy*off;
    s.push(`<line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" stroke="${col}" stroke-width="${width}"${dash} marker-end="url(#${marker})"/>`);
    const mx=(sx+ex)/2, my=(sy+ey)/2;
    if(label){ const lw=label.length*6.0+10;
      s.push(`<rect x="${mx-lw/2}" y="${my-8}" width="${lw}" height="15" rx="4" fill="var(--pill)"/>`);
      s.push(`<text x="${mx}" y="${my+3}" fill="${labelColor}" font-size="10" text-anchor="middle">${esc(label)}</text>`); }
    return [mx,my];
  }

  // ring edges between consecutive stages
  for(let i=0;i<n;i++){
    const a=NODES[i], b=NODES[(i+1)%n], k=wireKey(a,b), w=WIRE[k];
    const wrap = (i===n-1);
    if(w){
      const st=statusFor(step,w), col=COLOR[st]||COLOR.unknown, isC = cref && k===cref;
      const dash = w.lane==="slow" ? ` stroke-dasharray="7 5"` : "";
      const lab = trunc(w.contract||(w.lane==="slow"?"slow":""),12);
      const [mx,my]=edge(a,b,col,dash,"ahw",isC?5:3,lab,w.lane==='slow'?'var(--slow)':'var(--muted)');
      if(isC) s.push(`<circle cx="${mx}" cy="${my-14}" r="7" fill="var(--lamp)" style="filter:drop-shadow(0 0 6px var(--lamp));animation:pulse 1.1s infinite"/>`);
    } else if(wrap){
      edge(a,b,"var(--lamp)",` stroke-dasharray="3 5"`,"ahl",2,"\u21BA next pass","var(--lamp)");
    }
  }
  // non-consecutive real wires (forks) as inner chords
  L.wires.forEach(w => {
    const k=wireKey(w.from,w.to); if(idxOf[w.to]===(idxOf[w.from]+1)%n) return;
    const st=statusFor(step,w), col=COLOR[st]||COLOR.unknown;
    edge(w.from,w.to,col,` stroke-dasharray="2 3"`,"ahw",2,"",null);
  });
  // sub-cycle inner chord
  if(step.kind==="subcycle" && pos[step.from_stage] && pos[step.back_to]){
    const [ax,ay]=pos[step.from_stage], [bx,by]=pos[step.back_to];
    const mx=(ax+bx)/2*0.72+cx*0.28, my=(ay+by)/2*0.72+cy*0.28;
    s.push(`<path d="M ${ax} ${ay} Q ${mx} ${my} ${bx} ${by}" fill="none" stroke="var(--lamp)" stroke-width="2.5" stroke-dasharray="6 4" marker-end="url(#ahl)"/>`);
    s.push(`<text x="${mx}" y="${my-6}" fill="var(--lamp)" font-size="10.5" text-anchor="middle">\u21A9 ${esc(step.back_to)}</text>`);
  }
  // cursor hand
  if(cursor && pos[cursor]){ const [hx,hy]=pos[cursor];
    s.push(`<line x1="${cx}" y1="${cy}" x2="${hx}" y2="${hy}" stroke="var(--ink)" stroke-width="1.5" opacity="0.5"/>`); }
  // nodes
  NODES.forEach(nm => {
    const [x,y]=pos[nm], isC = cref && nm===cref, isCur = cursor===nm;
    const bw=Math.max(64, esc(trunc(nm,14)).length*7+14), bh=28;
    s.push(`<rect x="${x-bw/2}" y="${y-bh/2}" width="${bw}" height="${bh}" rx="8" fill="#0d1117" stroke="${isC?'var(--lamp)':(isCur?'var(--ink)':'var(--line)')}" stroke-width="${isC||isCur?2:1.5}"/>`);
    s.push(`<text x="${x}" y="${y+4}" fill="var(--ink)" font-size="11.5" text-anchor="middle">${esc(trunc(nm,14))}</text>`);
  });
  // hub
  s.push(`<circle cx="${cx}" cy="${cy}" r="56" fill="#0d1117" stroke="var(--line)"/>`);
  if(step.converged) s.push(`<text x="${cx}" y="${cy-22}" fill="var(--green)" font-size="13" text-anchor="middle">\u2713</text>`);
  s.push(`<text x="${cx}" y="${cy+2}" fill="var(--ink)" font-size="22" font-weight="650" text-anchor="middle">cycle ${step.cycle||1}</text>`);
  s.push(`<text x="${cx}" y="${cy+24}" fill="var(--muted)" font-size="12" text-anchor="middle">pass ${step.pass||1} \u00b7 ${esc(step.kind||"pass")}</text>`);
  badges(s, step, W);
  s.push(`</svg>`); return s.join("");
}

function render(idx){
  const step = STEPS[idx];
  document.getElementById("svg").innerHTML = (LAYOUT==="wheel") ? renderWheel(step) : renderLinear(step);
  const greens = L.wires.filter(w => statusFor(step,w)==="green").length;
  document.getElementById("lbl1").textContent = (step.kind||"pass")+" \u00b7 p"+(step.pass||"?")+"/c"+(step.cycle||"?");
  let cap = `<b>${greens}/${L.wires.length}</b> wires green`;
  const cref = crefOf(step); if(cref) cap += ` \u00b7 constraint <b>${esc(cref)}</b>`;
  if(step.kind==="subcycle") cap += ` \u00b7 <b>sub-cycle</b> back to ${esc(step.back_to||"")}`;
  if(step.closed_bugs!=null||step.closed_features!=null) cap += ` \u00b7 closed ${step.closed_bugs||0} bugs, ${step.closed_features||0} features`;
  const via=step.via||[]; if(via.length) cap += ` \u00b7 via ${via.map(esc).join(", ")}`;
  if(step.current) cap += ` \u00b7 <b>current</b>`;
  document.getElementById("cap").innerHTML = cap;
}

document.getElementById("meta").textContent =
  (L.stages?L.stages.join("  \u2192  "):"") + "   \u00b7   cycle "+(L.cycle||1)+" \u00b7 pass "+(L.pass||1)
  + " \u00b7 mode: "+(L.mode||"propose")+" \u00b7 intent: "+(L.intent||"harden")+" \u00b7 ["+LAYOUT+"]";
const scrub = document.getElementById("scrub");
scrub.max = STEPS.length-1; scrub.value = STEPS.length-1;
scrub.addEventListener("input", e => render(parseInt(e.target.value,10)));
if(STEPS.length<=1){ scrub.disabled=true;
  document.getElementById("note").textContent =
    "Only the current state is shown. Record pass and sub-cycle steps in history to scrub the loop revolution by revolution."; }
render(STEPS.length-1);
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render .andon/ledger.json as an HTML board.")
    ap.add_argument("ledger", nargs="?", default=".andon/ledger.json")
    ap.add_argument("-o", "--output", default="andon-board.html")
    ap.add_argument("--layout", choices=["linear", "wheel"], default="linear")
    args = ap.parse_args()

    ledger_path = Path(args.ledger)
    if not ledger_path.exists():
        print(f"Ledger not found: {ledger_path}", file=sys.stderr)
        return 1
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Ledger is not valid JSON: {e}", file=sys.stderr)
        return 1

    title = html.escape(", ".join(ledger.get("stages", [])) or ledger_path.parent.name or "stream")
    out_html = (TEMPLATE
                .replace("__TITLE__", title)
                .replace("__LAYOUT__", args.layout)
                .replace("__LEDGER_JSON__", json.dumps(ledger)))
    Path(args.output).write_text(out_html, encoding="utf-8")
    print(f"Wrote {args.output}  [{args.layout}]  ({len(ledger.get('wires', []))} wires, "
          f"{len(ledger.get('history', []))} steps, "
          f"cycle {ledger.get('cycle','?')} pass {ledger.get('pass','?')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
