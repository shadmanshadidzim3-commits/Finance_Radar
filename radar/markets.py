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

warnings.filterwarnings("ignore")

# (yahoo symbol, display name, group, why it matters for Bangladesh)
INSTRUMENTS = [
    # --- Currencies & rates: the taka's external pressure gauges ---
    ("BDT=X",     "USD/BDT",            "FX",         "Direct taka pressure; import costs and remittance value"),
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

    rows = []
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
        rows.append({
            "symbol": sym,
            "name": name,
            "group": group,
            "matters_because": why,
            "last": round(last, 4 if last < 10 else 2),
            "change_pct_1d": round((last - prev) / prev * 100, 2) if prev else None,
            "change_pct_1w": round((last - week) / week * 100, 2) if week else None,
            "change_pct_1m": round((last - month) / month * 100, 2) if month else None,
        })

    if not rows:
        return {"available": False, "reason": "no price series returned"}

    movers = sorted((r for r in rows if r["change_pct_1d"] is not None),
                    key=lambda r: abs(r["change_pct_1d"]), reverse=True)
    return {
        "available": True,
        "instruments": rows,
        "biggest_movers_1d": movers[:6],
        "by_group": {g: [r for r in rows if r["group"] == g]
                     for g in ("FX", "Rates", "Commodity", "Equity")},
    }
