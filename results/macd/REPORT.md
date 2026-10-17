# Gold MACD v2

Engine: `backtester/macd.py` (signals on the chart timeframe, every trade simulated minute by minute on M1, $0.20 spread).
Search: `scripts/macd_improve.py` (one-change sweep -> `sweep.csv`, 1,296 combinations -> `combo.csv`,
1,152 neighbours -> `neighbourhood.csv`). Chosen on Q4 2024 + 2025; 2026 is the check.
The engine reproduces v1 exactly (2026: 54 trades, 50% wins, $1,000 -> $2,882 at 10%).

## Changes
| Setting | v1 (OnCandleTrend MACD preset) | **v2** (`GoldMacdV2.mq5`) |
|---|---|---|
| Chart | H4 | **H2** (about twice as many trades) |
| Stop | 3 x ATR(14) | **2 x ATR(14)** |
| Target | none (exit on opposite cross) | **3R** (opposite cross still exits / reverses) |
Unchanged: MACD(12,26,9) signal-line cross, EMA(100) trend filter, reversal on an opposite signal.

## Results ($1,000)
| Period | Version | Trades | Win | PF | 5% risk | 10% risk |
|---|---|---|---|---|---|---|
| Q4 2024 | v1 | 14 | 43% | 1.77 | $1,133 (DD -5%) | $1,254 (-10%) |
| | **v2** | 31 | 42% | 1.90 | $1,444 (-12%) | $1,879 (-23%) |
| 2025 | v1 | 59 | 47% | 2.60 | $2,216 (-13%) | $4,419 (-25%) |
| | **v2** | 125 | 43% | 1.97 | $5,440 (-28%) | $19,215 (-49%) |
| **2026** | v1 | 54 | 50% | 2.32 | $1,787 (-18%) | $2,882 (-33%) |
| | **v2** | 88 | 47% | 2.22 | **$4,811** (-18%) | **$15,968** (-33%) |

2026 month-end at 10% (v2): Jan $2,081, Feb $2,494, Mar $5,057, Apr $6,010, May $6,343, Jun $11,148, Jul $9,958,
Aug $12,759, Sep $15,837, Oct $15,968.
Robustness: all 1,152 neighbours (H1.5-H3, EMA 80-150, stop 1.75-2.5, RR 2.5-4, MACD fast 10-14, with/without a
daily-trend filter) are profitable in 2025 and 2026 (99% in Q4 2024). Median 2026 result $7,709 (10th percentile
$3,460) vs v1 $2,882, so the pick ($15,968) is at the good end but the improvement is broad.
Risks: longest losing streak 12 trades (vs 6 for v1); 2025 drawdown -49% at 10%. Median hold 19 h.

## Tested and not adopted
H1 / H6 / D1, other MACD lengths, EMA 50/200/400, zero-line filter, ADX filter (fewer trades; lower drawdown but less
profit), trailing stops, break-even, exit on EMA cross, no reversal.
