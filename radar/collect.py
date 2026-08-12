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


# Words too common to identify a story. Overlap on these means nothing.
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "will", "has", "have",
    "after", "over", "into", "amid", "says", "said", "new", "its", "but", "not",
    "bangladesh", "bangladeshi", "dhaka", "taka", "crore", "lakh", "percent",
    "year", "years", "month", "day", "week", "government", "national",
}


def _canonical(name: str) -> str:
    """Reduce a publisher name to one comparable key.

    "The Daily Star", "thedailystar.net" and "The Daily Star — Business" are one
    newsroom, not three. Without this, finding the same story through a direct
    feed and through Google News counted as two-source corroboration when it
    was really one paper twice.
    """
    n = (name or "").lower().strip()
    n = re.sub(r"\s+[-–—|]\s+.*$", "", n)          # drop " — Business" sections
    n = re.sub(r"^https?://(www\.)?", "", n)
    n = re.sub(r"^(today|www)\.", "", n)
    n = re.sub(r"\.(com|net|org|co)(\.bd)?$", "", n)
    n = re.sub(r"[^a-z0-9]", "", n)                # "The Daily Star"->thedailystar
    # A masthead and its domain are the same newsroom under different names.
    for canon, variants in _OUTLET_ALIASES.items():
        if any(v in n for v in variants):
            return canon
    return n


_OUTLET_ALIASES = {
    "dailystar":        ("thedailystar", "dailystar"),
    "businessstandard": ("tbsnews", "businessstandard", "tbs"),
    "financialexpress": ("financialexpress",),
    "newage":           ("newagebd", "newage"),
    "prothomalo":       ("prothomalo",),
    "dhakatribune":     ("dhakatribune",),
    "bdnews24":         ("bdnews24",),
    "dailyobserver":    ("observerbd", "dailyobserver"),
    "bss":              ("bssnews",),
}


def _publisher(article: "Article") -> tuple[str, bool]:
    """Who actually published this, and whether we really know.

    Feeds are named for the query that found them ("BD energy / gas / power
    tariffs"), so counting feeds counts our own search terms rather than
    independent newsrooms. Google News keeps the publisher in the title suffix;
    direct feeds are named for their own paper. When neither is available the
    publisher is genuinely unknown, and an unknown must not be counted as
    corroboration — that is how you talk yourself into believing one story is
    three.

    Returns (display name, resolved?).
    """
    m = re.search(r"\s+[-|–—]\s+([^-|–—]{2,40})$", article.title or "")
    if m:
        return m.group(1).strip(), True
    host = re.sub(r"^https?://(www\.)?", "", article.url or "").split("/")[0]
    if host and "news.google.com" not in host:
        return host, True
    return f"via {article.source_name}", False


def _signature(norm_title: str) -> set:
    """The distinctive words in a headline, used to find the same story twice."""
    return {w for w in norm_title.split() if len(w) > 3 and w not in _STOPWORDS}


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
    #
    # A second outlet carrying the same story used to be thrown away as noise.
    # It is not noise — it is corroboration, and it is the cheapest signal we
    # have for whether a claim is real. Duplicates are now counted, so the
    # analyst can see that a story ran in four papers rather than one.
    articles.sort(key=lambda a: a.relevance, reverse=True)
    by_title, by_url, unique = {}, {}, []
    token_index: dict[str, list] = {}     # distinctive word -> entries using it

    for art in articles:
        key = _norm_title(art.title)
        url_key = art.url.split("?")[0].rstrip("/")
        if not key:
            continue

        entry = by_title.get(key) or by_url.get(url_key)

        # Identical headlines are rare across newsrooms — each paper writes its
        # own. Matching only on exact text found almost no corroboration, so
        # near-matches count too: candidates are drawn from a shared-word index
        # and confirmed by overlap, which is what makes "3 outlets ran this"
        # a real measurement rather than a formality.
        if entry is None:
            sig = _signature(key)
            if len(sig) >= 3:
                seen, best, best_score = set(), None, 0.0
                for tok in sig:
                    for cand in token_index.get(tok, ()):
                        cid = id(cand)
                        if cid in seen:
                            continue
                        seen.add(cid)
                        overlap = sig & cand["sig"]
                        score = len(overlap) / max(1, min(len(sig), len(cand["sig"])))
                        if score > best_score:
                            best, best_score = cand, score
                if best is not None and best_score >= 0.65:
                    entry = best

        pub, resolved = _publisher(art)
        ckey = _canonical(pub) if resolved else None
        if entry is not None:
            if ckey and ckey not in entry["publishers"]:
                entry["publishers"].add(ckey)
                entry["outlets"].append(pub)
            elif not resolved and pub not in entry["outlets"]:
                entry["outlets"].append(pub)
            continue

        entry = {"art": art, "outlets": [pub], "sig": _signature(key),
                 "publishers": {ckey} if ckey else set()}
        by_title[key] = entry
        by_url[url_key] = entry
        for tok in entry["sig"]:
            token_index.setdefault(tok, []).append(entry)
        unique.append(entry)

    out_articles = []
    for e in unique:
        d = e["art"].as_dict()
        # Only distinct, identified newsrooms count. Unresolved Google News
        # items are still listed, but they cannot inflate the number.
        d["corroboration"] = max(1, len(e["publishers"]))
        d["corroborating_outlets"] = e["outlets"]
        out_articles.append(d)

    return {
        "articles": out_articles,
        "counts": {
            "fetched": len(articles),
            "unique": len(unique),
            "bd": sum(1 for e in unique if e["art"].scope == "bd"),
            "global": sum(1 for e in unique if e["art"].scope == "global"),
            "macro": sum(1 for e in unique if e["art"].scope == "macro"),
            "corroborated_3plus": sum(1 for e in unique if len(e["publishers"]) >= 3),
            "corroborated_2plus": sum(1 for e in unique if len(e["publishers"]) >= 2),
            "single_source": sum(1 for e in unique if len(e["publishers"]) <= 1),
        },
        "source_report": sorted(report, key=lambda r: (-r["count"], r["source"])),
        "window_hours": hours,
    }
