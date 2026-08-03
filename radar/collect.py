"""News collection: fetch every feed in parallel, clean, dedupe, and rank.

Deduplication matters more than it sounds. The same Reuters story reaches us via
Yahoo, CNBC and two Google News queries; without dedupe the analyst sees one
event four times and over-weights it.
"""

from __future__ import annotations

import concurrent.futures as cf
import html
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from .sources import all_feeds, Source

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Words that mark a story as financially relevant. Used only to rank, never to
# hard-filter — a political story can be the biggest financial news of the day.
FINANCE_TERMS = {
    "bank", "inflation", "gdp", "export", "import", "tariff", "tax", "revenue",
    "budget", "deficit", "surplus", "reserve", "remittance", "taka", "dollar",
    "currency", "interest", "rate", "loan", "debt", "bond", "stock", "share",
    "index", "dse", "dsex", "ipo", "dividend", "earnings", "profit", "loss",
    "market", "trade", "investment", "investor", "fund", "capital", "price",
    "fuel", "gas", "energy", "power", "tariff", "rmg", "garment", "textile",
    "imf", "world bank", "adb", "bsec", "nbr", "monetary", "fiscal", "credit",
    "default", "npl", "liquidity", "merger", "acquisition", "subsidy", "fdi",
}


@dataclass
class Article:
    source_key: str
    source_name: str
    scope: str
    weight: int
    title: str
    url: str
    published: str
    summary: str
    tags: list = field(default_factory=list)
    relevance: float = 0.0

    def as_dict(self):
        return asdict(self)


def _clean(text: str, limit: int = 400) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _norm_title(title: str) -> str:
    """Normalise for dedupe: lowercase, strip source suffix and punctuation."""
    t = title.lower()
    t = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", t)   # trailing " - The Daily Star"
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _score(article: Article) -> float:
    """Rank by source weight, finance-term density, and recency."""
    blob = f"{article.title} {article.summary}".lower()
    hits = sum(1 for term in FINANCE_TERMS if term in blob)
    score = article.weight * 2.0 + min(hits, 12) * 1.5
    if article.scope == "bd":
        score += 6.0                      # Bangladesh is the user's home market
    if article.scope == "macro":
        score += 3.0                      # central banks move everything
    try:
        age_h = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(article.published)).total_seconds() / 3600
        score += max(0.0, 8.0 - age_h / 6.0)
    except Exception:
        pass
    return round(score, 2)


def _parse_entry(entry, src: Source, cutoff: datetime) -> Article | None:
    title = _clean(getattr(entry, "title", ""), 300)
    link = getattr(entry, "link", "") or ""
    if not title or not link:
        return None

    published = ""
    for attr in ("published_parsed", "updated_parsed"):
        tm = getattr(entry, attr, None)
        if tm:
            try:
                dt = datetime(*tm[:6], tzinfo=timezone.utc)
                if dt < cutoff:
                    return None
                published = dt.isoformat()
                break
            except Exception:
                pass

    summary = _clean(getattr(entry, "summary", "") or getattr(entry, "description", ""))
    return Article(
        source_key=src.key, source_name=src.name, scope=src.scope, weight=src.weight,
        title=title, url=link, published=published, summary=summary, tags=list(src.tags),
    )


def _fetch_one(src: Source, hours: int) -> list[Article]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        resp = requests.get(src.url, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception:
        return []
    out = []
    for entry in parsed.entries[:60]:
        art = _parse_entry(entry, src, cutoff)
        if art:
            art.relevance = _score(art)
            out.append(art)
    return out


def collect(hours: int = 30, per_source_cap: int = 12) -> dict:
    """Fetch all feeds, dedupe, and return ranked articles plus a source report."""
    feeds = all_feeds()
    report, articles = [], []

    empty: list = []

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(_fetch_one, s, hours): s for s in feeds}
        for fut in cf.as_completed(futures):
            src = futures[fut]
            try:
                got = fut.result()
            except Exception as e:
                report.append({"source": src.name, "ok": False, "count": 0, "error": str(e)[:80]})
                continue
            if not got:
                empty.append(src)          # retried serially below
                continue
            got.sort(key=lambda a: a.relevance, reverse=True)
            got = got[:per_source_cap]
            articles.extend(got)
            report.append({"source": src.name, "ok": True, "count": len(got)})

    # Google News rate-limits when a dozen of its query feeds arrive at once and
    # answers with an empty document rather than an error, so a source silently
    # disappears from the day's brief. Anything that came back empty gets one
    # more serial, spaced-out attempt before we believe it.
    for src in empty:
        got = []
        try:
            time.sleep(1.2)
            got = _fetch_one(src, hours)
        except Exception as e:
            report.append({"source": src.name, "ok": False, "count": 0, "error": str(e)[:80]})
            continue
        got.sort(key=lambda a: a.relevance, reverse=True)
        got = got[:per_source_cap]
        articles.extend(got)
        report.append({"source": src.name, "ok": True, "count": len(got),
                       "retried": True})

    # Dedupe: keep the highest-scoring copy of each story.
    articles.sort(key=lambda a: a.relevance, reverse=True)
    seen_titles, seen_urls, unique = set(), set(), []
    for art in articles:
        key = _norm_title(art.title)
        url_key = art.url.split("?")[0].rstrip("/")
        if not key or key in seen_titles or url_key in seen_urls:
            continue
        seen_titles.add(key)
        seen_urls.add(url_key)
        unique.append(art)

    return {
        "articles": [a.as_dict() for a in unique],
        "counts": {
            "fetched": len(articles),
            "unique": len(unique),
            "bd": sum(1 for a in unique if a.scope == "bd"),
            "global": sum(1 for a in unique if a.scope == "global"),
            "macro": sum(1 for a in unique if a.scope == "macro"),
        },
        "source_report": sorted(report, key=lambda r: (-r["count"], r["source"])),
        "window_hours": hours,
    }
