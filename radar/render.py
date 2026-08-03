"""Render the analysis into the daily brief and the social post."""

from __future__ import annotations

from datetime import date


def _pct(v):
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "n/a"


def brief_markdown(day: str, analysis: dict, dse: dict, mkt: dict,
                   news: dict, scorecard: dict, engine_name: str) -> str:
    L: list[str] = []
    add = L.append

    add(f"# Finance Radar — {day}")
    add("")
    add(f"*{news['counts']['unique']} unique stories from "
        f"{sum(1 for r in news['source_report'] if r['ok'])} live sources "
        f"({news['counts']['bd']} Bangladesh, {news['counts']['global']} global, "
        f"{news['counts']['macro']} central-bank). Analysis by `{engine_name}`.*")
    add("")

    # -------------------------------------------------- 60-second read (TL;DR)
    # Deliberately first and deliberately short: if you only have a minute,
    # everything that actually changed today is in this block.
    sp_top = analysis.get("social_post", {}) or {}
    stories = analysis.get("top_stories", []) or []
    add("## ⚡ 60-second read")
    add("")
    if sp_top.get("hook"):
        add(f"**{sp_top['hook']}**")
        add("")
    for s in stories[:5]:
        tick = ""
        if s.get("tickers"):
            tick = f" `{' '.join(s['tickers'][:3])}`"
        add(f"{s.get('rank')}. {s.get('headline', '')}{tick}")
    add("")

    facts = []
    if dse.get("available"):
        facts.append(f"**DSE** {_pct(dse['turnover_weighted_move_pct'])} · "
                     f"Tk {dse['total_turnover_crore_bdt']:,} cr turnover · "
                     f"{dse['advancers']}↑/{dse['decliners']}↓ · {dse['breadth_verdict']}")
        top_sec = (dse.get("sectors") or [{}])[0]
        if top_sec.get("sector"):
            facts.append(f"**Busiest sector** {top_sec['sector']} "
                         f"({_pct(top_sec['weighted_pct'])}, "
                         f"{top_sec['turnover_share_pct']:.0f}% of turnover)")
    if mkt.get("available"):
        movers = ", ".join(f"{m['name']} {_pct(m['change_pct_1d'])}"
                           for m in mkt.get("biggest_movers_1d", [])[:4])
        if movers:
            facts.append(f"**Global movers** {movers}")
    for f in facts:
        add(f"- {f}")
    if facts:
        add("")

    if sp_top.get("takeaway"):
        add(f"> {sp_top['takeaway']}")
        add("")
    add("---")
    add("")

    # ---------------------------------------------------------- the scenario
    add("## The day in one read")
    add("")
    add(analysis.get("scenario", "_No scenario produced._"))
    add("")

    # ------------------------------------------------------------ top stories
    add("## Top 10 stories")
    add("")
    for s in analysis.get("top_stories", []):
        tickers = s.get("tickers") or []
        tick = f" `{' '.join(tickers)}`" if tickers else ""
        impact = s.get("bd_impact", "")
        badge = {"direct": "🇧🇩 direct", "indirect": "🇧🇩 indirect",
                 "contextual": "context"}.get(impact, impact)
        add(f"**{s.get('rank')}. {s.get('headline', '')}**{tick}")
        add("")
        add(f"{s.get('why_it_matters', '')}")
        add("")
        meta = [s.get("category", ""), badge, f"confidence: {s.get('confidence', '?')}"]
        meta = [m for m in meta if m]
        src = ", ".join(s.get("sources") or [])
        url = s.get("url", "")
        line = " · ".join(meta)
        if src:
            line += f" · {src}"
        if url:
            line += f" · [read]({url})"
        add(f"<sub>{line}</sub>")
        add("")

    # ----------------------------------------------------------- connections
    add("## How these connect")
    add("")
    for c in analysis.get("connections", []):
        ranks = ", ".join(f"#{r}" for r in c.get("story_ranks", []))
        add(f"### {c.get('title', 'Connection')}")
        add(f"<sub>links {ranks} · {c.get('strength', '')}</sub>")
        add("")
        add(f"{c.get('chain', '')}")
        add("")
        add(f"**So what:** {c.get('so_what', '')}")
        add("")

    # --------------------------------------------------------- market tables
    mr = analysis.get("market_read", {})
    add("## Market read")
    add("")
    if mr.get("dse"):
        add(f"**Dhaka.** {mr['dse']}")
        add("")
    if mr.get("global"):
        add(f"**Global.** {mr['global']}")
        add("")
    if mr.get("transmission"):
        add(f"**Main transmission channel.** {mr['transmission']}")
        add("")

    if dse.get("available"):
        add("### DSE session")
        add("")
        add(f"| Metric | Value |")
        add(f"|---|---|")
        add(f"| Turnover | Tk {dse['total_turnover_crore_bdt']:,} crore |")
        add(f"| Advance / Decline | {dse['advancers']} / {dse['decliners']} "
            f"(ratio {dse['advance_decline_ratio']}) |")
        add(f"| Turnover-weighted move | {_pct(dse['turnover_weighted_move_pct'])} |")
        add(f"| Breadth | {dse['breadth_verdict']} |")
        add("")
        add("**Sectors by turnover**")
        add("")
        add("| Sector | Move | Share of turnover | Adv/Dec | Median P/E |")
        add("|---|---:|---:|:---:|---:|")
        for s in dse.get("sectors", [])[:10]:
            pe = s.get("median_pe")
            add(f"| {s['sector']} | {_pct(s['weighted_pct'])} | "
                f"{s['turnover_share_pct']:.1f}% | {s['advancers']}/{s['decliners']} | "
                f"{pe if pe else '—'} |")
        add("")
        add("**Blue chips**")
        add("")
        add("| Code | Sector | Close (Tk) | Move | Turnover (Tk mn) |")
        add("|---|---|---:|---:|---:|")
        for c in dse.get("blue_chips", [])[:12]:
            add(f"| {c['code']} | {c['sector']} | {c['close']:,} | "
                f"{_pct(c['pct'])} | {c['turnover_mn']:,.0f} |")
        add("")
    else:
        add(f"> DSE data was unavailable: {dse.get('reason', 'unknown')}")
        add("")

    if mkt.get("available"):
        add("### Global movers")
        add("")
        add("| Instrument | Last | 1d | 1w | 1m |")
        add("|---|---:|---:|---:|---:|")
        for r in mkt.get("biggest_movers_1d", []):
            add(f"| {r['name']} | {r['last']:,} | {_pct(r['change_pct_1d'])} | "
                f"{_pct(r['change_pct_1w'])} | {_pct(r['change_pct_1m'])} |")
        add("")

    # ----------------------------------------------------------- predictions
    res = analysis.get("resolutions") or []
    if res:
        add("## Scoring earlier calls")
        add("")
        icon = {"correct": "✅", "wrong": "❌", "partial": "🟡", "unclear": "⚪"}
        for r in res:
            add(f"- {icon.get(r.get('status'), '•')} **{r.get('status', '').upper()}** "
                f"(#{r.get('id')}) — {r.get('resolution', '')}")
            if r.get("lesson"):
                add(f"  <br><sub>Lesson: {r['lesson']}</sub>")
        add("")

    preds = analysis.get("predictions") or []
    if preds:
        add("## New calls")
        add("")
        for p in preds:
            add(f"- **{p.get('statement', '')}**  ")
            add(f"  <sub>{p.get('confidence', '?')}% confidence · "
                f"{p.get('horizon_days', '?')} days · {p.get('category', '')}</sub>  ")
            if p.get("rationale"):
                add(f"  {p['rationale']}")
        add("")

    if scorecard.get("scored"):
        add(f"> **Track record:** {scorecard['correct']} correct · "
            f"{scorecard['wrong']} wrong · {scorecard['partial']} partial · "
            f"**{scorecard['hit_rate_pct']}% hit rate** over "
            f"{scorecard['scored']} scored calls ({scorecard['open']} open).")
        add("")

    # ---------------------------------------------------------- social post
    sp = analysis.get("social_post", {})
    if sp:
        add("## Today's post")
        add("")
        add("```")
        add(sp.get("hook", ""))
        add("")
        add(sp.get("body", ""))
        add("")
        if sp.get("takeaway"):
            add(sp["takeaway"])
        if sp.get("hashtags"):
            add("")
            add(" ".join(f"#{h.lstrip('#')}" for h in sp["hashtags"]))
        add("```")
        add("")

    # -------------------------------------------------------------- appendix
    failed = [r for r in news["source_report"] if not r["ok"] or r["count"] == 0]
    if failed:
        add("<details><summary>Sources that returned nothing</summary>")
        add("")
        for r in failed:
            add(f"- {r['source']}{' — ' + r['error'] if r.get('error') else ''}")
        add("")
        add("</details>")
        add("")

    return "\n".join(L)


def social_text(analysis: dict, day: str) -> str:
    """The post, ready to copy into Facebook / Instagram / LinkedIn."""
    sp = analysis.get("social_post", {})
    parts = [sp.get("hook", ""), "", sp.get("body", "")]
    if sp.get("takeaway"):
        parts += ["", sp["takeaway"]]
    if sp.get("hashtags"):
        parts += ["", " ".join(f"#{h.lstrip('#')}" for h in sp["hashtags"])]
    return "\n".join(p for p in parts if p is not None).strip() + "\n"
