"""Build the archive dashboard: every day in one searchable, visual page.

Output is a single self-contained `data/dashboard.html`. All data is embedded in
the page, deliberately — a browser opening a `file://` page is not allowed to
fetch a sibling JSON file, so embedding is the only thing that works without
running a web server.

Colour note. Market moves use a blue-to-red diverging scale rather than the
green/red that finance conventionally uses. Red/green is the single most common
form of colour blindness, and in a calendar heatmap colour is the only encoding
present. The blue/red pair measures ΔE 21.6 under protanopia simulation against
green/red's near-zero, so it is legible to everyone. Every cell also carries its
number in the tooltip and in the table view, so colour never carries meaning
alone.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

# --- Validated palette (see references/palette.md; re-run validate_palette.js
# --- if you change any of these).
CATEGORICAL_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                     "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CATEGORICAL_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500",
                    "#d55181", "#008300", "#9085e9", "#e66767"]

# Diverging arms: blue = up, red = down, neutral gray = flat.
DIVERGING = {
    "light": {
        "pos": ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"],
        "neg": ["#fbd9d9", "#f5abab", "#ea7676", "#e34948", "#a82c2b"],
        "zero": "#f0efec",
    },
    "dark": {
        "pos": ["#0d366b", "#184f95", "#256abf", "#3987e5", "#86b6ef"],
        "neg": ["#5c1f1f", "#8f2f2f", "#c03c3c", "#e66767", "#f0a0a0"],
        "zero": "#383835",
    },
}


def _story_categories(runs: list[dict]) -> list[str]:
    """Fixed category order, most common first. Colour follows the entity."""
    counter: Counter = Counter()
    for r in runs:
        for s in json.loads(r["top_stories"] or "[]"):
            if s.get("category"):
                counter[s["category"]] += 1
    return [c for c, _ in counter.most_common()]


def build_payload(store, brief_dir: Path) -> dict:
    runs = store.recent_runs(days=3650)
    runs.sort(key=lambda r: r["run_date"])

    order = _story_categories(runs)
    days = []

    for r in runs:
        try:
            snapshot = json.loads(r["market_snapshot"] or "{}")
        except Exception:
            snapshot = {}
        dse = snapshot.get("dse") or {}
        glob = snapshot.get("global") or {}
        fx = snapshot.get("fx_bd") or {}
        stories = json.loads(r["top_stories"] or "[]")
        connections = json.loads(r["connections"] or "[]")
        social = json.loads(r["social_post"] or "{}")

        has_html = (brief_dir / f"{r['run_date']}.html").exists()

        day = {
            "date": r["run_date"],
            "hook": social.get("hook", ""),
            "takeaway": social.get("takeaway", ""),
            "scenario": r["scenario"] or "",
            "story_count": r["headline_count"],
            "brief": f"briefs/{r['run_date']}.html" if has_html else "",
            "card": f"cards/{r['run_date']}.png",
            "stories": [
                {
                    "rank": s.get("rank"),
                    "headline": s.get("headline", ""),
                    "plain": s.get("plain_english", ""),
                    "category": s.get("category", ""),
                    "tickers": s.get("tickers") or [],
                    "url": s.get("url", ""),
                }
                for s in stories
            ],
            "connections": [
                {"title": c.get("title", ""), "so_what": c.get("so_what", "")}
                for c in connections
            ],
            "dse": {
                "move": dse.get("turnover_weighted_move_pct"),
                "turnover": dse.get("total_turnover_crore_bdt"),
                "adv": dse.get("advancers"),
                "dec": dse.get("decliners"),
                "verdict": dse.get("breadth_verdict", ""),
                "sectors": [
                    {"name": s["sector"], "move": s["weighted_pct"],
                     "share": s["turnover_share_pct"], "pe": s.get("median_pe")}
                    for s in (dse.get("sectors") or [])[:12]
                ],
            } if dse.get("available") else None,
            "globals": [
                {"name": g["name"], "d1": g.get("change_pct_1d"),
                 "last": g.get("last"), "group": g.get("group", ""),
                 "stale": g.get("stale", False)}
                for g in (glob.get("instruments") or [])
            ],
            # The taka moved out of the Yahoo instrument list into its own
            # cross-checked collector, so it is carried separately here.
            # Older rows predate fx_bd and simply have no entry.
            "fx": ({"rate": fx.get("rate"), "d1": fx.get("change_pct"),
                    "confidence": fx.get("confidence"),
                    "sources": fx.get("source_count"),
                    "spread": fx.get("spread_bdt")}
                   if isinstance(fx, dict) and fx.get("available") else None),
        }
        days.append(day)

    preds = [dict(p) for p in store.db.execute(
        "SELECT * FROM predictions ORDER BY made_on DESC").fetchall()]

    return {
        "days": days,
        "categories": order,
        "predictions": preds,
        "scorecard": store.scorecard(),
        "generated": datetime.now().strftime("%d %b %Y, %H:%M"),
        "palette": {"light": CATEGORICAL_LIGHT, "dark": CATEGORICAL_DARK},
        "diverging": DIVERGING,
    }


def build(store, data_dir: Path) -> Path:
    """Regenerate data/dashboard.html from everything in the database."""
    data_dir = Path(data_dir)
    payload = build_payload(store, data_dir / "briefs")

    template = (Path(__file__).parent / "dashboard_template.html").read_text(encoding="utf8")
    blob = json.dumps(payload, ensure_ascii=False, default=str)
    # The data is injected into a <script> block, so any "</script>" inside a
    # headline would end the block early and break the page.
    blob = blob.replace("</", "<\\/")
    html = template.replace("/*__DATA__*/", blob)

    out = data_dir / "dashboard.html"
    out.write_text(html, encoding="utf8")
    return out
