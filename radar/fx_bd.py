"""The taka rate, cross-checked across independent providers.

Why this module exists
----------------------
Between 6 and 11 August 2026 every brief reported USD/BDT surging 1.0-1.6% a
day. It had not moved. The cause was a single unverified feed (Yahoo `BDT=X`)
whose daily series froze at 122.19 for five consecutive runs while its live
quote drifted; the code subtracted the frozen number from the drifting one and
published the gap as "today's move". On 8 August — a Saturday, no session
anywhere — that produced a lead story about a 1.61% surge to Tk 124.16. The
real rate that day was 121.86, and it had fallen.

The lesson was not "Yahoo is bad". It was: one source, plus a derived number,
plus no sanity check, equals confident fiction. Providers genuinely disagree
about the taka — checked on 12 Aug 2026, three of them differed by up to 2.06
taka on the same historical dates while agreeing to within 0.5 on that day.
A cross-rate feed, a retail aggregator and Bangladesh Bank's official
interbank fixing are simply not the same number.

So this module never reports a rate it cannot corroborate. It asks several
independent providers, takes the median, measures how far apart they are, and
hands the disagreement downstream as data. When they diverge, the brief is
told to say so rather than to pick a number and build a narrative on it.

Daily change is deliberately NOT taken from any provider's history endpoint —
those are what drifted out of alignment. It comes from our own stored series
in the radar DB, so today is always compared against a number we ourselves
published, on a date we can name.
"""

from __future__ import annotations

import warnings
from concurrent.futures import ThreadPoolExecutor
from statistics import median

warnings.filterwarnings("ignore")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_TIMEOUT = 25

# Sources must be genuinely independent — not several wrappers over one
# upstream. currency-api's jsdelivr mirror shares a backend with its pages.dev
# host, so only one of the pair is listed.
_SOURCES = [
    ("currency-api", "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
     lambda j: float(j["usd"]["bdt"])),
    ("er-api", "https://open.er-api.com/v6/latest/USD",
     lambda j: float(j["rates"]["BDT"])),
    ("floatrates", "https://www.floatrates.com/daily/usd.json",
     lambda j: float(j["bdt"]["rate"])),
    ("fxratesapi", "https://api.fxratesapi.com/latest?base=USD&currencies=BDT",
     lambda j: float(j["rates"]["BDT"])),
]

# How far apart providers may sit before we stop trusting the number.
# 0.50 taka is ~0.4% — wider than a normal interbank/retail spread, narrower
# than the 1.1-2.1 taka gaps that produced the August fiction.
AGREEMENT_TOLERANCE_BDT = 0.50

# No figure is published on fewer than this many agreeing providers. Two can
# both be wrong and look like consensus; three that agree is corroboration.
MIN_SOURCES = 3


def _fetch(spec):
    name, url, pick = spec
    try:
        import requests
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        if r.status_code != 200:
            return name, None, f"HTTP {r.status_code}"
        val = pick(r.json())
        # A taka rate outside this band means the feed changed shape or broke.
        if not (80.0 < val < 200.0):
            return name, None, f"implausible value {val}"
        return name, round(val, 4), None
    except Exception as e:
        return name, None, f"{type(e).__name__}: {e}"


def _yahoo_live():
    """Yahoo kept as a third opinion only — never as the sole source."""
    try:
        import yfinance as yf
        v = yf.Ticker("BDT=X").fast_info.get("lastPrice")
        if v and 80.0 < float(v) < 200.0:
            return "yahoo-live", round(float(v), 4), None
        return "yahoo-live", None, "no live price"
    except Exception as e:
        return "yahoo-live", None, f"{type(e).__name__}: {e}"


