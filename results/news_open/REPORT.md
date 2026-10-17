# News bias -> trade the New York open (USD medium + high impact)

**How it reads the news:** every USD medium/high release from the previous NY close (16:00 ET) to the NY open (09:30 ET)
gets Forex Factory's own verdict (`actualBetterWorse`: better / worse than forecast for USD). High impact counts x2.
The sum is the day's USD score; |score| >= threshold sets the USD bias. 489 trading days were checked (Nov 2024 - Oct 2026);
130 days had |score| >= 2.

**How it trades:** no trade at the release. At the NY open it watches 11 markets (gold, silver, EURUSD, GBPUSD, USDJPY,
USDCAD, BTC, Nasdaq, Dow, S&P 500, oil) for 5/15/30 min and only enters markets already moving in the news
direction (bullish USD -> gold/EUR/GBP/BTC/indices/oil down, USDJPY/USDCAD up), by momentum or pullback entry.
Stop beyond the observation range, targets 1:1.5 / 1:2 / 1:3 or hold to 16:00 ET, break-even on/off, best single
market or all of them. 10% risk per day. Exness spread + equal slippage. 1,728 settings per mode, M1 data.

## Results
| Mode (same settings grid) | Settings profitable 2025 | 2026 | both years | Median PF 2025 | Median PF 2026 |
|---|---|---|---|---|---|
| **Trade WITH the news (the strategy)** | 10% | 3% | **1%** | 0.55 | 0.42 |
| Control: ignore news, trade whatever moves | 2% | 0% | 0% | 0.55 | 0.50 |
| Control: trade AGAINST the news | 20% | 19% | 8% | 0.72 | 0.67 |

* Same settings: "with the news" beat "ignore news" in only 51% (2025) / 42% (2026) of settings - a coin flip.
* The top 20 news settings by 2025 (PF up to 2.16) were **all unprofitable in 2026** (median PF 0.51).
* Raw check: USD news direction vs the open-to-close move of each market agreed only 45-55% of the time
  (correlations -0.12 to +0.14). By 09:30 the news is already priced in.

**Verdict: no edge.** The news verdict carries no usable information by the NY open. If anything, the open tends to
reverse the pre-open news move (the "against" control does least badly), but that is not robust either.
