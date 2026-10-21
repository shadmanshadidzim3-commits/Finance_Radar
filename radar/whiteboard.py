"""Whiteboard animation: a hand writes and sketches each point while the voice talks.

Every segment of the script becomes one slide on a whiteboard. On each slide the
hand writes the tag and the headline, sketches a doodle stroke by stroke, then
writes the big figure. When the voice moves on, the board slides away and a
blank one comes in.

How it is drawn: one HTML page holds every slide as SVG. `renderAt(t)` puts the
whole picture into the exact state it should have at time t, and headless
Chrome takes a screenshot. Frames where nothing moves (the hand has finished and
only the subtitle is showing) are not screenshotted again; the previous frame is
simply held longer. That roughly halves the work.

Text is revealed with a clip that grows left to right, with the pen tip riding
its edge. That works for any script the browser can shape, Bangla included.
Doodles come from rough.js, which turns clean SVG paths into sketchy marker
lines, and are drawn by animating each stroke's dash offset.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
W, H = 1080, 1920

HEAD_FONT = {"en": "Caveat", "banglish": "Caveat", "bn": "Atma"}
BODY_FONT = {"en": "Inter", "banglish": "Inter", "bn": "Noto Sans Bengali"}


def _face(name: str, file: str) -> str:
    data = base64.b64encode((ASSETS / "fonts" / file).read_bytes()).decode()
    return (f"@font-face{{font-family:'{name}';src:url(data:font/ttf;base64,{data}) "
            f"format('truetype');font-weight:100 900;}}")


# Doodles on a 200x200 grid. Each part: [path, fill or null].
ICONS = {
    "oil": [["M50 55 Q100 43 150 55 L150 172 Q100 184 50 172 Z", "#cbd5e1"],
            ["M50 55 Q100 67 150 55", None],
            ["M50 95 Q100 107 150 95", None], ["M50 135 Q100 147 150 135", None],
            ["M172 12 Q190 42 172 54 Q154 42 172 12 Z", "#1f2937"]],
    "bolt": [["M112 12 L55 108 L96 108 L80 188 L150 80 L108 80 Z", "#fde047"]],
    "bank": [["M28 72 L100 24 L172 72 Z", "#99f6e4"], ["M34 82 L166 82", None],
             ["M46 90 h14 v68 h-14 Z", None], ["M78 90 h14 v68 h-14 Z", None],
             ["M108 90 h14 v68 h-14 Z", None], ["M140 90 h14 v68 h-14 Z", None],
             ["M24 164 L176 164 L176 182 L24 182 Z", "#99f6e4"]],
    "chart_up": [["M28 24 L28 176 L184 176", None],
                 ["M46 146 h22 v30 h-22 Z", "#bfdbfe"], ["M80 122 h22 v54 h-22 Z", "#bfdbfe"],
                 ["M114 94 h22 v82 h-22 Z", "#bfdbfe"], ["M148 62 h22 v114 h-22 Z", "#93c5fd"],
                 ["M40 112 L90 82 L122 96 L178 34", None], ["M152 32 L178 34 L176 60", None]],
    "chart_down": [["M28 24 L28 176 L184 176", None],
                   ["M46 62 h22 v114 h-22 Z", "#fecaca"], ["M80 94 h22 v82 h-22 Z", "#fecaca"],
                   ["M114 122 h22 v54 h-22 Z", "#fecaca"], ["M148 146 h22 v30 h-22 Z", "#fca5a5"],
                   ["M40 40 L90 74 L122 64 L178 128", None], ["M176 102 L178 128 L152 126", None]],
    "money": [["M16 58 h168 v88 h-168 Z", "#bbf7d0"], ["M100 78 a24 24 0 1 0 0.1 0", None],
              ["M40 72 v60", None], ["M160 72 v60", None],
              ["M28 158 h168 v12 h-168 Z", "#86efac"]],
    "ship": [["M18 120 L182 120 L160 160 L40 160 Z", "#cbd5e1"],
             ["M44 88 h36 v32 h-36 Z", "#fca5a5"], ["M82 88 h36 v32 h-36 Z", "#93c5fd"],
             ["M120 88 h36 v32 h-36 Z", "#fde047"], ["M63 56 h36 v32 h-36 Z", "#86efac"],
             ["M8 178 q16 -12 32 0 t32 0 t32 0 t32 0 t32 0 t32 0", None]],
    "factory": [["M20 178 L20 102 L60 122 L60 102 L100 122 L100 102 L140 122 "
                 "L140 58 L172 58 L172 178 Z", "#e2e8f0"],
                ["M40 140 h18 v18 h-18 Z", None], ["M80 140 h18 v18 h-18 Z", None],
                ["M118 140 h18 v18 h-18 Z", None],
                ["M156 48 q-12 -16 4 -26 q16 -10 26 6", None]],
    "globe": [["M100 24 a76 76 0 1 0 0.1 0", "#bfdbfe"], ["M100 24 a34 76 0 1 0 0.1 0", None],
              ["M24 100 L176 100", None], ["M36 62 Q100 78 164 62", None],
              ["M36 138 Q100 122 164 138", None]],
    "house": [["M30 104 L100 40 L170 104", None], ["M50 92 L50 176 L150 176 L150 92", "#fde68a"],
              ["M86 176 L86 128 L114 128 L114 176", None], ["M120 56 L120 30 L138 30 L138 72", None]],
    "cart": [["M14 36 L42 36 L64 136 L164 136", None], ["M48 58 L180 58 L164 116 L58 116 Z", "#fde68a"],
             ["M80 158 a12 12 0 1 0 0.1 0", None], ["M148 158 a12 12 0 1 0 0.1 0", None],
             ["M92 58 L96 116", None], ["M132 58 L128 116", None]],
    "bulb": [["M100 30 C56 30 46 80 72 108 C82 120 84 130 84 142 L116 142 "
              "C116 130 118 120 128 108 C154 80 144 30 100 30 Z", "#fde047"],
             ["M84 154 L116 154", None], ["M88 166 L112 166", None],
             ["M100 4 L100 16", None], ["M38 32 L48 42", None], ["M162 32 L152 42", None],
             ["M20 92 L34 92", None], ["M166 92 L180 92", None]],
    "scale": [["M100 26 L100 172", None], ["M58 176 L142 176", None], ["M26 58 L174 58", None],
              ["M26 58 L10 112", None], ["M26 58 L42 112", None],
              ["M4 112 Q26 136 48 112 Z", "#fde68a"],
              ["M174 58 L158 112", None], ["M174 58 L190 112", None],
              ["M152 112 Q174 136 196 112 Z", "#fde68a"]],
    "people": [["M66 30 a20 20 0 1 0 0.1 0", "#fed7aa"], ["M66 70 L66 128", None],
               ["M36 90 L96 90", None], ["M66 128 L44 178", None], ["M66 128 L88 178", None],
               ["M138 46 a20 20 0 1 0 0.1 0", "#bfdbfe"], ["M138 86 L138 138", None],
               ["M110 104 L166 104", None], ["M138 138 L118 182", None], ["M138 138 L158 182", None]],
    "phone": [["M62 16 h76 v168 h-76 Z", "#e2e8f0"], ["M74 36 h52 v118 h-52 Z", "#99f6e4"],
              ["M100 162 a7 7 0 1 0 0.1 0", None], ["M88 60 L112 60", None],
              ["M84 86 L116 86", None]],
    "document": [["M44 18 L128 18 L160 50 L160 184 L44 184 Z", "#f8fafc"],
                 ["M128 18 L128 50 L160 50", None], ["M64 76 L140 76", None],
                 ["M64 100 L140 100", None], ["M64 124 L140 124", None],
                 ["M64 148 L112 148", None]],
    "warning": [["M100 22 L184 172 L16 172 Z", "#fde047"], ["M100 74 L100 124", None],
                ["M100 146 a5 5 0 1 0 0.1 0", "#1f2937"]],
}
DEFAULT_ICON = {"hook": "chart_up", "story": "document", "lesson": "bulb", "outro": "people"}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
FONTFACES
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:#fdfcf7}
#board{position:absolute;inset:0}
#sub{position:absolute;left:64px;right:64px;top:1440px;min-height:170px;
  background:#fff;border:4px solid #1f2937;border-radius:22px;
  box-shadow:8px 8px 0 #1f2937;padding:26px 36px;
  font:600 50px/1.34 'BODYFONT',sans-serif;color:#111827;display:flex;align-items:center}
#sub:empty{visibility:hidden}
#foot{position:absolute;left:64px;right:64px;top:1672px;font:500 28px 'Inter';color:#64748b}
</style></head><body>
<svg id="board" width="1080" height="1920" viewBox="0 0 1080 1920">
  <defs><pattern id="grid" width="54" height="54" patternUnits="userSpaceOnUse">
    <path d="M54 0 L0 0 0 54" fill="none" stroke="#eef0ea" stroke-width="2"/></pattern></defs>
  <rect width="1080" height="1920" fill="url(#grid)"/>
  <g id="chrome"></g><g id="scenes"></g>
  <g id="hand" visibility="hidden"><g transform="rotate(38)">
    <path d="M0 0 L26 -10 L26 10 Z" fill="#334155"/>
    <rect x="24" y="-17" width="250" height="34" rx="9" fill="#1f2937"/>
    <rect x="58" y="-17" width="16" height="34" fill="#0f766e"/>
    <rect x="250" y="-60" width="560" height="160" rx="30" fill="#475569"/>
    <rect x="236" y="-64" width="40" height="168" rx="12" fill="#334155"/>
    <ellipse cx="196" cy="16" rx="82" ry="66" fill="#e7b38d" stroke="#b07c58" stroke-width="4"/>
    <ellipse cx="120" cy="-24" rx="58" ry="23" transform="rotate(-12 120 -24)" fill="#ecbd98" stroke="#b07c58" stroke-width="4"/>
    <ellipse cx="112" cy="30" rx="62" ry="22" transform="rotate(8 112 30)" fill="#ecbd98" stroke="#b07c58" stroke-width="4"/>
    <ellipse cx="146" cy="62" rx="50" ry="21" transform="rotate(14 146 62)" fill="#e7b38d" stroke="#b07c58" stroke-width="4"/>
    <ellipse cx="172" cy="88" rx="42" ry="19" transform="rotate(20 172 88)" fill="#e7b38d" stroke="#b07c58" stroke-width="4"/>
  </g></g>
</svg>
<div id="sub"></div><div id="foot"></div>
<script>ROUGHJS</script>
<script>
const NS='http://www.w3.org/2000/svg', ICONS=ICONSJSON;
const board=document.getElementById('board'), RC=rough.svg(board);
const HEAD='HEADFONT', TR=0.45, OFF={x:1180,y:2150};
let M, SC=[];
function el(tag,attrs,parent){const e=document.createElementNS(NS,tag);
  for(const k in attrs)e.setAttribute(k,attrs[k]);(parent||board).appendChild(e);return e}
const cvs=document.createElement('canvas').getContext('2d');
function wrap(text,font,maxW){cvs.font=font;const out=[];let cur='';
  for(const w of text.split(/\s+/)){const t=cur?cur+' '+w:w;
    if(cvs.measureText(t).width>maxW&&cur){out.push(cur);cur=w}else cur=t}
  if(cur)out.push(cur);return out}
let clipN=0;
function writable(g,text,x,y,size,color,weight){
  // One line of text revealed by a growing clip; returns the animation item.
  const id='c'+(clipN++);
  const cp=el('clipPath',{id},g), r=el('rect',{x:x-10,y:y-size*1.1,width:0,height:size*1.5},cp);
  const t=el('text',{x,y,'font-family':HEAD,'font-size':size,'font-weight':weight||700,
    fill:color,'clip-path':`url(#${id})`},g);t.textContent=text;
  const w=t.getComputedTextLength();
  return {kind:'text',r,x,y,size,w:w+20,cost:Math.max(0.35,text.length*0.055)}}
function sketch(g,name,x,y,size,seed){
  const parts=ICONS[name]||ICONS.document, gi=el('g',{transform:`translate(${x} ${y}) scale(${size/200})`},g);
  const paths=[];
  parts.forEach((p,i)=>{
    const node=RC.path(p[0],{roughness:1.3,bowing:1.1,stroke:'#1f2937',strokeWidth:3.2,
      fill:p[1]||undefined,fillStyle:'hachure',hachureGap:9,fillWeight:2.2,seed:seed+i});
    gi.appendChild(node);
    // rough draws fill hachures first; draw the outline first instead, like a person would
    const ps=[...node.querySelectorAll('path')];
    const outline=ps.filter(q=>q.getAttribute('fill')==='none'&&q.getAttribute('stroke')==='#1f2937');
    const fills=ps.filter(q=>!outline.includes(q));
    for(const q of [...outline,...fills]){const L=q.getTotalLength();
      q.style.strokeDasharray=L;q.style.strokeDashoffset=L;paths.push({el:q,L})}});
  const total=paths.reduce((a,b)=>a+b.L,0);
  return {kind:'path',paths,total,cost:1.0+Math.min(1.8,total/2600)}}

window.build=function(m){
  M=m;
  const ch=document.getElementById('chrome');
  const b=el('text',{x:64,y:118,'font-family':'Caveat','font-size':58,'font-weight':700,fill:'#0f766e'},ch);
  b.textContent=m.brand;
  const d=el('text',{x:1016,y:116,'text-anchor':'end','font-family':'Inter','font-size':30,fill:'#64748b'},ch);
  d.textContent=m.date;
  m.dots=[];for(let i=0;i<m.scenes.length;i++)
    m.dots.push(el('rect',{x:64+i*(952/m.scenes.length),y:150,width:952/m.scenes.length-14,height:9,rx:4.5,fill:'#e2e8f0'},ch));
  document.getElementById('foot').textContent=m.foot;
  const holder=document.getElementById('scenes');
  m.scenes.forEach((s,i)=>{
    const g=el('g',{visibility:'hidden'},holder), items=[];
    let y=280;
    if(s.label){const it=writable(g,s.label,64,y,50,'#0f766e',700);
      el('path',{d:`M60 ${y+16} q${it.w/2} 10 ${it.w-10} -2`,stroke:'#14b8a6','stroke-width':6,fill:'none',
        'stroke-linecap':'round',style:`stroke-dasharray:${it.w};stroke-dashoffset:${it.w}`},g);
      items.push(it);y+=150}
    const hs=s.stat?112:128, lines=wrap(s.head,`700 ${hs}px ${HEAD}`,950).slice(0,3);
    for(const ln of lines){items.push(writable(g,ln,64,y,hs,'#111827',700));y+=hs*1.02}
    const room=(s.stat?1150:1400)-y, isz=Math.max(320,Math.min(640,room-20));
    items.push(sketch(g,s.icon,(1080-isz)/2,y+10,isz,11*i+3));
    if(s.stat){const col=s.tone==='down'?'#dc2626':s.tone==='up'?'#1d4ed8':'#0f766e';
      let sz=260;cvs.font=`700 ${sz}px ${HEAD}`;while(cvs.measureText(s.stat).width>940&&sz>90){sz-=10;cvs.font=`700 ${sz}px ${HEAD}`}
      const w=cvs.measureText(s.stat).width;
      items.push(writable(g,s.stat,(1080-w)/2,1370,sz,col,700))}
    // Pace the drawing to the voice: the hand should finish well before the
    // segment ends, but never scribble faster than a person could.
    const avail=Math.max(1.2,(s.dur-TR)*0.72), need=items.reduce((a,b)=>a+b.cost,0)+0.25*items.length;
    const k=Math.min(1,avail/need);let t=TR+0.15;
    for(const it of items){it.t0=t;it.t1=t+it.cost*k;t=it.t1+0.25*k}
    SC.push({g,items,s,underline:g.querySelector('path[stroke="#14b8a6"]')});
  });
  return true};

function tipAt(it,p){
  if(it.kind==='text')return{x:it.x-10+it.w*p,y:it.y-it.size*0.28};
  let d=it.total*p;for(const q of it.paths){if(d<=q.L){
      const pt=q.el.getPointAtLength(d), m=q.el.getCTM();
      return{x:pt.x*m.a+pt.y*m.c+m.e,y:pt.x*m.b+pt.y*m.d+m.f}}d-=q.L}
  const q=it.paths[it.paths.length-1], pt=q.el.getPointAtLength(q.L), m=q.el.getCTM();
  return{x:pt.x*m.a+pt.y*m.c+m.e,y:pt.x*m.b+pt.y*m.d+m.f}}
function setItem(it,p){
  if(it.kind==='text'){it.r.setAttribute('width',Math.max(0,it.w*p)+10);return}
  let d=it.total*p;for(const q of it.paths){const v=Math.max(0,Math.min(q.L,d));
    q.el.style.strokeDashoffset=q.L-v;d-=q.L}}
const ease=x=>x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2, lerp=(a,b,u)=>({x:a.x+(b.x-a.x)*u,y:a.y+(b.y-a.y)*u});

window.renderAt=function(t){
  let i=M.scenes.findIndex(s=>t>=s.start&&t<s.start+s.dur);if(i<0)i=M.scenes.length-1;
  const s=M.scenes[i], lt=t-s.start;
  M.dots.forEach((d,j)=>d.setAttribute('fill',j<=i?'#14b8a6':'#e2e8f0'));
  SC.forEach((c,j)=>{const show=j===i||(j===i-1&&lt<TR);c.g.setAttribute('visibility',show?'visible':'hidden')});
  let moving=false;
  if(lt<TR&&i>0){const u=ease(lt/TR);moving=true;
    SC[i-1].g.setAttribute('transform',`translate(${-1080*u} 0)`);
    SC[i].g.setAttribute('transform',`translate(${1080*(1-u)} 0)`)}
  else SC[i].g.setAttribute('transform','');
  if(i>0)SC[i-1].items.forEach(it=>setItem(it,1));
  const c=SC[i];let hand=null;
  c.items.forEach((it,j)=>{const p=Math.max(0,Math.min(1,(lt-it.t0)/(it.t1-it.t0)));setItem(it,p);
    if(lt>=it.t0&&lt<it.t1)hand=tipAt(it,p)});
  if(c.underline){const it=c.items[0],p=Math.max(0,Math.min(1,(lt-it.t1)/0.3));
    c.underline.style.strokeDashoffset=it.w*(1-p)}
  if(!hand){const prev=[...c.items].reverse().find(it=>lt>=it.t1), next=c.items.find(it=>lt<it.t0);
    if(next&&lt>=TR){const a=prev?tipAt(prev,1):OFF, b=tipAt(next,0),
        t0=prev?prev.t1:TR, u=ease(Math.min(1,(lt-t0)/Math.max(0.01,next.t0-t0)));hand=lerp(a,b,u)}
    else if(prev&&!next&&lt-prev.t1<0.6){hand=lerp(tipAt(prev,1),OFF,ease((lt-prev.t1)/0.6))}}
  const h=document.getElementById('hand');
  if(hand&&!(lt<TR&&i>0)){moving=true;const wob=Math.sin(t*31)*3;
    h.setAttribute('transform',`translate(${hand.x} ${hand.y+wob})`);h.setAttribute('visibility','visible')}
  else h.setAttribute('visibility','hidden');
  let sub='';for(const x of s.subs)if(lt>=x.t0&&lt<x.t1)sub=x.text;
  const sb=document.getElementById('sub');if(sb.textContent!==sub)sb.textContent=sub;
  return moving?'move':'still|'+i+'|'+sub};
</script></body></html>"""


