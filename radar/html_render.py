"""Render the daily brief as a readable web page.

Markdown in a text editor is a wall of grey. This produces a page built for
actually reading: short blocks, clear hierarchy, and every technical term the
analyst used turned into something you can hover to learn.

The whole page is one self-contained file — no network, no build step. Open it
in any browser.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

CATEGORY_COLOURS = {
    "BD Macro": "#0f766e", "BD Policy": "#7c3aed", "DSE": "#b45309",
    "Banking": "#1d4ed8", "RMG/Export": "#be185d", "Energy": "#c2410c",
    "Global Macro": "#0e7490", "Global Markets": "#4338ca",
    "Commodities": "#a16207", "FX": "#047857", "Corporate": "#475569",
}


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _pct(v) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:+.2f}%"


def _cls(v) -> str:
    if not isinstance(v, (int, float)):
        return "flat"
    return "up" if v > 0 else ("down" if v < 0 else "flat")


# A sentence ends on .!? only when the character before it is a lowercase
# letter, digit, %, or closing bracket, AND whitespace plus a capital follows.
# Without the first condition "9.5%" and "U.S. Federal" get split apart.
_SENT_END = re.compile(r"""(?<=[a-z0-9%)\]"'])[.!?]+["')\]]*\s+(?=[A-Z"'(])""")


def _split_sentences(text: str) -> list[str]:
    bounds = [0] + [m.end() for m in _SENT_END.finditer(text)]
    out = []
    for i, start in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else len(text)
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
    return out


def _paras(text: str, per_para: int = 3) -> str:
    """Break long prose into paragraphs.

    A 250-word block is a wall regardless of how good the writing is. If the
    analyst supplied its own breaks we keep them; otherwise we split every few
    sentences so there is somewhere for the eye to rest.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if "\n\n" in text:
        chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    else:
        sentences = _split_sentences(text)
        if len(sentences) <= per_para + 1:
            chunks = [text]
        else:
            chunks = [" ".join(sentences[i:i + per_para])
                      for i in range(0, len(sentences), per_para)]
            # Avoid orphaning a single trailing sentence.
            if len(chunks) > 1 and len(chunks[-1].split()) < 18:
                chunks[-2] += " " + chunks.pop()
    return "".join(f"<p>{_e(c)}</p>" for c in chunks)


def _chip(category: str) -> str:
    colour = CATEGORY_COLOURS.get(category, "#475569")
    return f'<span class="chip" style="--chip:{colour}">{_e(category)}</span>'


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#fbfbfa; --surface:#fff; --ink:#12161f; --soft:#5b6577; --faint:#8b94a6;
  --line:#e6e8ec; --accent:#0f766e; --accent-soft:#f0fdfa;
  --up:#047857; --down:#be2d32; --hi:#fef9c3;
  --radius:14px;
  --sans:"Segoe UI Variable Text","Segoe UI",-apple-system,system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0e1116; --surface:#161b23; --ink:#e8ecf2; --soft:#9aa4b5; --faint:#6c7789;
    --line:#252c37; --accent:#2dd4bf; --accent-soft:#0d2b2a;
    --up:#34d399; --down:#f87171; --hi:#3f3a1a;
  }
}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
  font-size:17px; line-height:1.65; letter-spacing:-0.003em;
}
.wrap{max-width:760px;margin:0 auto;padding:32px 20px 96px}