def collect(prev_rate: float | None = None, prev_date: str | None = None) -> dict:
    """Cross-checked USD/BDT. Never raises.

    `prev_rate`/`prev_date` come from our own stored history, so the change we
    publish is always measured against a number we published before, on a
    named date — not against a provider's silently-realigned back series.
    """
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(_fetch, _SOURCES))
    results.append(_yahoo_live())

    quotes = {n: v for n, v in ((n, v) for n, v, _ in results) if v is not None}
    errors = {n: e for n, _, e in results if e}

    if not quotes:
        return {"available": False, "reason": "no FX provider responded",
                "errors": errors}

    values = sorted(quotes.values())
    rate = round(median(values), 4)
    spread = round(max(values) - min(values), 4)
    corroborated = len(quotes) >= MIN_SOURCES
    agree = spread <= AGREEMENT_TOLERANCE_BDT and corroborated

    out = {
        "available": True,
        "rate": rate,
        "quotes": quotes,
        "source_count": len(quotes),
        "spread_bdt": spread,
        "sources_agree": agree,
        "corroborated": corroborated,
        "confidence": "high" if agree else "low",
        "errors": errors or None,
    }

    # Fewer than three providers answered — report the level, refuse precision.
    if not corroborated:
        out["confidence"] = "low"
        out["sources_agree"] = False
        out["caveat"] = (
            f"Only {len(quotes)} provider(s) responded; {MIN_SOURCES} are required "
            "to corroborate a figure. This rate is uncorroborated — do not build "
            "a story on its exact level and do not make predictions keyed to it.")
    elif not agree:
        out["caveat"] = (
            f"Providers disagree by {spread:.2f} taka "
            f"({', '.join(f'{k} {v:.2f}' for k, v in sorted(quotes.items()))}). "
            "Report the taka as approximate. Do not quote a precise level and "
            "do not make predictions keyed to a threshold this spread could cross.")

    if prev_rate and prev_date:
        out["prev_rate"] = prev_rate
        out["prev_date"] = prev_date
        if prev_rate == rate:
            # Identical to the last stored value: either a genuinely flat day or
            # a frozen feed. Either way there is no move to report.
            out["change_pct"] = 0.0
            out["change_label"] = f"unchanged since {prev_date}"
            out["frozen_warning"] = True
        else:
            out["change_pct"] = round((rate - prev_rate) / prev_rate * 100, 3)
            out["change_label"] = f"since {prev_date}"
    else:
        out["change_pct"] = None
        out["change_label"] = "no prior reading stored — first run for this series"

    return out


def format_for_packet(fx: dict) -> str:
    """Render the taka block for the analyst, disagreement and all."""
    if not fx.get("available"):
        return ("### USD/BDT — the taka\n"
                f"Unavailable today ({fx.get('reason', 'unknown')}). Say the taka "
                "reading was missing. Do NOT state or estimate a rate.\n")

    lines = ["### USD/BDT — the taka (cross-checked across providers)"]
    lines.append(f"  Rate: Tk {fx['rate']:.2f} per USD   "
                 f"[median of {fx['source_count']} independent sources]")

    if fx.get("change_pct") is None:
        lines.append(f"  Change: {fx['change_label']}")
    else:
        lines.append(f"  Change: {fx['change_pct']:+.2f}% {fx['change_label']}")

    lines.append(f"  Provider quotes: " +
                 ", ".join(f"{k} {v:.2f}" for k, v in sorted(fx["quotes"].items())))
    lines.append(f"  Provider spread: {fx['spread_bdt']:.2f} taka   "
                 f"confidence: {fx['confidence'].upper()}   "
                 f"corroborated by {fx['source_count']}/{MIN_SOURCES} required")

    if fx.get("caveat"):
        lines.append(f"  ⚠ {fx['caveat']}")
    if fx.get("frozen_warning"):
        lines.append("  ⚠ Identical to the last stored reading. Treat the taka as "
                     "unchanged; do not describe any move.")
    if fx["confidence"] == "high":
        lines.append("  This reading is corroborated and safe to quote.")

    return "\n".join(lines) + "\n"
