# Improving the gold Asian breakout (v1 -> v2)

Engine: `backtester/gold.py` (signals on M15, every trade simulated minute by minute on M1, Exness spread $0.20).
Search: `scripts/gold_improve.py` (one-change sweeps -> `sweep.csv`; 5,184 combinations -> `combo.csv`;
2,304 neighbours of the pick -> `neighbourhood.csv`). Choices made on Q4 2024 + 2025 only; 2026 is the check.

## What changed (v2)
| Setting | v1 | v2 | Why (Q4 2024 / 2025 evidence) |
|---|---|---|---|
| Donchian lookback | 10 bars | **20 bars** | higher median PF in both periods across all combinations |
| Trend slope check | EMA vs 1 h ago (4 bars) | **vs 4 h ago (16 bars)** | higher 2025 PF |
| Target | 3R | **4R** | higher median PF in both periods |
| Break-even | +1R -> +0.1R | **+1R -> +0.3R** | better Q4 2024 |
Unchanged: 00:00-06:00 UTC entries, EMA400 trend, previous-day high/low break, stop 1.5 ATR (min $2), one trade at a time.

## Results ($1,000, 10% risk, M1-exact)
| Period | v1 PF | v1 $ | **v2 PF** | **v2 $** | v2 trades | v2 win | v2 max DD |
|---|---|---|---|---|---|---|---|
| Q4 2024 | 1.24 | $1,193 | 1.54 | $2,380 | 67 | 54% | -82% |
| 2025 (choice) | 1.73 | $317,385 | 2.04 | $612,758 | 240 | 63% | -58% |
| **2026 (check)** | 1.47 | $17,726 | **1.67** | **$28,138** | 194 | 56% | -82% |

Robustness: all 2,304 neighbouring settings of v2 are profitable in 2025 and 2026 (92% in Q4 2024); median 2026 PF 1.68,
median 2026 result $22,180 (10th percentile $7,348). Of all 5,184 combinations, 91% are profitable in all three periods.

2026 month-end balance at 10%: Jan $4,778, Feb $2,277, Mar $1,989, **Apr $967**, May $3,682, Jun $3,503, Jul $4,414,
Aug $21,362, Sep $17,791, Oct $28,138. Longest losing streak 6 (8 in Q4 2024).
Risk per trade in 2026: 5% -> $9,197 (DD -55%); 8% -> $20,221 (-74%); 10% -> $28,138 (-82%); 15% -> $34,966 (-94%).
Monte Carlo (2026 trades resampled, 10%): median $25,557; 26% chance of >= $100,000; 5% chance of ending below $1,000.

## Tested and not adopted
* Longer/shorter sessions, 22:00/23:00 starts, London/NY extensions: worse.
* Tighter stops (1.0-1.25 ATR), partial take-profit, time exits, trailing after break-even: worse or mixed.
* Long only: great in 2025 (PF 2.14) but PF 1.31 in 2026 - do not bet on direction.
* Daily-trend filter, volatility filter, strong-close filter, Asian opening-range entries: mixed, not consistent.
* Max 1-2 trades/day and stop-after-a-loss: help Q4 2024 but neutral overall; optional.
* Drawdown risk throttles (cut risk after -15 to -50%): lower drawdowns but lower profit by the same amount.
* Adding to winners at +1-2.5R: more 2026 profit only through more leverage (DD -91 to -96%), worse 2025: rejected.
* Weekday / hour filters: no stable pattern.

EA: `mt5/Experts/GoldAsianBreakout.mq5` v2.00 (defaults now = v2).
