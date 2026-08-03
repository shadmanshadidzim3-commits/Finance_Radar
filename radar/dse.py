"""Dhaka Stock Exchange collector.

DSE publishes a full end-of-session table at latest_share_price_scroll_l.php with
columns: #, TRADING CODE, LTP, HIGH, LOW, CLOSEP, YCP, CHANGE, TRADE, VALUE (mn), VOLUME.
That one page gives breadth, money flow, blue-chip moves and sector performance,
so we lean on it rather than scraping many fragile sub-pages.

Sector membership is read from DSE's own industry pages and cached on disk for a
week, so we never rely on a hand-maintained ticker list going stale.

Note on SSL: dsebd.org serves an incomplete certificate chain, so a verified
request fails. We retry with verification off. That is acceptable here because
this is public, read-only, non-sensitive market data — but it is why you see
`verify=False` below.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
import urllib3

from . import dse_sectors

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://www.dsebd.org/"
PRICE_URLS = [
    BASE + "latest_share_price_scroll_l.php",       # primary
    BASE + "latest_share_price_scroll_by_ltp.php",  # same data, different sort
]
SECTOR_PE_URL = BASE + "sectoral_PE.php"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Instrument classes that are not operating companies. Kept out of sector
# performance so government bonds don't drown out the equity signal.
NON_EQUITY = {"G-SEC (T.Bond)", "Corporate Bond", "Debenture"}

# Reported individually every day. Edit freely — anything here gets its own line.
BLUE_CHIPS = [
    "GP", "ROBI", "BATBC", "SQURPHARMA", "WALTONHIL", "BRACBANK", "RENATA",
    "UNITEDPOWR", "BEXIMCO", "LHBL", "ISLAMIBANK", "MARICO", "BERGERPBL",
    "TITASGAS", "POWERGRID", "DUTCHBANGL", "CITYBANK", "EBL", "SUMITPOWER",
    "BSRMLTD", "OLYMPIC", "IDLC", "BXPHARMA", "SQUARETEXT", "LINDEBD",
    "UNILEVERCL", "GPHISPAT", "BSCCL", "PUBALIBANK", "MJLBD", "PADMAOIL",
    "JAMUNAOIL", "HEIDELBCEM", "ACI", "ACMELAB", "IBNSINA", "DESCO",
    "NAVANACNG", "CONFIDCEM", "RECKITTBEN",
]


@dataclass
class Quote:
    code: str
    ltp: float
    high: float
    low: float
    close: float
    ycp: float          # yesterday's closing price
    change: float       # absolute taka change
    pct: float          # percent change
    trades: int
    value_mn: float     # turnover, millions of taka
    volume: int
    sector: str

    def as_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------
# fetching helpers
# --------------------------------------------------------------------------

def _fetch(url: str, timeout: int = 45) -> str:
    """Fetch a DSE page, retrying without SSL verification (broken cert chain)."""
    headers = {"User-Agent": UA}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except requests.exceptions.SSLError:
        r = requests.get(url, headers=headers, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.text


def _rows(html: str):
    """Yield each table row as a list of cleaned cell strings."""
    for table in re.findall(r"<table[^>]*>.*?</table>", html, re.S | re.I):
        parsed = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
            cells = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c).replace("\xa0", " ")).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            ]
            if cells:
                parsed.append(cells)
        if parsed:
            yield parsed


def _num(s: str, default=0.0) -> float:
    s = (s or "").replace(",", "").replace("\xa0", "").strip()
    if not s or s in {"-", "--", "N/A"}:
        return default
    try:
        return float(s)
    except ValueError:
        return default


# --------------------------------------------------------------------------
# sector map (scraped from DSE, cached on disk)
# --------------------------------------------------------------------------

def fetch_sector_pe() -> dict[str, float]:
    """Sector median P/E — useful valuation context for the analyst."""
    try:
        for table in _rows(_fetch(SECTOR_PE_URL)):
            if len(table) > 10 and any("P/E" in " ".join(r) for r in table[:2]):
                out = {}
                for row in table[1:]:
                    if len(row) >= 3 and row[0].isdigit():
                        pe = _num(row[2], default=0.0)
                        if pe:
                            out[row[1].strip()] = round(pe, 2)
                return out
    except Exception:
        pass
    return {}


# --------------------------------------------------------------------------
# quotes
# --------------------------------------------------------------------------

def fetch_quotes() -> list[Quote]:
    """Return every traded DSE instrument for the latest session."""
    last_err = None
    for url in PRICE_URLS:
        try:
            html = _fetch(url)
        except Exception as e:
            last_err = e
            continue
        for table in _rows(html):
            if len(table) < 50:                 # the real table has ~395 rows
                continue
            quotes = []
            for cells in table:
                if len(cells) < 11 or not cells[0].isdigit():
                    continue
                code = cells[1].strip().upper()
                ycp, change = _num(cells[6]), _num(cells[7])
                quotes.append(Quote(
                    code=code,
                    ltp=_num(cells[2]), high=_num(cells[3]), low=_num(cells[4]),
                    close=_num(cells[5]), ycp=ycp, change=change,
                    pct=round(change / ycp * 100.0, 2) if ycp else 0.0,
                    trades=int(_num(cells[8])), value_mn=_num(cells[9]),
                    volume=int(_num(cells[10])),
                    sector=dse_sectors.sector_for(code),
                ))
            if quotes:
                return quotes
    if last_err:
        raise last_err
    return []


def summarise(quotes: list[Quote], sector_pe: dict[str, float]) -> dict:
    """Turn the raw table into the numbers an analyst would actually look at."""
    if not quotes:
        return {"available": False, "reason": "no quotes parsed from DSE"}

    traded = [q for q in quotes if q.volume > 0]
    if not traded:
        return {"available": False, "reason": "market closed / no volume"}

    adv = sum(1 for q in traded if q.change > 0)
    dec = sum(1 for q in traded if q.change < 0)
    unch = sum(1 for q in traded if q.change == 0)

    total_turnover = sum(q.value_mn for q in traded)
    # Turnover-weighted average move: the closest honest proxy for "the market"
    # when the published DSEX print is not machine-readable.
    weighted = (sum(q.pct * q.value_mn for q in traded) / total_turnover) if total_turnover else 0.0

    def top(key, n=8, reverse=True):
        return [
            {"code": q.code, "sector": q.sector, "close": q.close,
             "pct": q.pct, "turnover_mn": round(q.value_mn, 1)}
            for q in sorted(traded, key=key, reverse=reverse)[:n]
        ]

    sector_rows = []
    for sector in sorted({q.sector for q in traded}):
        if sector in NON_EQUITY:      # bonds would drown out the equity signal
            continue
        members = [q for q in traded if q.sector == sector]
        turn = sum(q.value_mn for q in members)
        sector_rows.append({
            "sector": sector,
            "companies": len(members),
            "turnover_mn": round(turn, 1),
            "turnover_share_pct": round(turn / total_turnover * 100, 1) if total_turnover else 0,
            "avg_pct": round(statistics.fmean(q.pct for q in members), 2),
            "weighted_pct": round(sum(q.pct * q.value_mn for q in members) / turn, 2) if turn else 0.0,
            "advancers": sum(1 for q in members if q.change > 0),
            "decliners": sum(1 for q in members if q.change < 0),
            "median_pe": sector_pe.get(sector),
        })
    sector_rows.sort(key=lambda r: r["turnover_mn"], reverse=True)

    by_code = {q.code: q for q in traded}
    chips = [
        {"code": q.code, "sector": q.sector, "close": q.close,
         "pct": q.pct, "turnover_mn": round(q.value_mn, 1)}
        for q in (by_code.get(c) for c in BLUE_CHIPS) if q
    ]
    chips.sort(key=lambda c: abs(c["pct"]), reverse=True)

    return {
        "available": True,
        "instruments_listed": len(quotes),
        "instruments_traded": len(traded),
        "advancers": adv,
        "decliners": dec,
        "unchanged": unch,
        "advance_decline_ratio": round(adv / dec, 2) if dec else None,
        "total_turnover_mn_bdt": round(total_turnover, 1),
        "total_turnover_crore_bdt": round(total_turnover / 10, 1),   # 1 crore = 10 mn
        "turnover_weighted_move_pct": round(weighted, 2),
        "breadth_verdict": _verdict(adv, dec, weighted),
        "top_gainers": top(lambda q: q.pct),
        "top_losers": top(lambda q: q.pct, reverse=False),
        "most_active_by_turnover": top(lambda q: q.value_mn),
        "blue_chips": chips,
        "sectors": sector_rows,
        "sector_median_pe": sector_pe,
    }


def _verdict(adv: int, dec: int, weighted: float) -> str:
    if adv + dec == 0:
        return "no trading"
    ratio = adv / dec if dec else 99.0
    if ratio > 2 and weighted > 0.5:
        return "broad-based rally"
    if ratio > 1.3:
        return "positive breadth"
    if ratio < 0.5 and weighted < -0.5:
        return "broad-based selloff"
    if ratio < 0.77:
        return "negative breadth"
    return "mixed / rangebound"


def collect(data_dir: Path | None = None) -> dict:
    """Entry point used by the daily run. Never raises."""
    try:
        quotes = fetch_quotes()
        summary = summarise(quotes, fetch_sector_pe())
        summary["source"] = PRICE_URLS[0]
        summary["sector_coverage"] = dse_sectors.coverage([q.code for q in quotes])
        return summary
    except Exception as e:
        return {"available": False,
                "reason": f"{type(e).__name__}: {e}",
                "source": PRICE_URLS[0],
                "note": "DSE unreachable — check lankabd.com or amarstock.com manually today."}
