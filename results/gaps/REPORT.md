# Filling the gaps: range-pair mean reversion, true pairs, GBPJPY/USDJPY trend, London ORB

New data: EURCHF, AUDNZD, EURGBP, AUDUSD, NZDUSD, GBPJPY M1 (Dukascopy, Oct 2024 - Oct 2026).
Spreads: Exness Standard estimates (EURCHF 2.0, AUDNZD 3.0, EURGBP 1.5, AUDUSD 1.2, NZDUSD 1.8 pips, GBPJPY 2.5) x1.5.
Code: `backtester/gaps.py`, `scripts/run_gaps.py`. Chosen on 2025 (+ Q4 2024), judged on 2026, $ at 10% risk.

| Test | Settings | Profitable both years | Best 2026 (hindsight) | Verdict |
|---|---|---|---|---|
| Mean reversion (Bollinger / RSI / session-TWAP fade; Asian / London / all day; news filter on/off; 7 pairs, M15/H1) | 16,074 | 1.2% | $4,624 | rejected on a Standard account |
| Pairs with rolling cointegration (ADF) gate (AUDUSD/NZDUSD, EURUSD/GBPUSD, EURCHF/EURUSD, EURGBP/EURUSD) | 584 | 0.3% | $1,804 | rejected; the gate cuts trades but not losses |
| Trend following, 12 classic strategies (GBPJPY, USDJPY, EURGBP, AUDUSD; H1/H4/D1) | 1,446 | 5.3% | $2,369 | rejected; USDJPY H1/H4 slightly positive (Ichimoku, KAMA H4) but weak |
| London-open range breakout (GBPJPY, GBPUSD, EURGBP, EURUSD, USDJPY) | 360 | 1.7% | $729 | rejected |

The news filter (skip 30 min before to 90 min after high-impact news of either currency) did not change the results.

## Cost check: the range pairs do mean-revert, but the Standard spread eats it
Bollinger / TWAP fades with a 3-5 ATR stop and the news filter, share of settings profitable in both years:

| Pair (M15) | no spread | 0.5x Standard (~ Raw/Zero account) | 1.5x Standard |
|---|---|---|---|
| EURCHF | 100% (PF 1.85 / 1.42) | 66% (PF 1.39 / 1.06) | 5% |
| EURGBP | 71% | 21% | 0% |
| AUDNZD | 53% | 28% | 9% |

Best EURCHF setting picked on 2025 at 0.5x spread: Asian-session TWAP fade (z 2, stop 3 ATR): 20 trades a year,
70-75% wins, PF 5.05 -> 3.54, **$1,000 -> $1,749 in 2026** (DD -19%); Bollinger(50, 3) Asian fade: PF 4.09 -> 4.34,
$1,268 (DD -7%). A real but small edge, only on a low-spread account (Exness Raw Spread / Zero) and only ~20 trades/yr.
