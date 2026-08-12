# Known errors in your own past briefs

Everything here is a figure you previously published that turned out to be
wrong. Your memory still contains the original claims, so read this first and
treat these corrections as overriding anything you remember saying.

Do not repeat a corrected figure. Do not build a trend, a connection or a
prediction on one. If a past conclusion depended on a corrected number, say
plainly that the earlier read was based on bad data rather than quietly
dropping it — the record is supposed to be honest, not tidy.

---

## USD/BDT, 6–11 August 2026 — the taka never surged

**What you published:** daily "surges" in the taka of +1.25% (6 Aug), +1.03%
(7 Aug), +1.61% (8 and 9 Aug), +1.42% (10 Aug) and +1.09% (11 Aug), reaching
Tk 124.16. On 8 August this was the lead story: "USD/BDT surges 1.61% in a
single session to Tk 124.16 as dollar demand overwhelms bank reserves."

**What actually happened:**

| Date | You published | Actual |
|---|---|---|
| 6 Aug | 123.71, +1.25% | 122.20, +0.03% |
| 7 Aug | 123.41, +1.03% | 122.21, +0.01% |
| 8 Aug | 124.16, +1.61% | 121.86, −0.29% (Saturday, market closed) |
| 9 Aug | 124.16, +1.61% | 121.86, unchanged (Sunday, market closed) |
| 10 Aug | 123.93, +1.42% | 123.59, +1.42% (the one real move) |
| 11 Aug | 123.19, +1.09% | 123.41, −0.15% |

**The taka did not reach Tk 124 at any point.** Its high in that window was
Tk 123.59 on 10 August. There was exactly one genuine move — roughly +1.4% on
10 August — and it was not the 8 August "surge" you led with.

**Cause:** USD/BDT came from a single feed (Yahoo `BDT=X`) whose daily series
froze at 122.19 for five consecutive runs while its live quote drifted. The
code differenced the two and published the gap as a daily move. Nothing
cross-checked it. This is now fixed: the taka is the median of several
independent providers, the spread between them is reported, and the change is
measured against our own last stored reading.

**Consequences you must carry forward:**

- Any narrative of "sustained taka depreciation" or "accelerating dollar
  scarcity" built on 6–9 August FX data was built on nothing. The underlying
  pressures may still be real, but the FX evidence you cited was not.
- Two predictions ("USD/BDT above Tk 124.00", made 4 and 7 August) were scored
  **correct** against the false Tk 124.16. They have been re-scored **wrong**.
  Your hit rate was never 61.5%; it is 46.2%.
- Open predictions keyed to Tk 124.20–124.80 were made under this false
  premise. Judge them against corroborated data only, and expect them to fail.

---

## Recurring reasoning error — mean reversion on DSE turnover

Five of your seven wrong calls are the same call: DSE turnover or insurance
turnover share will fall back below a threshold within a few sessions. It
kept not happening. You have been betting on a rally cooling off and the
market has repeatedly declined to cool.

Before making another turnover-reversion call, state what is different this
time. If nothing is, do not make it.
