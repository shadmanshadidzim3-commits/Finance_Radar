"""One-off correction of predictions scored against the broken taka feed.

Two calls were marked `correct` on the strength of a USD/BDT reading of
Tk 124.16 on 2026-08-08. That number never existed. It came from Yahoo's
BDT=X series, whose daily bars had frozen at 122.19 while its live quote
drifted; 8 August was a Saturday with no FX session anywhere. Independent
sources put the taka at 121.86 that day, and its high for the whole window
at 123.59 on 10 August — it did not reach 124 at any point.

The predictions were therefore not correct. They are re-marked `wrong`, with
the evidence recorded, so the hit rate reflects what actually happened.

Run with --apply to write. Without it, prints the plan and changes nothing.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "data" / "radar.db"

# What actually happened, from sources independent of the broken feed.
EVIDENCE = (
    "Re-scored 2026-08-12. The Tk 124.16 reading this was judged against was a "
    "data error: Yahoo's BDT=X daily series had frozen at 122.19 while its live "
    "quote drifted, and 2026-08-08 was a Saturday with no FX session. "
    "Independent sources put USD/BDT at 121.86 on 8 Aug and at a window high of "
    "123.59 on 10 Aug. The taka never traded above Tk 124.00, so this call did "
    "not come in."
)
LESSON = (
    "Never resolve a prediction against the same feed that generated the "
    "narrative behind it, and never against a market that was closed. A "
    "threshold call needs a corroborated reading from an independent source "
    "before it can be marked correct."
)

TARGETS = [
    ("2026-08-04", "%124.00%"),
    ("2026-08-07", "%124.00%"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes")
    args = ap.parse_args()

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    def scorecard(label):
        rows = dict(db.execute(
            "SELECT status, COUNT(*) FROM predictions GROUP BY status").fetchall())
        judged = sum(v for k, v in rows.items() if k != "open")
        correct = rows.get("correct", 0)
        rate = (correct / judged * 100) if judged else 0
        print(f"{label}: {rows} -> {correct}/{judged} judged = {rate:.1f}% hit rate")

    scorecard("BEFORE")

    found = []
    for made_on, pattern in TARGETS:
        for r in db.execute(
                "SELECT id, made_on, statement, status, resolution FROM predictions "
                "WHERE made_on=? AND statement LIKE ? AND status='correct'",
                (made_on, pattern)):
            found.append(dict(r))

    if not found:
        print("\nNothing to correct — already re-scored, or the rows are not there.")
        return 0

    print(f"\n{len(found)} prediction(s) to re-mark correct -> wrong:")
    for r in found:
        print(f"\n  [{r['id']}] made {r['made_on']}")
        print(f"      {r['statement'][:100]}")
        print(f"      was scored: {(r['resolution'] or '')[:100]}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to write.")
        return 0

    for r in found:
        db.execute(
            "UPDATE predictions SET status='wrong', resolution=?, lesson=? "
            "WHERE id=?", (EVIDENCE, LESSON, r["id"]))
    db.commit()
    print("\nApplied.")
    scorecard("AFTER ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
