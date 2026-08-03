# Finance Radar

> ### Where you left off — 3 August 2026
>
> **It is fully automatic now.** A Windows scheduled task named
> `FinanceRadar Daily` runs it every evening at **20:30 Bangladesh time**. You
> get a clickable notification about ten minutes later; clicking it opens the
> brief. There is nothing you need to do.
>
> To run it by hand anyway:
>
> ```powershell
> cd D:\Projects\FinanceRadar
> .\.venv\Scripts\python.exe run_daily.py
> ```
>
> **State:** 3 briefs stored (31 July, 1–2 August). 12 open predictions, 4 per
> day; the first falls due **8 August 2026**, which is when the memory loop
> starts scoring itself and a hit rate appears.
>
> **Things to know:**
> - The DSE is closed Friday and Saturday, so a run on those days replays
>   Thursday's session. The news is still fresh; only the market numbers repeat.
> - `--engine gemini_cli` also exists but its free daily quota runs out fast.
>   `claude_cli` is the default and is better anyway.
> - If a source ever "returns nothing", it is usually Google News rate-limiting.
>   There is already a serial retry for this in `radar/collect.py`.

An automated financial analyst that runs on your PC once a day.

Every evening it reads about 230 stories from 29 news sources, pulls the full
Dhaka Stock Exchange session and 20 global instruments, hands all of it to a
capable AI model with the instructions of a CFA-charterholder strategist, and
writes you a brief. It remembers what it concluded on previous days, and it
scores its own past predictions so you can see whether the analysis is any good.

It produces three things each day:

1. **The daily brief** — a web page built for reading, at
   `data/briefs/YYYY-MM-DD.html`. It opens in your browser and needs nothing
   installed. A plain-markdown copy is saved alongside it.
2. **A social post** — a short, plain-language post for Instagram, Facebook or
   LinkedIn, plus a 1080×1080 image card. Saved to `data/briefs/` and `data/cards/`.
3. **A memory** — every conclusion and every prediction goes into a database, so
   tomorrow's analysis knows what yesterday's said.
4. **The archive dashboard** at `data/dashboard.html` — every day you have ever
   run, in one searchable page with a calendar and charts. It rebuilds itself on
   every run and is what opens when a run finishes.

## Running it automatically

It is already scheduled. `install_schedule.ps1` registered a Windows task called
**FinanceRadar Daily** that fires at **20:30** every day, reading the time from
`schedule.daily_time` in `config.yaml`.

**Why 20:30.** It is the one moment when the most is knowable:

| At 20:30 Bangladesh time | Status |
|---|---|
| Dhaka Stock Exchange | closed at 14:30 — session settled and final |
| Bangladeshi business dailies | the day's reporting is filed |
| London | an hour from the close, Europe's day essentially done |
| New York | an hour into its session, direction visible |

The brief lands about 20:40, leaving the evening to read it. The trade-off is
that it cannot see the US close (02:00 Bangladesh time) or a Fed decision
(00:00) — those appear in the *next* day's brief, and the analyst's memory
carries the thread across the two days.

To change the time, edit `daily_time` in `config.yaml` and re-run
`install_schedule.ps1`. If you would rather read it over breakfast with a
complete global picture including the US close, set it to `07:00`: that brief
covers the whole of the previous day and misses nothing.

```powershell
.\install_schedule.ps1              # apply the time in config.yaml
.\install_schedule.ps1 -Remove      # stop the automation
Start-ScheduledTask -TaskName "FinanceRadar Daily"   # run it right now
```

If your PC is off at 20:30, `StartWhenAvailable` means the run happens the next
time you switch it on, so the record does not develop a hole.

**If a scheduled run ever seems to do nothing**, the usual cause is the task's
environment differing from your terminal's. Diagnose it with:

```powershell
.\.venv\Scripts\python.exe probe_env.py    # writes logs/probe.txt
```

That reports whether `claude` is findable and makes a live test call.

## The dashboard

`data/dashboard.html` is the home page for everything.

- **Search** across every brief you have ever produced — headlines, plain-English
  lines, scenarios, sectors, tickers. Type "cotton" and get every day cotton
  mattered, with the matching line shown.
- **A calendar** where each square is a day you ran the model, coloured by how
  the Dhaka market moved. Click any square to open that day.
