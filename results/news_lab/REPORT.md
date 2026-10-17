# News lab: news strategies built from scratch (target: $1,000 -> $100,000 in 2026)

Code: `backtester/news_lab.py`, `scripts/run_news_lab.py` (`--surprise` for the surprise-size grid).
Events: every Forex Factory medium/high release of USD, EUR, GBP, JPY, CAD (Oct 2024 - Oct 2026, 1,505 events;
same-minute releases merged), traded on the markets they move (USD -> all 11, EUR -> EURUSD, GBP -> GBPUSD,
JPY -> USDJPY, CAD -> USDCAD). All distances in units of the pre-release M1 true range. Costs: Exness spread x5 if
the entry is < 3 min after the release, x3 if < 10 min, otherwise x2. Next-bar-open entries, stop-first intrabar.

## Families tested
* **cont** - follow the release spike after 1-60 min; **fade** - fade it; **news** - trade FF's verdict direction;
  **retest** - wait for a 50% retrace of the spike and join it.
* Filters: spike size 0-10 units; spike agrees / disagrees with the verdict; all / USD / high / tier-1 events.
* **Surprise size** (second grid): (actual - forecast) / std of that indicator's past surprises (FF history from 2022),
  trade only surprises >= 1/2/3 std.
* Stops 3-24 units or 0.75 x spike; targets 1-5R with/without breakeven, or trailing stops; holds 30 min / 4 h / 24 h.
* Each market alone, all markets of the event (risk split), or the largest spike only.
* **2,265,300 + 171,300 settings** with enough trades.

## Results
| Test | Result |
|---|---|
| Settings profitable in both 2025 and 2026 | 3.9% (main grid), 4.7% (surprise grid) - about what luck gives |
| Median profit factor | 0.60 / 0.63 - spreads around the release eat the moves |
| Top 100 clusters chosen on 2025 (+Q4 2024) | only 32% profitable in 2026; the surprise grid's top 50: 38% |
| Best 2025 picks at their own best risk | $1,000 -> $1.47M in 2025, then -> $0.05 in 2026 |
| **Best 2026 result with full hindsight (10% risk)** | **$52,983** - and that same setting lost 99% in 2025 |
| Settings reaching $100,000 in 2026 | **0 of 2.4 million** |

Best markets: Nasdaq, gold, Dow (10-16% of settings profitable in both years vs 1-3% for FX, oil, silver).
The few setups that held up when chosen on 2025 (e.g. gold: fade a spike that went against a >= 1 std surprise,
15 min after the release; PF 1.61 -> 1.49) trade only ~15 times a year: worth a few hundred dollars, not 100x.

**Conclusion:** no news strategy found here can honestly turn $1,000 into $100,000 in 2026; the target is not
reachable even with hindsight. News v2 (`results/news_open/REPORT.md`) remains the best news strategy.
