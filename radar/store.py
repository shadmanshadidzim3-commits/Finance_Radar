"""Persistent memory.

This is the piece that makes the system compound rather than restart each day.
Three things are remembered:

  runs        — one row per day: the scenario, the connections, the social post.
  headlines   — the stories behind each day's brief, so themes can be traced.
  predictions — explicit, dated, falsifiable calls with a resolution date.

Predictions are the point. A prediction that is never scored is just an opinion,
so every open call is re-shown to the analyst each day and must eventually be
marked correct, wrong, partial or unclear. The scorecard that comes out of this
is the honest record of how good the analysis actually is.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_date        TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    headline_count  INTEGER,
    top_stories     TEXT,   -- JSON
    connections     TEXT,   -- JSON
    scenario        TEXT,
    social_post     TEXT,   -- JSON
    market_snapshot TEXT,   -- JSON
    engine          TEXT,
    raw_response    TEXT
);

CREATE TABLE IF NOT EXISTS headlines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT NOT NULL,
    rank        INTEGER,
    headline    TEXT NOT NULL,
    why_matters TEXT,
    category    TEXT,
    tickers     TEXT,
    sources     TEXT,
    url         TEXT,
    FOREIGN KEY (run_date) REFERENCES runs(run_date)
);

CREATE TABLE IF NOT EXISTS predictions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    made_on       TEXT NOT NULL,
    statement     TEXT NOT NULL,
    rationale     TEXT,
    confidence    INTEGER,          -- 1-100
    horizon_days  INTEGER,
    resolve_by    TEXT,
    category      TEXT,
    status        TEXT DEFAULT 'open',   -- open|correct|wrong|partial|unclear
    resolved_on   TEXT,
    resolution    TEXT,
    lesson        TEXT
);

CREATE INDEX IF NOT EXISTS idx_pred_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_headlines_date ON headlines(run_date);
"""


