"""Build the analyst's briefing packet and parse what comes back.

The packet is deliberately ordered the way a human analyst would read it:
what the market did, then what happened in the world, then what we said
before and whether it held up.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .engine import Engine, extract_json


def _fmt_dse(dse: dict) -> str:
    if not dse.get("available"):
        return (f"DSE data unavailable today ({dse.get('reason', 'unknown')}). "
                "Do not invent Bangladeshi market levels — say the data was missing.\n")

    out = [
        "### Dhaka Stock Exchange — latest session",
        f"- Instruments traded: {dse['instruments_traded']} of {dse['instruments_listed']} listed",
        f"- Advancers {dse['advancers']} / Decliners {dse['decliners']} / Unchanged {dse['unchanged']}"
        f"  (A/D ratio {dse['advance_decline_ratio']})",
        f"- Total turnover: Tk {dse['total_turnover_crore_bdt']:,} crore",
        f"- Turnover-weighted market move: {dse['turnover_weighted_move_pct']:+.2f}%",
        f"- Breadth verdict: {dse['breadth_verdict']}",
        "",
        "Top gainers: " + ", ".join(
            f"{g['code']} {g['pct']:+.2f}% (Tk {g['turnover_mn']:.0f}mn, {g['sector']})"
            for g in dse["top_gainers"][:6]),
        "Top losers: " + ", ".join(
            f"{l['code']} {l['pct']:+.2f}% (Tk {l['turnover_mn']:.0f}mn, {l['sector']})"
            for l in dse["top_losers"][:6]),
        "Most active by turnover: " + ", ".join(
            f"{m['code']} Tk {m['turnover_mn']:.0f}mn ({m['pct']:+.2f}%)"
            for m in dse["most_active_by_turnover"][:6]),
        "",
        "Blue chips (largest absolute moves first):",
    ]
    for c in dse.get("blue_chips", [])[:14]:
        out.append(f"  {c['code']:<12} {c['pct']:+6.2f}%  close Tk {c['close']:,}  "
                   f"turnover Tk {c['turnover_mn']:.0f}mn  [{c['sector']}]")

    out.append("")
    out.append("Sector performance (turnover-weighted):")
    for s in dse.get("sectors", [])[:14]:
        pe = f"  median P/E {s['median_pe']}" if s.get("median_pe") else ""
        out.append(f"  {s['sector']:<24} {s['weighted_pct']:+6.2f}%  "
                   f"{s['turnover_share_pct']:>5.1f}% of turnover  "
                   f"adv {s['advancers']}/dec {s['decliners']}{pe}")
    return "\n".join(out) + "\n"


def _fmt_markets(mkt: dict) -> str:
    if not mkt.get("available"):
        return f"Global market data unavailable ({mkt.get('reason', 'unknown')}).\n"
    out = ["### Global markets"]
    for group in ("FX", "Rates", "Commodity", "Equity"):
        rows = mkt["by_group"].get(group) or []
        if not rows:
            continue
        out.append(f"\n{group}:")
        for r in rows:
            d1 = f"{r['change_pct_1d']:+.2f}%" if r["change_pct_1d"] is not None else "  n/a"
            d5 = f"{r['change_pct_1w']:+.2f}%" if r["change_pct_1w"] is not None else "  n/a"
            d20 = f"{r['change_pct_1m']:+.2f}%" if r["change_pct_1m"] is not None else "  n/a"
            out.append(f"  {r['name']:<20} {r['last']:>12,}   1d {d1:>8}  1w {d5:>8}  1m {d20:>8}"
                       f"   — {r['matters_because']}")
    return "\n".join(out) + "\n"


def _fmt_news(articles: list[dict], limit: int) -> str:
    out = ["### Today's news pool",
           f"({len(articles)} unique stories after deduplication; "
           f"showing the {min(limit, len(articles))} highest-ranked)\n"]
    for i, a in enumerate(articles[:limit], 1):
        scope = {"bd": "BD", "global": "GLOBAL", "macro": "MACRO"}.get(a["scope"], a["scope"])
        out.append(f"[{i}] ({scope}) {a['title']}")
        out.append(f"    source: {a['source_name']} | {a['published'][:16]}")
        if a.get("summary"):
            out.append(f"    {a['summary'][:280]}")
        out.append(f"    {a['url']}")
        out.append("")
    return "\n".join(out)


def _fmt_memory(store, today: str, lookback_days: int) -> str:
    out = ["### Your memory — what you have said before\n"]

    runs = store.recent_runs(days=lookback_days, before=today)
    if not runs:
        out.append("This is your first run. You have no prior context yet; say so "
                   "naturally rather than pretending to remember earlier days.\n")
    else:
        out.append(f"Your daily conclusions for the last {len(runs)} run(s), newest first:\n")
        for r in runs:
            out.append(f"**{r['run_date']}**")
            scenario = (r["scenario"] or "").strip()
            out.append(f"  Scenario: {scenario[:700]}")
            try:
                tops = json.loads(r["top_stories"] or "[]")[:4]
                if tops:
                    out.append("  Lead stories: " + " | ".join(
                        t.get("headline", "")[:90] for t in tops))
            except Exception:
                pass
            out.append("")

    open_preds = store.open_predictions()
    if open_preds:
        out.append(f"\n### Open predictions ({len(open_preds)}) — judge any that can now be settled\n")
        for p in open_preds:
            due = "DUE NOW" if p["resolve_by"] <= today else f"due {p['resolve_by']}"
            out.append(f"  id={p['id']} | made {p['made_on']} | {due} | "
                       f"confidence {p['confidence']}%")
            out.append(f"    \"{p['statement']}\"")
            if p.get("rationale"):
                out.append(f"    rationale was: {p['rationale'][:200]}")
        out.append("\nResolve every prediction whose evidence is now clear — especially "
                   "those marked DUE NOW. Leave genuinely undecidable ones open by "
                   "omitting them. Be strict: mark it wrong if it was wrong.\n")
    else:
        out.append("\nNo open predictions to judge.\n")

    card = store.scorecard()
    if card["scored"]:
        out.append(f"Your track record so far: {card['correct']} correct, "
                   f"{card['wrong']} wrong, {card['partial']} partial "
                   f"({card['hit_rate_pct']}% hit rate over {card['scored']} scored calls). "
                   f"{card['open']} still open.")
        if card["hit_rate_pct"] is not None and card["hit_rate_pct"] < 45:
            out.append("Your hit rate is poor. Be more conservative and more specific.")

    themes = store.recurring_themes()
    if themes:
        out.append("\nRecurring themes in the last 30 days: " + ", ".join(
            f"{t['category']} ({t['c']}x, last {t['last_seen']})" for t in themes))
    return "\n".join(out) + "\n"


def build_packet(store, news: dict, dse: dict, mkt: dict,
                 today: str, news_limit: int = 70, lookback_days: int = 7) -> str:
    return "\n\n".join([
        f"# Daily briefing packet — {today}",
        _fmt_memory(store, today, lookback_days),
        _fmt_dse(dse),
        _fmt_markets(mkt),
        _fmt_news(news.get("articles", []), news_limit),
        ("### Your task\n"
         "Produce today's note as a single JSON object exactly matching the schema "
         "in your instructions. Rank the ten stories by financial consequence for "
         "Bangladesh. Draw the connections between them. Judge your open "
         "predictions honestly, make new ones you could lose, and write the "
         "social post for a smart non-expert.\n\n"
         "Output the JSON object only."),
    ])


REQUIRED = ("top_stories", "connections", "scenario", "social_post")


def analyse(engine: Engine, system_prompt: str, packet: str) -> tuple[dict, str]:
    """Run the engine and validate the shape of what comes back."""
    raw = engine.run(system_prompt, packet)
    data = extract_json(raw)

    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"analysis missing required keys: {missing}")

    data.setdefault("predictions", [])
    data.setdefault("resolutions", [])
    data.setdefault("market_read", {})
    data.setdefault("jargon_decoder", [])
    data.setdefault("teaching_note", {})

    if not isinstance(data["top_stories"], list) or not data["top_stories"]:
        raise ValueError("top_stories is empty")

    for i, story in enumerate(data["top_stories"], 1):
        story.setdefault("rank", i)
        story.setdefault("tickers", [])
        story.setdefault("sources", [])
    return data, raw


def load_system_prompt(path: Path) -> str:
    return Path(path).read_text(encoding="utf8")
