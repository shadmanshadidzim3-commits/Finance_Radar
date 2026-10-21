#!/usr/bin/env python
"""Make (or remake) the English and Bangla videos for a day that already has a brief.

    python make_video.py                        latest brief
    python make_video.py --date 2026-10-19
    python make_video.py --engine gemini_api    override the configured engine

The daily run makes the videos by itself; this is for redoing one by hand.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from radar import engine as engine_mod, video  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None)
    ap.add_argument("--engine", default=None)
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf8")) or {}
    db = sqlite3.connect(ROOT / "data" / "radar.db")
    q = ("select run_date, raw_response from runs where run_date = ?"
         if args.date else
         "select run_date, raw_response from runs order by run_date desc limit 1")
    row = db.execute(q, (args.date,) if args.date else ()).fetchone()
    if not row:
        print(f"No brief stored for {args.date or 'any day'}.")
        return 1
    day, raw = row
    analysis = engine_mod.extract_json(raw)

    eng_cfg = cfg.get("engine", {})
    eng = engine_mod.build_engine(args.engine or eng_cfg.get("name", "auto"),
                                  eng_cfg.get("model"))
    print(f"Making videos for {day} with {eng.name}…")
    out = video.make_videos(eng, analysis, day, ROOT / "data" / "videos",
                            cfg.get("video", {}),
                            brand=cfg.get("output", {}).get("brand", "60 SECOND FINANCE"),
                            prompt_path=ROOT / "prompts" / "video_script.md")
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
