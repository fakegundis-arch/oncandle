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
