"""Global market data via Yahoo Finance.

The instrument list is deliberately Bangladesh-centric. Cotton matters because
RMG is ~80% of export earnings; wheat and soybean oil drive food inflation and
the import bill; crude and LNG drive the energy subsidy and the power tariff
debate; the dollar index and US 10-year drive pressure on the taka and on
remittance-funded reserves. India's Sensex is included because Bangladesh's
trade and competitive position is tied to it.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

# How many identical consecutive closes mean the series has stopped updating
# rather than genuinely sitting still. Yahoo's BDT=X froze at 122.19 for five
# straight runs in August 2026 while the code kept differencing it against a
# drifting live quote and publishing the gap as a daily move.
FROZEN_RUN_LENGTH = 3

# A bar older than this is not "the latest close" and must not be labelled one.
MAX_BAR_AGE_DAYS = 5

# (yahoo symbol, display name, group, why it matters for Bangladesh)
#
# USD/BDT is deliberately ABSENT. Yahoo's BDT=X is a thin synthetic cross that
# goes stale for days without saying so; it is now only one of three opinions
# inside radar/fx_bd.py, which cross-checks providers and refuses to report a
# taka rate it cannot corroborate. Do not add it back here.
INSTRUMENTS = [
    # --- Currencies & rates: the taka's external pressure gauges ---
    ("DX-Y.NYB",  "US Dollar Index",    "FX",         "Broad dollar strength squeezes all EM currencies"),
    ("INR=X",     "USD/INR",            "FX",         "Competitiveness vs India, Bangladesh's main trade rival"),
    ("EURUSD=X",  "EUR/USD",            "FX",         "EU is the largest RMG export destination"),
    ("^TNX",      "US 10Y Treasury",    "Rates",      "Global risk-free rate; drives EM capital flows"),

    # --- Commodities: Bangladesh's import bill and input costs ---
    ("CT=F",      "Cotton",             "Commodity",  "Core RMG input cost — direct margin impact"),
    ("CL=F",      "WTI Crude",          "Commodity",  "Fuel imports, subsidy burden, inflation"),
    ("BZ=F",      "Brent Crude",        "Commodity",  "Benchmark for Bangladesh's fuel import pricing"),
    ("NG=F",      "Natural Gas",        "Commodity",  "LNG import cost; power and fertiliser tariffs"),
    ("ZW=F",      "Wheat",              "Commodity",  "Food inflation; Bangladesh is a major wheat importer"),
    ("ZS=F",      "Soybeans",           "Commodity",  "Edible oil and feed prices"),
    ("GC=F",      "Gold",               "Commodity",  "Risk sentiment and domestic savings behaviour"),

    # --- Equity indices ---
    ("^GSPC",     "S&P 500",            "Equity",     "Global risk appetite"),
    ("^IXIC",     "Nasdaq Composite",   "Equity",     "Tech and growth sentiment"),
    ("^DJI",      "Dow Jones",          "Equity",     "US large-cap industrials"),
    ("^FTSE",     "FTSE 100",           "Equity",     "UK — significant RMG buyer"),
    ("^N225",     "Nikkei 225",         "Equity",     "Japan — major development partner and investor"),
    ("^HSI",      "Hang Seng",          "Equity",     "China proxy; Bangladesh's largest import source"),
    ("^BSESN",    "BSE Sensex",         "Equity",     "India — regional benchmark and trade partner"),
    ("^VIX",      "VIX (volatility)",   "Equity",     "Fear gauge; spikes precede EM outflows"),
]


def collect() -> dict:
    """Fetch last close and daily/weekly moves. Never raises."""
    try:
        import yfinance as yf
    except ImportError:
        return {"available": False, "reason": "yfinance not installed"}

    symbols = [s for s, *_ in INSTRUMENTS]
    meta = {s: (name, group, why) for s, name, group, why in INSTRUMENTS}

    try:
        data = yf.download(symbols, period="1mo", interval="1d",
                           progress=False, auto_adjust=True,
                           group_by="ticker", threads=True)
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}

    today = datetime.now(timezone.utc).date()
    rows, suppressed = [], []
    for sym in symbols:
        name, group, why = meta[sym]
        try:
            closes = data[sym]["Close"].dropna()
        except Exception:
            continue
        if len(closes) < 2:
            continue

        last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        week = float(closes.iloc[-6]) if len(closes) >= 6 else prev
        month = float(closes.iloc[0])

        # --- Is this series actually alive? ---------------------------------
        # Two failure modes, both silent, both seen in production:
        #   1. the last bar is weeks old and gets read as "today's close";
        #   2. the provider keeps re-serving one value while a live quote
        #      drifts away from it, so the difference looks like a market move.
        try:
            as_of = closes.index[-1].date()
            prev_date = closes.index[-2].date()
        except Exception:
            as_of = prev_date = None

        age_days = (today - as_of).days if as_of else None
        gap_days = (as_of - prev_date).days if as_of and prev_date else None

        # Look at the settled bars BEHIND the last one, not including it. The
        # August failure had a frozen history with a drifting live bar on top
        # (122.19, 122.19, 122.19, 123.93) — checking the tail *with* the live
        # bar sees three different values and waves it through. It is the
        # denominator that goes stuck, so that is what has to be inspected.
        history = [round(float(v), 6)
                   for v in closes.iloc[-(FROZEN_RUN_LENGTH + 1):-1]]
        frozen = len(history) == FROZEN_RUN_LENGTH and len(set(history)) == 1
        too_old = age_days is not None and age_days > MAX_BAR_AGE_DAYS

        stale = frozen or too_old
        reason = (f"feed frozen — the {FROZEN_RUN_LENGTH} closes behind the "
                  "latest bar are identical, so any change measured against "
                  "them is meaningless" if frozen else
                  f"last bar is {age_days} days old" if too_old else None)

        row = {
            "symbol": sym,
            "name": name,
            "group": group,
            "matters_because": why,
            "last": round(last, 4 if last < 10 else 2),
            "as_of": as_of.isoformat() if as_of else None,
            "stale": stale,
            "stale_reason": reason,
            # A gap wider than a long weekend is not a one-day move. Say what
            # the number actually measures instead of implying "today".
            "change_label": ("since " + prev_date.isoformat()
                             if gap_days and gap_days > 4 else "1d"),
            "change_pct_1d": None if stale else (
                round((last - prev) / prev * 100, 2) if prev else None),
            "change_pct_1w": None if stale else (
                round((last - week) / week * 100, 2) if week else None),
            "change_pct_1m": None if stale else (
                round((last - month) / month * 100, 2) if month else None),
        }
        rows.append(row)
        if stale:
            suppressed.append(f"{name} ({reason})")

    if not rows:
        return {"available": False, "reason": "no price series returned"}

    # Stale instruments must never headline the movers list — that is exactly
    # how a frozen feed became a lead story in August 2026.
    movers = sorted((r for r in rows
                     if r["change_pct_1d"] is not None and not r["stale"]),
                    key=lambda r: abs(r["change_pct_1d"]), reverse=True)
    return {
        "available": True,
        "instruments": rows,
        "biggest_movers_1d": movers[:6],
        "stale_instruments": suppressed,
        "by_group": {g: [r for r in rows if r["group"] == g]
                     for g in ("FX", "Rates", "Commodity", "Equity")},
    }
