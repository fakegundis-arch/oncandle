# Deep search at 10% risk per trade (built from scratch)

**Search:** 5,880 backtests covering 46 session-restricted entry types (ORB, Asian-range break, previous-day
high/low break, Donchian + H1 trend, EMA pullbacks, trend v2, RSI2 reversion, opening drive follow/fade, run fade),
3 stop rules and 10 exit rules, on BTC, gold, Nasdaq and Dow M1/M5/M15 data with Exness spreads. Each was scored
by what $1,000 becomes at 10% risk. It was followed by a 2,730-run fine grid on the winning family.

## The trap
The single best strategy by 2025 results (Dow Asian-range break in New York, trail 4 ATR) turned $1,000 into
**$262,000 in 2025 and $10 in 2026**. Of the top 50 picks by 2025, only 42% made money in 2026.

## Choosing by family robustness (2025 only)
Gold **Donchian breakout + ~50h trend filter, M15, Asian session** was the only family with 100% of its
stop/exit variants profitable in 2025. In 2026 (unseen), 83% were profitable, with a median of 2.2x at 10% risk.
In the fine grid, Donchian 10-55 with a 50-100h trend filter was profitable in 80-98% of 2026 variants.

## Final pick (by 2025 profit factor within the family)
XAUUSD M15, new trades only 00:00-06:00 UTC (Tokyo). Long when the close breaks the prior 20-bar high, price > EMA200
(M15) and the EMA is rising vs 1 h ago (shorts mirror). Stop 1.5 x ATR(14), target 3R, stop to +0.1R at +1R.
Re-verified minute by minute on M1:

| Period | Trades | Win | PF | $1,000 at 10% risk | Max drawdown |
|---|---|---|---|---|---|
| Q4 2024 (unseen) | 60 | 57% | 1.25 | $1,131 | -79% |
| 2025 (used to choose) | 228 | 64% | 1.96 | $260,440 (in-sample, overstated) | -59% |
| **2026 (unseen)** | 182 | 53% | 1.38 | **$3,853** | **-74%** |

2026 month-end balances: Jan $2,778, Feb $2,360, Mar $2,025, **Apr $1,438**, May $1,723, Jun $1,804,
Jul $1,481, **Aug $4,074**, Sep $4,940, Oct $3,853. Longest losing streak: 6. Median stop $8.78/oz, median hold 1.3 h.

EA: `mt5/Experts/GoldAsianBreakout.mq5` on XAUUSD M15 (defaults = these rules, 10% risk, session 0-6 server time).

---
# Round 3: all 11 markets (`deep_all_markets.csv`, 16,170 backtests)
Markets: Dow, Nasdaq, S&P 500, gold, silver, WTI oil, BTC, EURUSD, GBPUSD, USDJPY, USDCAD. Same 46 session entries
x 3 stops x 10 exits at 10% risk, chosen on 2025 and judged on 2026.

* The best single configs by 2025 failed again: the top pick went to $10 in 2026, and only 38% of the top 50 made money.
* By family robustness, **only gold in the Asian session survived**: Donchian + trend (100% / 83% of variants
  profitable in 2025 / 2026) and the previous-day high/low break (90% / 85%). The best family of every other market
  dropped to 0-7% profitable in 2026, including all FX pairs, S&P 500, silver, oil and BTC.

## Combining the two gold Asian signals (`gold_asian_combined.csv`)
Either signal opens a trade (one at a time). The combined family was profitable in 95-100% of its stop/exit variants in 2026.
Final pick by 2025: **Donchian10 + 100h trend OR previous-day break, stop 1.5 ATR, target 3R, stop to +0.1R at +1R**.
Verified minute by minute on M1:

| Period | Trades | Win | PF | $1,000 at 10% risk | Max drawdown |
|---|---|---|---|---|---|
| Q4 2024 (unseen) | 88 | 52% | 1.21 | $1,074 | **-87%** |
| 2025 (used to choose) | 309 | 60% | 1.74 | $375,054 (in-sample, overstated) | -69% |
| **2026 (unseen)** | 260 | 53% | 1.46 | **$15,953** | **-78%** |

2026 month-end balances: Jan $5,558, Feb $3,855, Mar $5,747, Apr $3,696, May $7,544, Jun $7,865, Jul $6,110, Aug $8,825,
Sep $11,001, Oct $15,953. Longest losing streak in 2026: 8 trades (about -57% at 10% risk).

EA: `mt5/Experts/GoldAsianBreakout.mq5` (defaults updated: Donchian 10, EMA 400, previous-day break on).

## Break-even on vs off (combined gold Asian strategy, M1-verified, 10% risk)
| Version | 2026 trades | Win | PF 2026 | $1,000 in 2026 | Max DD 2026 | Longest losing streak 2026 | Q4 2024 |
|---|---|---|---|---|---|---|---|
| **1:3 with break-even (default)** | 260 | 53% | 1.46 | **$15,953** | -78% | 8 | $1,074 (DD -87%) |
| 1:3 no break-even | 240 | 32% | 1.42 | $20,662 | -85% | 11 | $641 (DD -96%, 28 losses in a row) |
| 1:2 no break-even | 271 | 38% | 1.23 | $2,940 | -84% | 12 | $985 |
| 1:4 no break-even | 226 | 26% | 1.41 | $9,551 | -91% | 17 | $257 |
| 1:2 with break-even | 280 | 54% | 1.26 | $3,458 | -86% | 8 | $882 |

Without break-even, 1:3 ended higher in 2026, mostly thanks to July (peak $27,423), but with deeper drawdowns,
longer losing streaks and a near wipe-out in Q4 2024. Break-even stays the default; set `InpBETrigger = 0` in the EA to disable it.