- **Filters** by category and by time range, which re-scope every chart at once.
- **Charts**: daily turnover, sector performance, which themes dominate your
  briefs, and your prediction scorecard.
- **Light and dark themes**, and a table view under every chart.

A note on the colours. Market moves use **blue for up and red for down**, not the
green/red finance normally uses. Red/green is the most common form of colour
blindness, and in the calendar the colour is the only thing carrying the meaning.
The blue/red pair measures ΔE 21.6 under colour-blindness simulation where
green/red measures near zero. Every square also shows its actual number on hover
and in the table view, so the colour is never the only way to read it.

## It is built to teach you, not just inform you

The brief is designed for someone still learning finance, so it uses the real
technical vocabulary and then makes sure you actually learn it:

- **Every story has an "In plain English" line** — the same news told with zero
  jargon, so you always understand what happened before you tackle why.
- **The jargon decoder** explains 4–6 terms from that day's note: what it means
  in plain words, why it mattered *today*, and a one-line hook to make it stick.
- **Hover any dotted word** in the brief to see its definition without
  scrolling. The page finds and links those terms automatically.
- **Today's lesson** teaches one proper finance concept from scratch, using the
  day's real events as the worked example, and ends with a question to test
  yourself.

The aim is that after a year you have not just read the news, you have picked up
the vocabulary and the mental models that go with it.

---

## Getting started

You need to do **one** manual thing before this works: give it a model to think
with. Everything else is already built.

### Step 1 — Set up

Open PowerShell in this folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### Step 2 — Give it a brain

The system needs an AI model to do the analysis. Pick whichever suits you:

| Option | Cost | How |
|---|---|---|
| **Claude Code CLI** (recommended) | Free with your existing Claude plan | `npm install -g @anthropic-ai/claude-code` then run `claude` once and log in |
| **Gemini CLI** | Free tier | Run `gemini` once and log in with Google (it is already installed) |
| **Claude API** | ~$0.10–0.30 per day | Set an `ANTHROPIC_API_KEY` environment variable |

The first option is almost certainly what you want: you already pay for Claude,
so the daily run costs you nothing extra.

Once one of those works, `config.yaml` has `engine.name: auto`, which finds it
automatically.

### Step 3 — Test it

Check that data collection works without spending anything:

```powershell
.\.venv\Scripts\python.exe run_daily.py --dry-run
```

Then do a real run:

```powershell
.\.venv\Scripts\python.exe run_daily.py
```

### Step 4 — Make it automatic

```powershell
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1
```

This registers a Windows scheduled task for 19:30 daily (change `daily_time` in
`config.yaml` first if you want a different time). If your PC is off at that
hour, the run happens next time you switch it on.

---

## Why 19:30?

The DSE session has closed and settled, and the US market has just opened. You
get the complete Bangladeshi trading day and the start of the American one in a
single brief.

---

## What it reads

**Bangladesh (weighted highest):** The Daily Star (business and economy), The
Business Standard, Prothom Alo (English and Bangla), Dhaka Tribune, plus targeted
searches that catch Bangladesh Bank circulars, BSEC orders, NBR tariff changes,
budget news, RMG and export stories, energy and power tariffs, inflation data,
and IMF/World Bank/ADB activity.

**Global:** WSJ Markets, FT, The Economist, CNBC, MarketWatch, Yahoo Finance,
BBC, The Guardian, Investing.com, Al Jazeera.

**Central banks:** US Federal Reserve and ECB press releases.

**Dhaka Stock Exchange:** the full session — every traded instrument with open,
high, low, close, turnover and volume. From that it derives market breadth,
sector performance weighted by turnover, the top gainers and losers, the most
active stocks by money traded, and a blue-chip watchlist. Sector median P/E
ratios come from DSE's own published table.

**Global markets:** USD/BDT, the dollar index, USD/INR, EUR/USD, the US 10-year,
cotton, Brent, WTI, natural gas, wheat, soybeans, gold, and the major equity
indices including the Sensex and Hang Seng.

The instrument list is deliberately Bangladesh-shaped. Cotton is there because
RMG is most of your export earnings; wheat because you import it; crude and LNG
because they drive the subsidy bill and power tariffs; the Sensex because India
is your main competitor.

---

## The prediction scorecard

This is the part that makes the system worth running for a year rather than a week.

