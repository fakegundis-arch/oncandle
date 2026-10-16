# Can $1,000 become $20,000 in 2026? An honest search

**Method:** 1,159 strategy variants with a real edge in 2025, covering the 12 trend systems on H1/H4, all
mean-reversion families on M15/H1/H4, and Trend Rider v2 on M1, across BTC, gold, Nasdaq and Dow. For each one,
the growth-optimal (Kelly) bet size was found on **2025 only**. Each was then traded through **2026** at half that size,
chosen without seeing 2026. Exness spreads are included.

## Results
* **No variant reached 20x in 2026, even with hindsight.** The best of all 1,159 was 13.7x, with a 40% drawdown.
* Best single pick by 2025 data (Ichimoku, gold H1): **$1,000 -> $2,117**, with a 75% drawdown.
* Top 50 picks by 2025: median **1.4x** in 2026, and **42% lost money**.
* Splitting $1,000 across the top-K picks from 2025 gave **$2,100 - $3,500**.

## Most robust family: trend following on gold H4
MACD + EMA Filter: 8/8 variants profitable in 2026 (median 3.1x at half-Kelly, median drawdown -71%).
PSAR + EMA: 7/8 profitable.

Gold H4, MACD(12,26,9) + EMA100, stop 3x ATR, no trail. 2026: 54 trades, 50% wins, +0.24R average.

| Risk per trade | $1,000 becomes (2026) | Max drawdown |
|---|---|---|
| 2% | $1,279 | -7% |
| 5% | $1,787 | -18% |
| 10% | $2,881 | -33% |
| 20% | $5,883 | -57% |
| 25% | $7,596 | -67% |
| 35% | $10,621 | -81% |
| 50% | $11,655 | -93% |

Risking more than ~35% per trade barely adds return and drives the drawdown toward 100%. Within this
search, 20x in 2026 was not reachable at any risk level.

EA: `mt5/Experts/OnCandleTrend.mq5` on XAUUSD H4 with Strategy = MACD + EMA Filter, MacdTrend = 100,
StopATR = 3, TrailATR = 0.
