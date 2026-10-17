# Non-trend strategies (target: $1,000 -> $100,000 in 2026)

Code: `backtester/alt.py`, `scripts/run_alt.py`. 11 markets, Oct 2024 - Oct 2026, Exness spreads x1.5-2.
Chosen on 2025 (+ Q4 2024), judged on 2026. $ figures at 10% risk per trade.

| Family | Settings | Profitable both years | Best 2026 (hindsight) | Verdict |
|---|---|---|---|---|
| **Pairs mean reversion** (rolling-OLS spread z-score, 10 pairs, M15/H1) | 888 | 7.5% | $1,676 | rejected |
| **RSI(2) snap-back** (M15/H1/H4, with/without SMA200 filter) | 4,608 | 11.8% | $3,387 | small edge on gold H4 only |
| **Gap fade** (fade the open after a trading break back to the prior close) | 315 | 31.7% with 2x spread | - | **rejected: needs the first Sunday quote at a normal spread** |
| **Hour-of-day seasonality** (slots with t >= 2.5 in 2025, confirmed in Q4 2024) | 3 slots | 2 of 3 | small | too few trades |

Notes
* Pairs: a first version reused a moving hedge ratio inside open trades (a look-ahead that showed $1,000 -> $585M);
  fixed by freezing the ratio at entry and using a past-only rolling regression residual. After the fix: no edge.
* Gap fade: USDJPY looked excellent (94% of settings profitable, PF 1.84 / 2.35), but with 5x spread at the Sunday open
  only 22% survive (PF 0.79 in 2026), and entering 15 min later kills it (0%). Same for USDCAD, GBPUSD, EURUSD.
* RSI(2) on gold H4 (RSI(2) < 3 buy / > 97 sell, stop 3-5 ATR, exit on a close through SMA5): 76% wins,
  PF 3.2-3.9 in 2025 and 1.5-1.6 in 2026, but only ~33 trades a year: +15-22% in 2026 at 10% risk, DD -12 to -15%.

**Conclusion:** nothing here comes close to 100x; no tested setting even reaches 4x in 2026 with hindsight.
The gold Asian breakout (`results/deep/REPORT.md`) remains the strongest strategy found in this project.
