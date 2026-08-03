# Running it in the cloud, for free

This makes the brief appear in your inbox every day whether your laptop is on,
asleep, or switched off — at no cost.

## What makes it free

| Piece | Free because |
|---|---|
| The computer that runs it | GitHub Actions gives a private repo **2,000 minutes a month**. This job uses about 5 a day, so ~150. |
| The AI that analyses the news | A **Gemini API key** from Google AI Studio has a free daily quota far larger than one run. |
| Storage and memory | The database and briefs are committed back to your own repo after each run. |
| Email | Gmail's SMTP is free. |

Total: **Tk 0 per month.**

---

## The five things you need to do

Everything else is already built and committed.

### 1. Get a free Gemini API key

Go to **https://aistudio.google.com/apikey**, sign in with your Google account,
and click **Create API key**. Copy it — it starts with `AIza`.

### 2. Get a Gmail App Password

Your normal Gmail password will not work; Google blocks it for apps.

1. Go to **https://myaccount.google.com/security**
2. Turn on **2-Step Verification** if it is not already on
3. Search that page for **App passwords**
4. Create one called `Finance Radar` and copy the 16 characters

### 3. Create a private GitHub repository

At **https://github.com/new**, name it `FinanceRadar`, choose **Private**, and
do **not** add a README or .gitignore (this project already has both).

### 4. Push this project to it

In PowerShell, from `D:\Projects\FinanceRadar` — replace `YOUR-USERNAME`:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/FinanceRadar.git
git push -u origin main
```

### 5. Add your three secrets

On GitHub: your repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Add these three, named exactly:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | the key from step 1 |
| `GMAIL_ADDRESS` | your Gmail address |
| `GMAIL_APP_PASSWORD` | the 16 characters from step 2 |

Secrets are write-only — nobody, including you, can read them back afterwards,
and they never appear in the logs.

---

## Test it before waiting a day

Repo → **Actions** tab → **Finance Radar — daily brief** → **Run workflow**.

It takes about five minutes. When it finishes you should have an email. If you
don't, open the run and read the log — the failing step says why.

After that it runs by itself at **14:30 UTC, which is 20:30 in Dhaka**. GitHub
queues scheduled jobs, so it can start a few minutes late; that is normal and
not a fault.

---

## Two things to expect

**The Dhaka Stock Exchange might not answer.** GitHub's computers are in the
United States, and `dsebd.org` may not serve them. If that happens the brief
still runs — the news, the global markets and the analysis are all unaffected —
but the DSE section will say the data was unavailable. **The first run tells
us.** If it is blocked, keep your laptop run for the market data and let the
cloud run cover the days your laptop is off.

**The analysis will be a little weaker than Claude's.** Gemini's free tier is
good, not equal. If you later decide the quality matters more than the money,
add an `ANTHROPIC_API_KEY` secret and change `--engine gemini_api` to
`--engine anthropic_api` in `.github/workflows/daily.yml`. That costs roughly
**Tk 370–550 a month** at this packet size.

---

## Reading it

The email contains the whole brief, so your phone is enough. To open the full
dashboard, download it from the **Actions** run (the `brief` artifact), or pull
the repo on any machine and open `data/dashboard.html`.
