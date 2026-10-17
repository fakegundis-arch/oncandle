# BTC H1 Run Fade v2

Engine: `backtester/btcfade.py` (signals on H1, every trade simulated minute by minute on M1; $20 spread).
Search: `scripts/btc_fade_improve.py` (one-change sweep -> `sweep.csv`, 1,944 combinations -> `combo.csv`,
243 neighbours of the pick -> `neighbourhood.csv`). Chosen on Q4 2024 + 2025; 2026 is the check.
The rebuilt engine reproduces v1 exactly (35 / 121 / 79 trades, PF 2.30 / 1.82 / 1.78).

## Changes (v2)
| Setting | v1 | v2 |
|---|---|---|
| Stop | 4 x ATR | **3 x ATR** |
| Max hold | 30 bars | **48 bars** |
| Trend rule | none | **only fade runs that go with the EMA(50) trend** (buy after a red run only if the close is below EMA50, sell after a green run only if above; counter-trend pullbacks are skipped) |
Unchanged: H1, 4 same-colour candles, combined move >= 2.5 x ATR(14), target 0.5 x ATR, one trade at a time.

## Results ($1,000)
| Period | Version | Trades | Win | PF | Avg R | 10% risk | 20% risk |
|---|---|---|---|---|---|---|---|
| Q4 2024 | v1 | 35 | 94% | 2.30 | +0.067 | $1,249 (DD -12%) | $1,521 (-24%) |
| | **v2** | 34 | 94% | 2.67 | +0.098 | $1,375 (-12%) | $1,828 (-25%) |
| 2025 | v1 | 121 | 93% | 1.82 | +0.053 | $1,798 (-16%) | $2,891 (-31%) |
| | **v2** | 115 | 91% | 1.75 | +0.065 | $1,978 (-22%) | $3,359 (-42%) |
| **2026** | v1 | 79 | 92% | 1.78 | +0.051 | $1,446 (-19%) | $1,942 (-36%) |
| | **v2** | 75 | 93% | **2.33** | **+0.089** | **$1,878** (-19%) | **$3,253** (-36%) |

Robustness: all 243 neighbouring settings (min move 2.25-2.75, stop 2.5-3.5, target 0.4-0.6, EMA 30-100,
hold 36-72) are profitable in all three periods; median PF 3.0 / 1.67 / 1.68.
Of all 1,944 combinations, 35% are profitable in all three periods.
Spread: at $30-60 the 2026 PF is 1.92 ($1,663 at 10%). Longest losing streak 2; average win +0.167R, loss -1R;
median hold 0.8 h. 2026 month-end at 10%: Jan $851, Feb $972, Mar $950, Apr $1,102, May $1,279, Jun $1,336,
Jul $1,576, Aug $1,798, Sep $1,758, Oct $1,878.

## Tested and not adopted
30-min / 2-h / 4-h candles, 3-, 5-, 6-candle runs, bigger targets (0.75-2 ATR), confirmation candle, trading only
with counter-trend runs, hour and weekend filters, volatility filters, break-even / trailing (never reached before the
target), shorts only (great in 2025-26, weak in Q4 2024).

EA: `mt5/Experts/RunFadeV2.mq5` (BTCUSD H1; defaults = v2, risk 5%).

---
# Risk-reward test ("v3" candidate: 1:1 to 1:4 instead of a small target)

`scripts/btc_fade_rr.py` -> `rr_grid.csv` (672 variants: stop 0.5-3 ATR x RR 0.17-4 x break-even x hold x trend filter x
min move) and a follow-the-run version (trade WITH the run, RR 1-4, 1,344 variants -> `follow_grid.csv`).

| Fade, risk:reward | Median PF Q4 2024 / 2025 / 2026 | Median 2026 win rate | Profitable in all 3 periods |
|---|---|---|---|
| **1:0.17 (v2 style)** | 1.51 / 1.12 / 1.67 | 91% | **58%** |
| 1:0.5 | 1.07 / 1.19 / 1.21 | 70% | 56% |
| 1:1 | 0.85 / 1.10 / 1.05 | 52% | 25% |
| 1:1.5 | 0.80 / 1.15 / 0.99 | 47% | 12% |
| 1:2 | 0.74 / 1.15 / 1.02 | 45% | 20% |
| **1:3** | 0.67 / 1.09 / 1.02 | 44% | **7%** |
| 1:4 | 0.64 / 1.15 / 0.88 | 44% | 4% |
Example, v2 signals with a 1-ATR stop and 3-ATR target: PF 0.55 / 1.10 / 0.98.
Follow the run instead (RR 1-4): 5% of variants profitable in all periods, median 2026 PF 0.82; the best by 2025 lost
in 2026 (PF 0.65).

**Conclusion:** the edge is a small, fast snap-back after a stretched run; bigger targets are rarely reached and the
win rate collapses faster than the payoff grows. No v3 adopted; v2 (small target, wide stop) stays.