/* ---------- header ---------- */
header{margin-bottom:28px}
.brand{font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
h1{font-size:31px;line-height:1.2;margin:6px 0 8px;letter-spacing:-0.02em}
.meta{font-size:13.5px;color:var(--faint)}

/* ---------- generic blocks ---------- */
section{margin:38px 0}
h2{
  font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
  color:var(--faint);margin:0 0 16px;padding-bottom:9px;border-bottom:1px solid var(--line)
}
h3{font-size:18.5px;line-height:1.35;margin:0 0 8px;letter-spacing:-0.01em}
p{margin:0 0 12px}
a{color:var(--accent)}
.card{
  background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:20px 22px;margin-bottom:14px
}

/* ---------- hero / 60-second read ---------- */
.hero{
  background:var(--accent-soft);border:1px solid var(--accent);border-radius:var(--radius);
  padding:24px 24px 20px;margin-bottom:14px
}
.hero .hook{font-size:22px;font-weight:700;line-height:1.32;margin:0 0 16px;letter-spacing:-0.02em}
.flash{list-style:none;margin:0;padding:0;counter-reset:f}
.flash li{
  counter-increment:f;position:relative;padding:7px 0 7px 34px;
  border-top:1px solid color-mix(in srgb,var(--accent) 22%,transparent);font-size:15.5px;line-height:1.5
}
.flash li::before{
  content:counter(f);position:absolute;left:0;top:9px;width:22px;height:22px;
  background:var(--accent);color:#fff;border-radius:50%;font-size:12px;font-weight:700;
  display:grid;place-items:center
}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.stat{
  background:var(--surface);border:1px solid var(--line);border-radius:9px;
  padding:8px 12px;font-size:13.5px
}
.stat b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);font-weight:700}

/* ---------- stories ---------- */
.story{display:grid;grid-template-columns:34px 1fr;gap:14px}
.rank{
  font-size:15px;font-weight:700;color:var(--faint);border:1px solid var(--line);
  border-radius:8px;height:30px;display:grid;place-items:center
}
.plain{
  background:var(--accent-soft);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;
  padding:10px 14px;margin:0 0 12px;font-size:15.5px;line-height:1.55
}
.plain b{
  display:block;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--accent);margin-bottom:3px
}
.why{color:var(--soft);font-size:16px}
.foot{
  margin-top:12px;padding-top:10px;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--faint);display:flex;flex-wrap:wrap;gap:8px;align-items:center
}
.chip{
  background:color-mix(in srgb,var(--chip) 13%,transparent);color:var(--chip);
  border:1px solid color-mix(in srgb,var(--chip) 30%,transparent);
  border-radius:20px;padding:2px 10px;font-size:11.5px;font-weight:600;white-space:nowrap
}
.tick{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--soft)}

/* ---------- connections ---------- */
.chain{
  font-size:15.5px;line-height:1.7;background:var(--bg);border:1px dashed var(--line);
  border-radius:10px;padding:14px 16px;margin:10px 0
}
.sowhat{border-left:3px solid var(--accent);padding-left:14px;margin-top:12px}
.sowhat b{color:var(--accent);font-size:11px;letter-spacing:.1em;text-transform:uppercase;display:block;margin-bottom:3px}

/* ---------- teaching ---------- */
.lesson{background:linear-gradient(180deg,var(--accent-soft),transparent 70%);border:1px solid var(--accent)}
.lesson .tag{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.quiz{
  margin-top:14px;padding:12px 14px;background:var(--surface);
  border:1px solid var(--line);border-radius:10px;font-size:15px
}
.quiz b{color:var(--accent);font-size:11px;letter-spacing:.1em;text-transform:uppercase;display:block;margin-bottom:4px}

/* ---------- jargon ---------- */
.terms{display:grid;gap:12px}
@media(min-width:620px){.terms{grid-template-columns:1fr 1fr}}
.term{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.term h4{margin:0 0 6px;font-size:16px;color:var(--accent)}
.term p{font-size:14.5px;line-height:1.55;color:var(--soft);margin:0 0 8px}
.term .stick{
  font-size:13.5px;background:var(--hi);color:var(--ink);
  border-radius:7px;padding:7px 10px;display:block
}
.jargon{
  border-bottom:2px dotted var(--accent);cursor:help;position:relative;
  background:color-mix(in srgb,var(--accent) 7%,transparent)
}
.jargon:hover::after{
  content:attr(data-def);position:absolute;left:0;bottom:calc(100% + 8px);z-index:20;
  width:min(320px,78vw);background:var(--ink);color:var(--bg);font-size:13.5px;
  line-height:1.5;font-weight:400;padding:10px 12px;border-radius:9px;
  box-shadow:0 8px 26px rgba(0,0,0,.28);letter-spacing:0
}

/* ---------- tables ---------- */
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14.5px;min-width:420px}
th{
  text-align:left;font-size:11px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--faint);padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap
}
td{padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:var(--up);font-weight:600}
.down{color:var(--down);font-weight:600}
.flat{color:var(--faint)}

