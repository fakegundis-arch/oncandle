# Session strategies on M1 (Asian / London / New York)

972 variants were tested on BTC, gold, Nasdaq and Dow, with new trades opened only inside the session.
The families were opening-range breakout, Asian-range breakout into London, session-mean fade,
opening drive (follow or fade), and Trend Rider v2 restricted to one session. Exness spreads,
discovery on 2025, validation on 2026.

* 70 variants had PF > 1.1 in 2025; **28 were also profitable in 2026**.
* Clear winner: **Nasdaq, Trend Rider v2, Asian session only** (Tokyo 09:00-15:00 = 00:00-06:00 UTC).
  4/4 variants were profitable in both years, as were **all 36 neighbouring settings**.

## Winner: USTEC/NAS100 M1, Asian session
Trend judged on completed M5 bars (EMA20/50, slope, ADX > 20, efficiency ratio > 0.3, held through pullbacks).
Entry is an M1 pullback to EMA20 with EMA20 > 50 > 200. **New trades only 00:00-06:00 UTC.** Stop >= 40 points,
target 1:3, stop to entry + 0.1R at 1R. Trades stay open after the session (median hold 1.8 h).

| Spread (pts) | 2025 PF | 2026 PF |
|---|---|---|
| 1.5 (actual Asian-hours median) | 1.26 | 1.39 |
| 3.0 | 1.18 | 1.26 |
| 5.0 | 1.04 | 1.12 |

Q4 2024 was about break-even (PF 1.03); 7 of 9 quarters were positive.

$1,000 in 2026 (spread 1.5): 1% -> $2,060 (DD -18%); 2% -> $3,862 (-33%); **3% (half-Kelly from 2025)
-> $6,613 (-46%)**; 5% -> $14,969 (-66%); 7.5% -> $26,340 (-82%); 10% -> $28,878 (-91%).

EA: `mt5/Experts/TrendRiderV2.mq5` on USTEC M1 with MinStopPrice 40, RR 3, BETrigger 1,
SessionStart 0, SessionEnd 6 (server time GMT+0).
