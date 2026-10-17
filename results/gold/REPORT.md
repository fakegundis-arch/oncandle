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

---
# v3: drawdown control + diversification

## Why v2 suffered
Feb-Apr 2026 gold turned extremely volatile (median stop $19-23 vs ~$12 normally) and breakouts kept failing; Dec 2024
looked the same. v2 at 10%: $1,000 -> $4,778 (Jan) -> $967 (Apr) -> $28,138 (Oct), max DD -82%.

## Step 1 - drawdown filters on the gold strategy (`scripts/gold_v3.py`, 2,016 variants, chosen on Q4 2024 + 2025)
Added to v2:
1. **Daily trend:** buy only if yesterday closed above the D1 EMA(20); sell only if below.
2. **Volatility cap:** skip if ATR(14) > 2 x its 100-bar median.
3. **Equity-curve filter:** every signal is traded on paper; a real trade is placed only if the last 10 paper trades
   sum to >= -2R (the strategy "sits out" its own losing streaks and comes back when the paper trades recover).
4. **Weekly stop:** after this week's real trades lose 2R, no new trades until next week.

| Gold alone, 10% risk | Q4 2024 | 2025 | 2026 (check) |
|---|---|---|---|
| v2 | $2,380, DD -82% | $612,758, DD -58% | $28,138, DD -82% |
| **v3** | **$9,450, DD -34%** | $125,692, **DD -42%** | **$30,750, DD -64%** (PF 2.18, 100 trades) |
The 144 neighbouring variants (d1 trend 20, equity filter 5-10 trades, any threshold / weekly cap) are all profitable in
all three periods; their median 2026 result is $9,929 (DD -66%), so v3's 2026 is at the good end.
Lower drawdowns, but one strategy alone still had -64% in 2026 at 10% risk.

## Step 2 - portfolio (`scripts/gold_v3_portfolio.py`; weights chosen on 2025 + Q4 2024 with a 35% drawdown budget)
Monthly R correlation with gold v3: Trump-tariff Dow -0.03, BTC H1 Run Fade -0.14, gold H4 MACD +0.35.

| v3 portfolio | Risk per trade |
|---|---|
| Gold Asian breakout v3 (`GoldAsianBreakoutV3.mq5`) | 7% |
| Truth Social tariff posts -> Dow (`results/truth/REPORT.md`, no EA yet) | 4% |
| BTC H1 Run Fade (`RunFade.mq5`) | 5% |
| Gold H4 MACD + EMA100 (`OnCandleTrend.mq5`, MACD strategy) | 4% |

| $1,000 | Q4 2024 | 2025 | **2026 (check)** |
|---|---|---|---|
| v2 at 10% | $2,380 / DD -82% | $612,758 / -58% | $28,138 / **-82%** |
| **v3 portfolio** | $5,746 / DD -31% | $176,034 / -34% | **$38,694 / DD -33%** |
| v3 portfolio without the Truth Social leg | $6,404 / -26% | $94,737 / -37% | $25,720 / -35% |
| gold v3 alone at 7% | $5,339 / -25% | $40,452 / -31% | $15,649 / -50% |

2026 month-end balance (full v3 portfolio): Jan $4,678, Feb $4,086, Mar $4,735, Apr $4,061, May $6,745, Jun $7,244,
Jul $8,316, Aug $32,392, Sep $38,351, Oct $38,694.
Lowest balance $1,120. Up to ~21% of equity can be at risk at once when all four strategies hold trades.
Note: a simulator bug (a trade opened and stopped in the same minute was not counted) was found and fixed; all numbers
above are after the fix.