def page_html(lang: str) -> str:
    faces = "".join([_face("Caveat", "Caveat.ttf"), _face("Atma", "Atma-SemiBold.ttf"),
                     _face("Inter", "Inter.ttf"),
                     _face("Noto Sans Bengali", "NotoSansBengali.ttf")])
    return (PAGE.replace("FONTFACES", faces)
            .replace("ROUGHJS", (ASSETS / "js" / "rough.js").read_text(encoding="utf8"))
            .replace("ICONSJSON", json.dumps(ICONS))
            .replace("HEADFONT", HEAD_FONT.get(lang, "Caveat"))
            .replace("BODYFONT", BODY_FONT.get(lang, "Inter")))


def render_frames(page, meta: dict, total_s: float, fps: int, out_dir: Path,
                  log=print) -> list[tuple[Path, float]]:
    """Screenshot the animation. Returns [(image, seconds)] for ffmpeg's concat."""
    page.evaluate("m => window.build(m)", meta)
    frames: list[tuple[Path, float]] = []
    last_sig = None
    n = int(total_s * fps) + 1
    for f in range(n):
        sig = page.evaluate("t => window.renderAt(t)", f / fps)
        if sig.startswith("still") and sig == last_sig:
            img, d = frames[-1]
            frames[-1] = (img, d + 1 / fps)
            continue
        img = out_dir / f"f{len(frames):05d}.jpg"
        page.screenshot(path=str(img), type="jpeg", quality=90)
        frames.append((img, 1 / fps))
        last_sig = sig
    log(f"    {n} frames, {len(frames)} drawn")
    return frames