Every day the analyst must make two to four **falsifiable** calls — specific
enough to be proved wrong, with a deadline. Those go into the database as `open`.

Every following day, it is shown its own open predictions and required to judge
any whose evidence has arrived: `correct`, `wrong`, `partial` or `unclear`. When
it gets one wrong it has to name the reasoning error.

Over time this builds an honest hit rate, which appears in every brief. If the
rate drops below 45%, the analyst is told to be more conservative.

A forecast nobody scores is just an opinion. This scores them.

---

## Files

```
config.yaml            Settings. Edit this, not the code.
run_daily.py           The daily run.
setup.ps1              One-time setup.
install_schedule.ps1   Registers/removes the Windows scheduled task.
prompts/analyst.md     The analyst's instructions and output schema.
                       This is the highest-leverage file in the project —
                       change it to change how the analysis thinks.
radar/
  sources.py           The news feeds. Every one was tested live.
  collect.py           Fetches, cleans, deduplicates and ranks stories.
  dse.py               Dhaka Stock Exchange collector.
  dse_sectors.py       Ticker to sector mapping.
  markets.py           Global market data.
  store.py             The memory: runs, headlines, predictions.
  analyze.py           Builds the briefing packet, validates the response.
  engine.py            The swappable model adapters.
  html_render.py       Builds the readable HTML brief. Styling lives here.
  dashboard.py         Builds the archive dashboard from the database.
  dashboard_template.html
                       The dashboard's HTML, CSS and charts. Edit this to
                       restyle it or add a chart.
  render.py            Writes the plain markdown copy.
  card.py              Draws the social image.
  notify.py            Windows toast and Telegram.
data/
  radar.db             The memory database.
  briefs/              Daily briefs and social posts.
  cards/               Daily social images.
logs/                  What was sent to the model, and what came back.
```

---

## Useful commands

```powershell
# Collect data and show what would be sent, without calling the model
.\.venv\Scripts\python.exe run_daily.py --dry-run

# Redo a day you already ran
.\.venv\Scripts\python.exe run_daily.py --force

# Use a specific engine for one run
.\.venv\Scripts\python.exe run_daily.py --engine gemini_cli

# Run the scheduled task right now
Start-ScheduledTask -TaskName "FinanceRadar Daily"

# Stop the automation
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Remove
```

---

## Getting it on your phone

Windows notifications only reach you at your desk. To get the brief on your
phone, set up a free Telegram bot:

1. Message `@BotFather` on Telegram and send `/newbot`. Copy the token.
2. Message your new bot once, then open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find your chat id.
3. Put both into the `telegram` section of `config.yaml`.

You will then get the post and the image card pushed to you every evening.

---

## Tuning it

**The analysis feels shallow.** Edit `prompts/analyst.md`. That file is the whole
personality of the system. Add the sectors you care about, change the ranking
rules, demand more accounting detail.

**Too much jargon, or not enough.** Also `prompts/analyst.md`, in the "How you
write" section. It currently insists on using real technical terms and defining
them on first use. Loosen or tighten that as your vocabulary grows.

**You want the page to look different.** All the styling is the `CSS` block at
the top of `radar/html_render.py`. It is plain CSS with no build step.

**You want different stocks tracked individually.** Edit `BLUE_CHIPS` in
`radar/dse.py`.

**A company shows as "Unclassified".** Add it to `radar/dse_sectors.py`. About
87% of the exchange is classified; the rest are mostly small or newly listed.

**You want a different news source.** Add it to `radar/sources.py`. Check it
returns real XML first — several Bangladeshi outlets advertise RSS feeds that do
not actually work, and the ones that failed testing are listed at the bottom of
that file with the reason.

---

## Honest limitations

- **The AI can be wrong, and confidently so.** It is reading headlines and
  summaries, not full articles, and it cannot verify claims. The prediction
  scorecard exists precisely because you should not trust it blindly.
- **DSE's website has a broken SSL certificate.** The collector works around it
  by skipping verification for that one host. This is public read-only market
  data, so the risk is low, but you should know it is happening.
- **Google News feeds can return loosely related stories.** They are a safety net
  for policy news that has no proper RSS feed, not a precision instrument.
- **This is not investment advice**, and the social card says so on every image.
- **Sector mapping is maintained by hand** because DSE renders its industry pages
  in JavaScript, so they cannot be scraped server-side.