class Store:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    # ---------------------------------------------------------------- writes

    def save_run(self, run_date: str, analysis: dict, market: dict,
                 engine: str, raw: str, headline_count: int) -> None:
        self.db.execute("""
            INSERT INTO runs (run_date, created_at, headline_count, top_stories,
                              connections, scenario, social_post, market_snapshot,
                              engine, raw_response)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_date) DO UPDATE SET
                created_at=excluded.created_at,
                headline_count=excluded.headline_count,
                top_stories=excluded.top_stories,
                connections=excluded.connections,
                scenario=excluded.scenario,
                social_post=excluded.social_post,
                market_snapshot=excluded.market_snapshot,
                engine=excluded.engine,
                raw_response=excluded.raw_response
        """, (
            run_date, datetime.now().isoformat(timespec="seconds"), headline_count,
            json.dumps(analysis.get("top_stories", []), ensure_ascii=False),
            json.dumps(analysis.get("connections", []), ensure_ascii=False),
            analysis.get("scenario", ""),
            json.dumps(analysis.get("social_post", {}), ensure_ascii=False),
            json.dumps(market, ensure_ascii=False, default=str),
            engine, raw,
        ))

        self.db.execute("DELETE FROM headlines WHERE run_date = ?", (run_date,))
        for i, story in enumerate(analysis.get("top_stories", []), start=1):
            self.db.execute("""
                INSERT INTO headlines (run_date, rank, headline, why_matters,
                                       category, tickers, sources, url)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                run_date, i, story.get("headline", ""), story.get("why_it_matters", ""),
                story.get("category", ""),
                ", ".join(story.get("tickers", []) or []),
                ", ".join(story.get("sources", []) or []),
                story.get("url", ""),
            ))
        self.db.commit()

    def save_predictions(self, run_date: str, predictions: list[dict]) -> int:
        # Re-running a day (--force) replaces that day's brief, so the calls
        # from the superseded run are orphans and must go with it. Matching on
        # statement text is not enough: the model rewords its calls each time,
        # so every re-run used to leave a whole extra set behind, inflating the
        # open list and skewing the eventual hit rate. Anything already
        # resolved is kept — that judgement has been made and stands.
        self.db.execute(
            "DELETE FROM predictions WHERE made_on=? AND status='open'",
            (run_date,))

        n = 0
        for p in predictions:
            statement = (p.get("statement") or "").strip()
            if not statement:
                continue
            # Don't store the same call twice if a day is re-run.
            dup = self.db.execute(
                "SELECT 1 FROM predictions WHERE made_on=? AND statement=?",
                (run_date, statement)).fetchone()
            if dup:
                continue
            horizon = int(p.get("horizon_days") or 7)
            resolve_by = (date.fromisoformat(run_date) + timedelta(days=horizon)).isoformat()
            self.db.execute("""
                INSERT INTO predictions (made_on, statement, rationale, confidence,
                                         horizon_days, resolve_by, category, status)
                VALUES (?,?,?,?,?,?,?, 'open')
            """, (run_date, statement, p.get("rationale", ""),
                  int(p.get("confidence") or 50), horizon, resolve_by,
                  p.get("category", "")))
            n += 1
        self.db.commit()
        return n

    def apply_resolutions(self, resolutions: list[dict], today: str) -> int:
        n = 0
        for r in resolutions:
            pid = r.get("id")
            status = (r.get("status") or "").lower()
            if pid is None or status not in {"correct", "wrong", "partial", "unclear"}:
                continue
            cur = self.db.execute("""
                UPDATE predictions
                   SET status=?, resolved_on=?, resolution=?, lesson=?
                 WHERE id=? AND status='open'
            """, (status, today, r.get("resolution", ""), r.get("lesson", ""), int(pid)))
            n += cur.rowcount          # rows actually updated, not a running total
        self.db.commit()
        return n

    # ----------------------------------------------------------------- reads

    def recent_runs(self, days: int = 7, before: str | None = None) -> list[dict]:
        q = "SELECT * FROM runs"
        args: list = []
        if before:
            q += " WHERE run_date < ?"
            args.append(before)
        q += " ORDER BY run_date DESC LIMIT ?"
        args.append(days)
        return [dict(r) for r in self.db.execute(q, args).fetchall()]

    def open_predictions(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM predictions WHERE status='open' ORDER BY resolve_by ASC"
        ).fetchall()]

    def due_predictions(self, today: str) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM predictions WHERE status='open' AND resolve_by <= ? "
            "ORDER BY resolve_by ASC", (today,)).fetchall()]

    def scorecard(self) -> dict:
        rows = self.db.execute(
            "SELECT status, COUNT(*) c FROM predictions GROUP BY status").fetchall()
        counts = {r["status"]: r["c"] for r in rows}
        scored = sum(counts.get(k, 0) for k in ("correct", "wrong", "partial"))
        correct = counts.get("correct", 0) + 0.5 * counts.get("partial", 0)
        return {
            "total": sum(counts.values()),
            "open": counts.get("open", 0),
            "correct": counts.get("correct", 0),
            "wrong": counts.get("wrong", 0),
            "partial": counts.get("partial", 0),
            "unclear": counts.get("unclear", 0),
            "scored": scored,
            "hit_rate_pct": round(correct / scored * 100, 1) if scored else None,
        }

    def recurring_themes(self, days: int = 30, min_count: int = 2) -> list[dict]:
        """Categories that keep reappearing — the analyst uses these to spot trends."""
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = self.db.execute("""
            SELECT category, COUNT(*) c, MAX(run_date) last_seen
              FROM headlines WHERE run_date >= ? AND category != ''
             GROUP BY category HAVING c >= ? ORDER BY c DESC LIMIT 12
        """, (since, min_count)).fetchall()
        return [dict(r) for r in rows]

    def has_run(self, run_date: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM runs WHERE run_date=?", (run_date,)).fetchone() is not None