/* ---------- predictions ---------- */
.pred{display:flex;gap:12px;padding:13px 0;border-bottom:1px solid var(--line)}
.pred:last-child{border-bottom:none}
.conf{
  flex:none;width:46px;height:46px;border-radius:50%;display:grid;place-items:center;
  font-size:13px;font-weight:700;background:var(--accent-soft);color:var(--accent);
  border:2px solid var(--accent)
}
.pred .body{flex:1;min-width:0}
.pred .body p{margin:4px 0 0;font-size:14.5px;color:var(--soft)}
.badge{font-size:11.5px;color:var(--faint)}
.res{display:flex;gap:10px;padding:11px 0;border-bottom:1px solid var(--line);font-size:15px}
.res:last-child{border-bottom:none}

/* ---------- post ---------- */
.post{
  background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:20px 22px;white-space:pre-wrap;font-size:16px;line-height:1.7
}
.copy{
  margin-top:12px;background:var(--accent);color:#fff;border:none;border-radius:9px;
  padding:9px 16px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit
}
.copy:active{transform:translateY(1px)}

details{margin-top:12px}
summary{cursor:pointer;color:var(--accent);font-size:14.5px;font-weight:600;padding:6px 0}
footer{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);font-size:12.5px;color:var(--faint)}
@media print{
  body{background:#fff;font-size:11pt}
  .card,.hero,.term{break-inside:avoid}
  .copy{display:none}
}
"""

JS = """
// Turn every term in the decoder into a hoverable definition wherever it
// appears in the prose. Walks text nodes so we never break existing markup.
(function(){
  var terms = window.__JARGON__ || [];
  if(!terms.length) return;
  terms.sort(function(a,b){return b.term.length - a.term.length;});
  var used = {};
  terms.forEach(function(t){ used[t.term.toLowerCase()] = 0; });

  function esc(s){ return s.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&'); }

  document.querySelectorAll('.prose').forEach(function(root){
    terms.forEach(function(t){
      var key = t.term.toLowerCase();
      if(used[key] >= 2) return;                     // avoid peppering the page
      var re = new RegExp('\\\\b(' + esc(t.term) + ')\\\\b','i');
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      var nodes = [], n;
      while((n = walker.nextNode())) nodes.push(n);
      for(var i=0;i<nodes.length;i++){
        var node = nodes[i];
        if(node.parentNode.closest('.jargon')) continue;
        var m = node.nodeValue.match(re);
        if(!m) continue;
        var idx = m.index;
        var after = node.splitText(idx);
        after.nodeValue = after.nodeValue.substring(m[0].length);
        var span = document.createElement('span');
        span.className = 'jargon';
        span.setAttribute('data-def', t.plain);
        span.textContent = m[0];
        node.parentNode.insertBefore(span, after);
        used[key]++;
        break;
      }
    });
  });

  var btn = document.getElementById('copyPost');
  if(btn){
    btn.addEventListener('click', function(){
      navigator.clipboard.writeText(window.__POST__ || '').then(function(){
        var old = btn.textContent;
        btn.textContent = 'Copied';
        setTimeout(function(){ btn.textContent = old; }, 1600);
      });
    });
  }
})();
"""


def _stories(analysis: dict) -> str:
    out = []
    for s in analysis.get("top_stories", []):
        tickers = s.get("tickers") or []
        tick = (f'<span class="tick">{_e(" ".join(tickers[:4]))}</span>'
                if tickers else "")
        src = ", ".join(s.get("sources") or [])
        link = (f'<a href="{_e(s.get("url"))}" target="_blank" rel="noopener">read the story →</a>'
                if s.get("url") else "")
        plain = ""
        if s.get("plain_english"):
            plain = (f'<div class="plain"><b>In plain English</b>'
                     f'{_e(s["plain_english"])}</div>')
        impact = {"direct": "hits Bangladesh directly",
                  "indirect": "reaches Bangladesh indirectly",
                  "contextual": "background context"}.get(s.get("bd_impact", ""), "")
        out.append(f"""
<article class="card story">
  <div class="rank">{_e(s.get('rank'))}</div>
  <div>
    <h3>{_e(s.get('headline'))}</h3>
    {plain}
    <p class="why prose">{_e(s.get('why_it_matters'))}</p>
    <div class="foot">
      {_chip(s.get('category', ''))}{tick}
      <span>{_e(impact)}</span>
      <span>{_e(src)}</span>
      {link}
    </div>
  </div>
</article>""")
    return "".join(out)


def _connections(analysis: dict) -> str:
    out = []
    for c in analysis.get("connections", []):
        ranks = "".join(f'<span class="chip" style="--chip:#475569">#{_e(r)}</span>'
                        for r in c.get("story_ranks", []))
        out.append(f"""
<article class="card">
  <h3>{_e(c.get('title'))}</h3>
  <div class="foot" style="margin:0 0 10px;padding:0;border:none">
    {ranks}<span>{_e(c.get('strength', ''))} link</span>
  </div>
  <div class="chain prose">{_e(c.get('chain'))}</div>
  <div class="sowhat prose"><b>So what</b>{_e(c.get('so_what'))}</div>
</article>""")
    return "".join(out)


def _teaching(analysis: dict) -> str:
    t = analysis.get("teaching_note") or {}
    if not t.get("concept"):
        return ""
    quiz = ""
    if t.get("test_yourself"):
        quiz = (f'<div class="quiz"><b>Test yourself</b>'
                f'{_e(t["test_yourself"])}</div>')
    return f"""
<section>
  <h2>Today's lesson</h2>
  <article class="card lesson">
    <div class="tag">Concept</div>
    <h3>{_e(t.get('concept'))}</h3>
    <div class="prose">{_paras(t.get('explanation'))}</div>
    {quiz}
  </article>
</section>"""


def _jargon(analysis: dict) -> str:
    terms = analysis.get("jargon_decoder") or []
    if not terms:
        return ""
    cards = []
    for t in terms:
        stick = (f'<span class="stick">{_e(t["remember_this"])}</span>'
                 if t.get("remember_this") else "")
        why = f'<p>{_e(t["why_today"])}</p>' if t.get("why_today") else ""
        cards.append(f"""
<div class="term">
  <h4>{_e(t.get('term'))}</h4>
  <p>{_e(t.get('plain'))}</p>
  {why}{stick}
</div>""")
    return f"""
<section>
  <h2>Jargon decoder</h2>
  <p style="font-size:14.5px;color:var(--faint);margin:-4px 0 16px">
    These terms appear in today's brief. Hover any dotted word above to see its
    meaning without scrolling back.
  </p>
  <div class="terms">{''.join(cards)}</div>
</section>"""


def _dse_tables(dse: dict) -> str:
    if not dse.get("available"):
        return (f'<div class="card"><p>DSE data was unavailable today: '
                f'{_e(dse.get("reason", "unknown"))}</p></div>')

    sectors = "".join(f"""
<tr><td>{_e(s['sector'])}</td>
<td class="num {_cls(s['weighted_pct'])}">{_pct(s['weighted_pct'])}</td>
<td class="num">{s['turnover_share_pct']:.1f}%</td>
<td class="num">{s['advancers']}/{s['decliners']}</td>
<td class="num">{_e(s['median_pe']) if s.get('median_pe') else '—'}</td></tr>"""
        for s in dse.get("sectors", [])[:10])

    chips = "".join(f"""
<tr><td><b>{_e(c['code'])}</b></td>
<td style="color:var(--faint)">{_e(c['sector'])}</td>
<td class="num">{c['close']:,}</td>
<td class="num {_cls(c['pct'])}">{_pct(c['pct'])}</td>
<td class="num">{c['turnover_mn']:,.0f}</td></tr>"""
        for c in dse.get("blue_chips", [])[:12])

    return f"""
<div class="card">
  <h3 style="margin-bottom:14px">Sectors, ranked by money traded</h3>
  <div class="scroll"><table>
    <thead><tr><th>Sector</th><th class="num">Move</th><th class="num">Share of turnover</th>
    <th class="num">Up/Down</th><th class="num">Median P/E</th></tr></thead>
    <tbody>{sectors}</tbody>
  </table></div>
  <details>
    <summary>Show blue-chip stocks</summary>
    <div class="scroll" style="margin-top:12px"><table>
      <thead><tr><th>Code</th><th>Sector</th><th class="num">Close (Tk)</th>
      <th class="num">Move</th><th class="num">Turnover (Tk mn)</th></tr></thead>
      <tbody>{chips}</tbody>
    </table></div>
  </details>
</div>"""


def _global_table(mkt: dict) -> str:
    if not mkt.get("available"):
        return ""
    rows = "".join(f"""
<tr><td>{_e(r['name'])}</td>
<td class="num">{r['last']:,}</td>
<td class="num {_cls(r['change_pct_1d'])}">{_pct(r['change_pct_1d'])}</td>
<td class="num {_cls(r['change_pct_1w'])}">{_pct(r['change_pct_1w'])}</td>
<td class="num {_cls(r['change_pct_1m'])}">{_pct(r['change_pct_1m'])}</td></tr>"""
        for r in mkt.get("instruments", []))
    return f"""
<div class="card">
  <h3 style="margin-bottom:14px">Global markets</h3>
  <div class="scroll"><table>
    <thead><tr><th>Instrument</th><th class="num">Last</th><th class="num">1 day</th>
    <th class="num">1 week</th><th class="num">1 month</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</div>"""


def _predictions(analysis: dict, scorecard: dict) -> str:
    blocks = []

    res = analysis.get("resolutions") or []
    if res:
        icon = {"correct": "✅", "wrong": "❌", "partial": "🟡", "unclear": "⚪"}
        items = "".join(f"""
<div class="res"><div>{icon.get(r.get('status'), '•')}</div>
<div><b>{_e(r.get('status', '').upper())}</b> — {_e(r.get('resolution'))}
{f'<p style="margin:5px 0 0;font-size:14px;color:var(--soft)">Lesson: {_e(r["lesson"])}</p>' if r.get('lesson') else ''}
</div></div>""" for r in res)
        blocks.append(f'<div class="card"><h3>How yesterday\'s calls turned out</h3>{items}</div>')

    preds = analysis.get("predictions") or []
    if preds:
        items = "".join(f"""
<div class="pred">
  <div class="conf">{_e(p.get('confidence', '?'))}%</div>
  <div class="body">
    <b>{_e(p.get('statement'))}</b>
    <p>{_e(p.get('rationale'))}</p>
    <div class="badge">judged in {_e(p.get('horizon_days', '?'))} days · {_e(p.get('category', ''))}</div>
  </div>
</div>""" for p in preds)
        blocks.append(f'<div class="card"><h3>Calls made today</h3>{items}</div>')

    if scorecard.get("scored"):
        blocks.append(f"""
<div class="card" style="text-align:center">
  <div style="font-size:34px;font-weight:700;color:var(--accent)">{scorecard['hit_rate_pct']}%</div>
  <div style="font-size:13.5px;color:var(--faint)">
    hit rate · {scorecard['correct']} correct, {scorecard['wrong']} wrong,
    {scorecard['partial']} partial, {scorecard['open']} still open
  </div>
</div>""")
    return "".join(blocks)


def render(day: str, analysis: dict, dse: dict, mkt: dict,
           news: dict, scorecard: dict, engine_name: str,
           social_text: str = "", brand: str = "60 SECOND FINANCE") -> str:
    sp = analysis.get("social_post", {}) or {}
    stories = analysis.get("top_stories", []) or []

    flash = "".join(f"<li>{_e(s.get('plain_english') or s.get('headline'))}</li>"
                    for s in stories[:5])

    stats = []
    if dse.get("available"):
        stats.append(f'<div class="stat"><b>DSE</b>'
                     f'<span class="{_cls(dse["turnover_weighted_move_pct"])}">'
                     f'{_pct(dse["turnover_weighted_move_pct"])}</span> · '
                     f'Tk {dse["total_turnover_crore_bdt"]:,.0f} cr</div>')
        stats.append(f'<div class="stat"><b>Breadth</b>{dse["advancers"]} up / '
                     f'{dse["decliners"]} down</div>')
    for m in (mkt.get("biggest_movers_1d") or [])[:3]:
        stats.append(f'<div class="stat"><b>{_e(m["name"])}</b>'
                     f'<span class="{_cls(m["change_pct_1d"])}">'
                     f'{_pct(m["change_pct_1d"])}</span></div>')

    post_block = ""
    if social_text:
        post_block = f"""
<section>
  <h2>Ready to post</h2>
  <div class="post">{_e(social_text.strip())}</div>
  <button class="copy" id="copyPost">Copy post</button>
</section>"""

    ok_sources = sum(1 for r in news["source_report"] if r["ok"] and r["count"])
    jargon_json = json.dumps(
        [{"term": t.get("term", ""), "plain": t.get("plain", "")}
         for t in (analysis.get("jargon_decoder") or []) if t.get("term")],
        ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance Radar — {_e(day)}</title>
<style>{CSS}</style>
</head><body><div class="wrap">

<header>
  <div class="brand">{_e(brand)}</div>
  <h1>{_e(datetime.strptime(day, '%Y-%m-%d').strftime('%A, %d %B %Y'))}</h1>
  <div class="meta">{news['counts']['unique']} stories from {ok_sources} sources ·
    {news['counts']['bd']} Bangladesh · {news['counts']['global']} global ·
    analysed by {_e(engine_name)}</div>
</header>

<div class="hero">
  <p class="hook">{_e(sp.get('hook', 'Today in Bangladeshi and global finance'))}</p>
  <ol class="flash">{flash}</ol>
  <div class="stats">{''.join(stats)}</div>
</div>

<section>
  <h2>The day in one read</h2>
  <div class="card"><div class="prose">{_paras(analysis.get('scenario', ''))}</div></div>
</section>

{_teaching(analysis)}

<section>
  <h2>The ten stories that mattered</h2>
  {_stories(analysis)}
</section>

<section>
  <h2>How they connect</h2>
  {_connections(analysis)}
</section>

{_jargon(analysis)}

<section>
  <h2>The numbers</h2>
  {_dse_tables(dse)}
  {_global_table(mkt)}
</section>

<section>
  <h2>Predictions</h2>
  {_predictions(analysis, scorecard)}
</section>

{post_block}

<footer>
  Finance Radar · generated {_e(datetime.now().strftime('%d %b %Y, %H:%M'))} ·
  Not investment advice. Every figure should be checked against the original
  source before you act on it.
</footer>

</div>
<script>
window.__JARGON__ = {jargon_json};
window.__POST__ = {json.dumps(social_text, ensure_ascii=False)};
{JS}
</script>
</body></html>"""
