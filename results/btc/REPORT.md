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
