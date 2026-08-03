"""Source registry.

Every feed in FEEDS was probed live on 2026-07-31 and returned parseable items.
Feeds that failed probing are recorded in DEAD_FEEDS at the bottom with the
reason, so nobody wastes time re-adding them.

weight  : how much the analyst should trust/prioritise this source (1-5).
scope   : 'bd' (Bangladesh), 'global', 'macro' (central banks/institutions).
tags    : free-form, used to help the analyst understand what a source covers.
"""

from dataclasses import dataclass, field


@dataclass
class Source:
    key: str
    name: str
    url: str
    scope: str
    weight: int = 3
    tags: list = field(default_factory=list)
    lang: str = "en"


FEEDS = [
    # ------------------------------------------------------------------
    # BANGLADESH — primary outlets
    # ------------------------------------------------------------------
    Source("ds_biz", "The Daily Star — Business", "https://www.thedailystar.net/business/rss.xml",
           "bd", 5, ["bd-business", "markets", "policy"]),
    Source("ds_econ", "The Daily Star — Economy", "https://www.thedailystar.net/business/economy/rss.xml",
           "bd", 5, ["bd-macro", "policy"]),
    Source("ds_top", "The Daily Star — Top News", "https://www.thedailystar.net/rss.xml",
           "bd", 4, ["bd-general", "politics"]),
    Source("tbs_econ", "The Business Standard — Economy", "https://www.tbsnews.net/economy/rss.xml",
           "bd", 5, ["bd-business", "bd-macro", "markets"]),
    Source("tbs_all", "The Business Standard — All", "https://www.tbsnews.net/rss.xml",
           "bd", 4, ["bd-general", "bd-business"]),
    Source("pa_en", "Prothom Alo (English)", "https://en.prothomalo.com/feed",
           "bd", 4, ["bd-general", "politics", "bd-business"]),
    Source("pa_bn", "Prothom Alo (Bangla)", "https://www.prothomalo.com/feed",
           "bd", 4, ["bd-general", "politics"], lang="bn"),
    Source("dt", "Dhaka Tribune", "https://www.dhakatribune.com/feed/",
           "bd", 3, ["bd-general", "bd-business"]),

    # ------------------------------------------------------------------
    # BANGLADESH — policy / regulator / market, via Google News queries.
    # These act as a safety net: they surface Bangladesh Bank circulars,
    # BSEC orders, NBR tariff changes and budget news even when they break
    # on sites that have no usable RSS feed of their own.
    # ------------------------------------------------------------------
    Source("gn_dse", "DSE / Bangladesh stock market",
           "https://news.google.com/rss/search?q=%22Dhaka+Stock+Exchange%22+OR+DSEX+OR+%22Bangladesh+stock+market%22+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["dse", "markets", "equities"]),
    Source("gn_bb", "Bangladesh Bank / monetary policy",
           "https://news.google.com/rss/search?q=%22Bangladesh+Bank%22+monetary+policy+OR+reserves+OR+circular+OR+remittance+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["central-bank", "policy", "fx", "remittance"]),
    Source("gn_policy", "BD government policy / budget / tax",
           "https://news.google.com/rss/search?q=Bangladesh+government+policy+OR+budget+OR+tariff+OR+NBR+OR+%22interim+government%22+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["policy", "fiscal", "tax", "government"]),
    Source("gn_bsec", "BSEC / securities regulation",
           "https://news.google.com/rss/search?q=BSEC+Bangladesh+securities+OR+listing+OR+IPO+when:3d&hl=en-US&gl=US&ceid=US:en",
           "bd", 4, ["regulator", "equities", "ipo"]),
    Source("gn_infl", "BD inflation / GDP / statistics",
           "https://news.google.com/rss/search?q=Bangladesh+inflation+OR+CPI+OR+GDP+OR+%22trade+deficit%22+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["bd-macro", "inflation"]),
    Source("gn_rmg", "RMG / garments / exports",
           "https://news.google.com/rss/search?q=Bangladesh+garment+OR+RMG+OR+BGMEA+OR+export+earnings+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["rmg", "exports", "textiles"]),
    Source("gn_energy", "BD energy / gas / power tariffs",
           "https://news.google.com/rss/search?q=Bangladesh+LNG+OR+gas+price+OR+%22power+tariff%22+OR+fuel+price+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 4, ["energy", "utilities", "inflation"]),
    Source("gn_imf", "BD & IMF / World Bank / ADB",
           "https://news.google.com/rss/search?q=Bangladesh+IMF+OR+%22World+Bank%22+OR+ADB+loan+OR+tranche+when:7d&hl=en-US&gl=US&ceid=US:en",
           "bd", 4, ["multilateral", "sovereign", "policy"]),
    # Mobile financial services are how most Bangladeshis actually touch the
    # financial system, and none of the feeds above reliably surface them: a
    # governor's announcement about offline MFS matches neither "monetary
    # policy" nor "circular".
    Source("gn_mfs", "MFS / fintech / digital payments",
           "https://news.google.com/rss/search?q=bKash+OR+Nagad+OR+%22mobile+financial+services%22+OR+%22digital+bank%22+OR+%22agent+banking%22+Bangladesh+when:2d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["fintech", "mfs", "payments", "financial-inclusion"]),
    # Banking-sector health drives a third of DSE turnover and is the main
    # channel through which policy reaches the real economy.
    Source("gn_banks", "BD banking sector health",
           "https://news.google.com/rss/search?q=Bangladesh+%22non-performing+loan%22+OR+%22defaulted+loan%22+OR+%22bank+merger%22+OR+%22Islamic+bank%22+OR+recapitalisation+when:3d&hl=en-US&gl=US&ceid=US:en",
           "bd", 5, ["banking", "credit", "npl", "policy"]),

    # ------------------------------------------------------------------
    # GLOBAL MARKETS & FINANCE
    # ------------------------------------------------------------------
    Source("wsj_mkt", "WSJ — Markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
           "global", 5, ["markets", "equities", "rates"]),
    Source("wsj_world", "WSJ — World News", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews",
           "global", 4, ["geopolitics"]),
    Source("mw_top", "MarketWatch — Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories",
           "global", 4, ["markets", "equities"]),
    Source("mw_pulse", "MarketWatch — Market Pulse", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
           "global", 4, ["markets", "intraday"]),
    Source("cnbc_top", "CNBC — Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html",
           "global", 4, ["markets", "business"]),
    Source("cnbc_econ", "CNBC — Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html",
           "global", 5, ["macro", "rates", "inflation"]),
    Source("cnbc_fin", "CNBC — Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html",
           "global", 4, ["banks", "finance"]),
    Source("yf", "Yahoo Finance", "https://finance.yahoo.com/news/rssindex",
           "global", 3, ["markets", "equities"]),
    Source("ft", "Financial Times — Home", "https://www.ft.com/rss/home",
           "global", 5, ["markets", "macro", "geopolitics"]),
    Source("econ_fin", "The Economist — Finance & Economics",
           "https://www.economist.com/finance-and-economics/rss.xml",
           "global", 5, ["macro", "analysis"]),
    Source("bbc_biz", "BBC — Business", "https://feeds.bbci.co.uk/news/business/rss.xml",
           "global", 3, ["business", "macro"]),
    Source("guard_biz", "The Guardian — Business", "https://www.theguardian.com/uk/business/rss",
           "global", 3, ["business", "macro"]),
    Source("inv_news", "Investing.com — News", "https://www.investing.com/rss/news.rss",
           "global", 3, ["markets", "commodities"]),
    Source("inv_fx", "Investing.com — Forex", "https://www.investing.com/rss/news_1.rss",
           "global", 3, ["fx", "currencies"]),
    Source("ajz", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml",
           "global", 3, ["geopolitics", "south-asia", "energy"]),

    # ------------------------------------------------------------------
    # MACRO / CENTRAL BANKS — these move everything downstream
    # ------------------------------------------------------------------
    Source("fed", "US Federal Reserve — Press Releases",
           "https://www.federalreserve.gov/feeds/press_all.xml",
           "macro", 5, ["central-bank", "rates", "us"]),
    Source("ecb", "European Central Bank — Press",
           "https://www.ecb.europa.eu/rss/press.html",
           "macro", 4, ["central-bank", "rates", "eu"]),
]


# Feeds that were probed and did NOT work — kept so they are not retried blindly.
DEAD_FEEDS = {
    "https://www.newagebd.net/rss": "404 — New Age has no working public RSS path found",
    "https://thefinancialexpress.com.bd/feed": "returns HTML, not XML (JS-rendered site)",
    "https://businesspostbd.com/rss": "404",
    "https://bdnews24.com/feed": "404 — bdnews24 dropped public RSS",
    "https://feeds.reuters.com/reuters/businessNews": "DNS gone — Reuters retired public RSS",
    "https://www.imf.org/en/News/RSS?language=eng": "403 — IMF blocks non-browser clients",
    "https://www.sec.gov/rss/litigation/litreleases.xml": "403 — SEC requires a declared User-Agent contact",
    "https://www.worldbank.org/en/news/all?format=rss": "malformed XML",
    "https://bonikbarta.com/feed": "returns HTML, not XML",
    "https://www.jugantor.com/feed/rss.xml": "access denied",
    "https://samakal.com/feed": "returns HTML, not XML",
}


def by_scope(scope: str):
    return [s for s in FEEDS if s.scope == scope]


def all_feeds():
    return list(FEEDS)
