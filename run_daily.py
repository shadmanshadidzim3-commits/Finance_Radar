#!/usr/bin/env python
"""Finance Radar — daily run.

    python run_daily.py                 normal run
    python run_daily.py --dry-run       gather data, print what would be sent, no LLM call
    python run_daily.py --force         re-run a day that already has a brief
    python run_daily.py --date 2026-07-30    label the run as a specific date
    python run_daily.py --engine gemini_cli  override the configured engine
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import webbrowser
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from radar import analyze, card, collect, dashboard, dse as dse_mod, engine as engine_mod
from radar import html_render, markets, notify, render
from radar.store import Store

DATA = ROOT / "data"
LOGS = ROOT / "logs"


def log(msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the daily Finance Radar brief.")
    ap.add_argument("--dry-run", action="store_true",
                    help="collect and build the packet, but do not call the model")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing brief for this date")
    ap.add_argument("--date", default=date.today().isoformat(),
                    help="date label for this run (YYYY-MM-DD)")
    ap.add_argument("--engine", default=None, help="override the configured engine")
    args = ap.parse_args()

    cfg = load_config()
    day = args.date
    LOGS.mkdir(parents=True, exist_ok=True)

    store = Store(DATA / "radar.db")
    if store.has_run(day) and not args.force and not args.dry_run:
        log(f"A brief for {day} already exists. Use --force to redo it.")
        store.close()
        return 0

    # ------------------------------------------------------------- gather
    log("Collecting news…")
    news = collect.collect(hours=cfg["news"]["window_hours"],
                           per_source_cap=cfg["news"]["per_source_cap"])
    ok_sources = sum(1 for r in news["source_report"] if r["ok"] and r["count"])
    log(f"  {news['counts']['unique']} unique stories from {ok_sources} sources "
        f"({news['counts']['bd']} BD / {news['counts']['global']} global / "
        f"{news['counts']['macro']} macro)")

    dse_data = {"available": False, "reason": "disabled in config"}
    if cfg["markets"].get("include_dse", True):
        log("Collecting DSE…")
        dse_data = dse_mod.collect(DATA)
        if dse_data.get("available"):
            log(f"  {dse_data['instruments_traded']} traded · "
                f"Tk {dse_data['total_turnover_crore_bdt']:,} crore turnover · "
                f"{dse_data['breadth_verdict']}")
        else:
            log(f"  DSE unavailable: {dse_data.get('reason')}")

    mkt = {"available": False, "reason": "disabled in config"}
    if cfg["markets"].get("include_global", True):
        log("Collecting global markets…")
        mkt = markets.collect()
        log(f"  {len(mkt.get('instruments', []))} instruments"
            if mkt.get("available") else f"  unavailable: {mkt.get('reason')}")

    if not news["articles"] and not dse_data.get("available"):
        log("No news and no market data — aborting rather than writing an empty brief.")
        store.close()
        return 2

    # ------------------------------------------------------------- packet
    log("Building the briefing packet…")
    packet = analyze.build_packet(
        store, news, dse_data, mkt, day,
        news_limit=cfg["news"]["send_to_analyst"],
        lookback_days=cfg["memory"]["lookback_days"])
    (LOGS / f"packet_{day}.md").write_text(packet, encoding="utf8")
    log(f"  packet is {len(packet):,} characters "
        f"(~{len(packet)//4:,} tokens) → logs/packet_{day}.md")

    if args.dry_run:
        due = store.due_predictions(day)
        log(f"Dry run. {len(store.open_predictions())} open predictions "
            f"({len(due)} due for judgement).")
        print("\n" + "=" * 70)
        print(packet[:3000])
        print("… truncated. Full packet in logs/.")
        store.close()
        return 0

    # ------------------------------------------------------------ analyse
    eng_cfg = cfg["engine"]
    try:
        eng = engine_mod.build_engine(args.engine or eng_cfg["name"], eng_cfg.get("model"))
    except engine_mod.EngineError as e:
        log(f"ENGINE ERROR\n{e}")
        store.close()
        return 3

    log(f"Analysing with {eng.name}… (this usually takes 1-3 minutes)")
    system_prompt = analyze.load_system_prompt(ROOT / "prompts" / "analyst.md")
    try:
        analysis, raw = analyze.analyse(eng, system_prompt, packet)
    except Exception as e:
        (LOGS / f"error_{day}.txt").write_text(
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}", encoding="utf8")
        log(f"Analysis failed: {type(e).__name__}: {e}")
        log(f"  details in logs/error_{day}.txt")
        store.close()
        return 4

    (LOGS / f"raw_{day}.txt").write_text(raw, encoding="utf8")
    log(f"  {len(analysis.get('top_stories', []))} stories · "
        f"{len(analysis.get('connections', []))} connections · "
        f"{len(analysis.get('predictions', []))} new calls · "
        f"{len(analysis.get('resolutions', []))} resolutions")

    # -------------------------------------------------------------- persist
    resolved = store.apply_resolutions(analysis.get("resolutions", []), day)
    saved = store.save_predictions(day, analysis.get("predictions", []))
    market_snapshot = {"dse": dse_data, "global": mkt}
    store.save_run(day, analysis, market_snapshot, eng.name, raw,
                   news["counts"]["unique"])
    scorecard = store.scorecard()
    log(f"  memory updated: {saved} new predictions, {resolved} resolved · "
        f"hit rate {scorecard['hit_rate_pct']}%"
        if scorecard["scored"] else f"  memory updated: {saved} new predictions")

    # -------------------------------------------------------------- outputs
    post_text = render.social_text(analysis, day)

    brief_md = render.brief_markdown(day, analysis, dse_data, mkt, news,
                                     scorecard, eng.name)
    md_path = DATA / "briefs" / f"{day}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(brief_md, encoding="utf8")

    # The HTML page is the one built for reading, so it is what gets opened.
    brief_path = DATA / "briefs" / f"{day}.html"
    brief_path.write_text(
        html_render.render(day, analysis, dse_data, mkt, news, scorecard,
                           eng.name, social_text=post_text,
                           brand=cfg["output"].get("brand", "60 SECOND FINANCE")),
        encoding="utf8")

    post_path = DATA / "briefs" / f"{day}_post.txt"
    post_path.write_text(post_text, encoding="utf8")

    card_path = None
    if cfg["output"].get("make_card", True):
        try:
            card_path = card.make_card(analysis, day, DATA / "cards" / f"{day}.png",
                                       brand=cfg["output"].get("brand", "60 SECOND FINANCE"))
        except Exception as e:
            log(f"  card generation failed ({type(e).__name__}: {e}) — continuing")

    try:
        dash_path = dashboard.build(store, DATA)
    except Exception as e:
        dash_path = None
        log(f"  dashboard build failed ({type(e).__name__}: {e}) — continuing")

    log(f"Brief   → {brief_path}")
    log(f"Markdown→ {md_path}")
    log(f"Post    → {post_path}")
    if card_path:
        log(f"Card    → {card_path}")
    if dash_path:
        log(f"Archive → {dash_path}   <- your dashboard, searchable across all days")

    # --------------------------------------------------------------- notify
    results = notify.announce(cfg.get("notify", {}), day, analysis, brief_path, card_path)
    if results:
        log("Notified: " + ", ".join(f"{k}={'ok' if v else 'failed'}"
                                     for k, v in results.items()))

    if cfg["output"].get("open_brief_when_done"):
        # Open the archive: it lands on today with a link through to the full
        # brief, and gives you every previous day in the same place.
        webbrowser.open((dash_path or brief_path).resolve().as_uri())

    store.close()
    log("Done.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
